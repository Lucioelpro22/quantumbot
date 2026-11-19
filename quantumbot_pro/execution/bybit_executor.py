"""Offline-testable order protocol; the concrete Bybit transport stays denied.

Uncertain execution latches this executor closed. Reconciliation, rather than a
new entry or automatic retry, is required after any possible exposure.
"""
from __future__ import annotations

import asyncio
import math
import uuid
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import TYPE_CHECKING, Any

from bybit_client import BybitClient

if TYPE_CHECKING:
    from core.models import RiskDecision


class ExchangeStateUnknown(RuntimeError):
    """The exchange did not supply a complete trustworthy state."""


def _rows(response):
    if not isinstance(response, dict) or response.get('retCode') != 0:
        raise ExchangeStateUnknown('Exchange query failed')
    result = response.get('result')
    if not isinstance(result, dict) or not isinstance(result.get('list'), list):
        raise ExchangeStateUnknown('Exchange response is incomplete')
    if result.get('nextPageCursor'):
        raise ExchangeStateUnknown('Incomplete paginated response; reconciliation required')
    if not all(isinstance(row, dict) for row in result['list']):
        raise ExchangeStateUnknown('Malformed exchange records')
    return result['list']


def _number(value, *, positive=False):
    try:
        if isinstance(value, bool):
            raise ValueError()
        result = float(value)
        if not math.isfinite(result) or result < 0 or (positive and result <= 0):
            raise ValueError()
        return result
    except (ValueError, TypeError, OverflowError) as exc:
        raise ExchangeStateUnknown('Invalid exchange numeric field') from exc


def parse_active_positions(response):
    active = {}
    for pos in _rows(response):
        size = _number(pos.get('size'))
        if size == 0:
            continue
        symbol = pos.get('symbol')
        if not isinstance(symbol, str) or not symbol or symbol in active:
            raise ExchangeStateUnknown('Missing or ambiguous position identity')
        if pos.get('side') not in ('Buy', 'Sell') or type(pos.get('positionIdx')) is not int:
            raise ExchangeStateUnknown('Incomplete position identity')
        if pos['positionIdx'] not in (0, 1, 2):
            raise ExchangeStateUnknown('Invalid position index')
        if pos.get('positionStatus') != 'Normal':
            raise ExchangeStateUnknown('Position is not in a normal state')
        active[symbol] = pos
    return active


class AsyncBybitExecutor:
    def __init__(self, api_key: str, secret_key: str, use_testnet: bool = True):
        self.reconciliation_required = False
        self.client = BybitClient(api_key, secret_key, use_testnet=use_testnet, use_demo=use_testnet)

    async def _call(self, method, *args, **kwargs):
        return await asyncio.to_thread(method, *args, **kwargs)

    async def _normalize_quantity(self, symbol, quantity):
        rows = _rows(await self._call(self.client.get_instrument, symbol))
        matches = [row for row in rows if row.get('symbol') == symbol]
        if len(matches) != 1:
            raise ExchangeStateUnknown('Instrument identity missing or ambiguous')
        try:
            lot = matches[0]['lotSizeFilter']
            step, minimum = Decimal(lot['qtyStep']), Decimal(lot['minOrderQty'])
            requested = Decimal(str(quantity))
            if not all(x.is_finite() and x > 0 for x in (step, minimum, requested)):
                raise ValueError()
            qty = (requested / step).to_integral_value(rounding=ROUND_DOWN) * step
            maximum = Decimal(lot['maxMktOrderQty'])
            if not maximum.is_finite() or maximum <= 0:
                raise ValueError()
            if qty < minimum or qty > maximum:
                return Decimal(0)
            return qty
        except (KeyError, InvalidOperation, ValueError, TypeError) as exc:
            raise ExchangeStateUnknown('Invalid instrument limits') from exc

    async def _confirm_order(self, symbol, order_id):
        for _ in range(10):
            rows = _rows(await self._call(self.client.get_order, symbol, order_id))
            matches = [row for row in rows if row.get('orderId') == order_id and row.get('symbol') == symbol]
            if len(matches) > 1 or (rows and not matches):
                raise ExchangeStateUnknown('Order identity mismatch')
            if matches:
                order = matches[0]
                if order.get('orderStatus') in ('Filled', 'PartiallyFilled', 'PartiallyFilledCanceled',
                                               'Cancelled', 'Rejected', 'Deactivated'):
                    return order
            await asyncio.sleep(0.5)
        raise ExchangeStateUnknown('Order outcome unknown')

    async def get_account_balance(self):
        rows = _rows(await self._call(self.client.get_balance))
        if len(rows) != 1:
            raise ExchangeStateUnknown('Account identity ambiguous')
        return _number(rows[0].get('totalEquity'), positive=True)

    async def get_active_positions(self):
        try:
            return parse_active_positions(await self._call(self.client.get_positions))
        except Exception:
            self.reconciliation_required = True
            raise

    async def set_sl_tp_protection(self, symbol, position_idx, stop_loss, take_profit):
        clean_symbol = symbol.replace('-', '')
        # A full protection proof needs BOTH prices, the exact position and a
        # successful modification response; any old positive stop is insufficient.
        _number(stop_loss, positive=True)
        _number(take_profit, positive=True)
        response = await self._call(self.client.request, 'POST', '/v5/position/trading-stop', {
            'category': 'linear', 'symbol': clean_symbol, 'positionIdx': position_idx,
            'stopLoss': str(stop_loss), 'takeProfit': str(take_profit),
            'slTriggerBy': 'MarkPrice', 'tpTriggerBy': 'MarkPrice', 'tpslMode': 'Full',
        })
        if not isinstance(response, dict) or response.get('retCode') != 0:
            return False
        rows = _rows(await self._call(self.client.get_positions, symbol=clean_symbol))
        matches = [p for p in rows if p.get('symbol') == clean_symbol
                   and p.get('positionIdx') == position_idx and _number(p.get('size')) > 0]
        if len(matches) != 1:
            return False
        position = matches[0]
        side = 'Buy' if position_idx == 1 else 'Sell'
        if position.get('side') != side or position.get('positionStatus') != 'Normal':
            return False
        try:
            return (Decimal(str(position.get('stopLoss'))) == Decimal(str(stop_loss))
                    and Decimal(str(position.get('takeProfit'))) == Decimal(str(take_profit)))
        except InvalidOperation:
            return False

    def _uncertain(self, client_order_id, order_id=None, order=None):
        self.reconciliation_required = True
        return {'status': 'RECONCILIATION_REQUIRED', 'client_order_id': client_order_id,
                'order_id': order_id, 'order_status': (order or {}).get('orderStatus', 'Unknown'),
                'filled_qty': (order or {}).get('cumExecQty'), 'sl_confirmed': False}

    async def execute_trade_decision(self, decision: RiskDecision) -> dict[str, Any]:
        if self.reconciliation_required:
            raise ExchangeStateUnknown('Executor latched: reconciliation required')
        if not decision.is_allowed:
            return {'status': 'REJECTED', 'reason': decision.reason}
        symbol = decision.symbol.replace('-', '')
        direction = decision.direction.value
        if direction not in ('LONG', 'SHORT') or not 1 <= decision.leverage <= 3:
            return {'status': 'REJECTED', 'reason': 'Invalid direction or leverage'}
        side, idx = ('Buy', 1) if direction == 'LONG' else ('Sell', 2)
        _number(decision.stop_loss_price, positive=True)
        _number(decision.take_profit_price, positive=True)
        if ((direction == 'LONG' and decision.stop_loss_price >= decision.take_profit_price)
                or (direction == 'SHORT' and decision.stop_loss_price <= decision.take_profit_price)):
            return {'status': 'REJECTED', 'reason': 'Invalid protection ordering'}
        setup = await self._call(self.client.setup_symbol, symbol, is_isolated=True, leverage=decision.leverage)
        if not isinstance(setup, dict) or setup.get('retCode') not in (0, 110026):
            return {'status': 'REJECTED', 'reason': 'Margin/leverage setup failed'}
        qty = await self._normalize_quantity(symbol, decision.quantity)
        if qty <= 0:
            return {'status': 'REJECTED', 'reason': 'Quantity outside instrument limits'}
        client_id = 'QB_' + uuid.uuid4().hex  # 35 characters; stable for this attempt.
        params = {
            'category': 'linear', 'symbol': symbol, 'side': side, 'orderType': 'Market',
            'qty': str(qty), 'positionIdx': idx, 'orderLinkId': client_id, 'timeInForce': 'IOC',
            'takeProfit': str(decision.take_profit_price), 'stopLoss': str(decision.stop_loss_price),
            'tpTriggerBy': 'MarkPrice', 'slTriggerBy': 'MarkPrice', 'tpslMode': 'Full',
            'tpOrderType': 'Market', 'slOrderType': 'Market',
        }
        order_id = None
        try:
            # Exactly one submission. Never automatically retry an uncertain POST.
            response = await self._call(self.client.request, 'POST', '/v5/order/create', params)
            if not isinstance(response, dict) or response.get('retCode') != 0:
                return self._uncertain(client_id)
            order_id = response.get('result', {}).get('orderId')
            if not isinstance(order_id, str) or not order_id:
                return self._uncertain(client_id)
            order = await self._confirm_order(symbol, order_id)
            if order.get('orderStatus') != 'Filled':
                return self._uncertain(client_id, order_id, order)
            filled = _number(order.get('cumExecQty'), positive=True)
            avg_price = _number(order.get('avgPrice'), positive=True)
            if Decimal(str(filled)) != qty:
                return self._uncertain(client_id, order_id, order)
            protected = await self.set_sl_tp_protection(
                symbol, idx, decision.stop_loss_price, decision.take_profit_price)
            if not protected:
                return self._uncertain(client_id, order_id, order)
            return {'status': 'SUCCESS', 'client_order_id': client_id, 'order_id': order_id,
                    'order_status': 'Filled', 'filled_qty': filled, 'avg_price': avg_price,
                    'sl_confirmed': True}
        except Exception:
            return self._uncertain(client_id, order_id)
