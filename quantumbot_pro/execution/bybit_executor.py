"""
execution/bybit_executor.py — Ejecutor de Órdenes Async para Bybit V5 (Demo & Real)
Maneja envío de órdenes a mercado, configuración de apalancamiento aislado, generación de orderLinkId (Client Order ID)
y VERIFICACIÓN ESTRICTA DE SL/TP CONFIRMADO EN EL EXCHANGE (P0.4).
"""

import asyncio
import time
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any
from bybit_client import BybitClient
from core.models import RiskDecision


class AsyncBybitExecutor:
    def __init__(self, api_key: str, secret_key: str, use_testnet: bool = True):
        self.use_testnet = use_testnet
        self.client = BybitClient(api_key, secret_key, use_testnet=use_testnet, use_demo=use_testnet)

    async def _normalize_quantity(self, symbol: str, quantity: float) -> float:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: self.client.get_instrument(symbol))
        try:
            lot = res['result']['list'][0]['lotSizeFilter']
            step = Decimal(str(lot['qtyStep']))
            minimum = Decimal(str(lot['minOrderQty']))
            qty = Decimal(str(quantity)).quantize(step, rounding=ROUND_DOWN)
            return float(qty) if qty >= minimum else 0.0
        except (KeyError, IndexError, TypeError, ValueError):
            return 0.0

    async def _confirm_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        for _ in range(10):
            await asyncio.sleep(0.5)
            res = await loop.run_in_executor(None, lambda: self.client.get_order(symbol, order_id))
            orders = res.get('result', {}).get('list', []) if res.get('retCode') == 0 else []
            if orders:
                status = orders[0].get('orderStatus', 'Unknown')
                if status in ('Filled', 'PartiallyFilled', 'Cancelled', 'Rejected', 'Deactivated'):
                    return orders[0]
        return {'orderStatus': 'Unconfirmed'}

    async def get_account_balance(self) -> float:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, self.client.get_balance)
        if res.get('retCode') == 0:
            try:
                lst = res['result']['list'][0]
                return float(lst.get('totalEquity') or lst.get('totalWalletBalance', 0.0))
            except (KeyError, IndexError, ValueError):
                return 0.0
        return 0.0

    async def get_active_positions(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, self.client.get_positions)
        active = {}
        if res.get('retCode') == 0:
            for pos in res.get('result', {}).get('list', []):
                size = float(pos.get('size', 0))
                if size > 0:
                    symbol = pos.get('symbol')
                    active[symbol] = pos
        return active

    async def set_sl_tp_protection(self, symbol: str, position_idx: int, stop_loss: float, take_profit: float) -> bool:
        """
        P0.4 — Envía y confirma la orden de Stop Loss y Take Profit en Bybit V5.
        """
        loop = asyncio.get_running_loop()
        clean_symbol = symbol.replace('-', '')
        params = {
            'category': 'linear',
            'symbol': clean_symbol,
            'positionIdx': position_idx,
            'stopLoss': str(round(stop_loss, 4)),
            'takeProfit': str(round(take_profit, 4)),
            'slTriggerBy': 'MarkPrice',
            'tpTriggerBy': 'MarkPrice',
            'tpslMode': 'Full'
        }

        # 1. Enviar solicitud de SL/TP
        res = await loop.run_in_executor(None, lambda: self.client.request('POST', '/v5/position/trading-stop', params))
        if res.get('retCode') != 0:
            print(f"⚠️ [Bybit SL/TP Error] {clean_symbol}: {res.get('retMsg')}")

        # 2. Re-consultar la posición en el exchange para VERIFICAR CONFIRMACIÓN REAL (P0.4)
        await asyncio.sleep(0.3)
        pos_res = await loop.run_in_executor(None, lambda: self.client.get_positions(symbol=clean_symbol))
        if pos_res.get('retCode') == 0:
            positions = pos_res.get('result', {}).get('list', [])
            for p in positions:
                if float(p.get('size', 0)) > 0:
                    ex_sl = float(p.get('stopLoss', 0) or 0)
                    if ex_sl > 0:
                        print(f"🛡️ [SL Confirmado en Bybit Exchange] {clean_symbol} SL @ ${ex_sl:.4f}")
                        return True

        print(f"🚨 [ALERTA DE SEGURIDAD P0.4] No se pudo confirmar el SL en el exchange para {clean_symbol}")
        return False

    async def execute_trade_decision(self, decision: RiskDecision) -> Dict[str, Any]:
        """
        Ejecuta la decisión de entrada con idempotencia (orderLinkId) y verificación estricta de SL/TP.
        """
        if not decision.is_allowed:
            return {"status": "REJECTED", "reason": decision.reason}

        loop = asyncio.get_running_loop()
        clean_symbol = decision.symbol.replace('-', '')
        side = "Buy" if decision.direction.value == "LONG" else "Sell"
        position_idx = 1 if decision.direction.value == "LONG" else 2

        # 1. Configurar apalancamiento e aislamiento de margen
        setup_res = await loop.run_in_executor(
            None,
            lambda: self.client.setup_symbol(clean_symbol, is_isolated=True, leverage=decision.leverage)
        )

        # La configuración puede devolver "not modified"; cualquier otro error bloquea entrada.
        if setup_res.get('retCode') not in (0, 110026):
            return {'status': 'REJECTED', 'reason': f"No se pudo aislar margen: {setup_res.get('retMsg')}"}

        quantity = await self._normalize_quantity(clean_symbol, decision.quantity)
        if quantity <= 0:
            return {'status': 'REJECTED', 'reason': 'Cantidad inferior al mínimo o metadata no disponible'}

        # 2. Generar Client Order ID único para IDEMPOTENCIA (P2.1)
        client_order_id = f"QUANTUM_{clean_symbol}_{side}_{int(time.time() * 1000)}"

        # 3. Enviar Orden de Entrada a Mercado
        order_params = {
            'category': 'linear',
            'symbol': clean_symbol,
            'side': side,
            'orderType': 'Market',
            'qty': str(quantity),
            'positionIdx': position_idx,
            'orderLinkId': client_order_id,
            'timeInForce': 'IOC',
            'takeProfit': str(decision.take_profit_price),
            'stopLoss': str(decision.stop_loss_price),
            'tpTriggerBy': 'MarkPrice',
            'slTriggerBy': 'MarkPrice',
            'tpslMode': 'Full',
            'tpOrderType': 'Market',
            'slOrderType': 'Market'
        }

        res = await loop.run_in_executor(None, lambda: self.client.request('POST', '/v5/order/create', order_params))

        if res.get('retCode') == 0:
            order_id = res['result'].get('orderId')
            confirmed = await self._confirm_order(clean_symbol, order_id)
            order_status = confirmed.get('orderStatus', 'Unconfirmed')
            if order_status != 'Filled':
                return {'status': 'NOT_FILLED', 'order_id': order_id,
                        'client_order_id': client_order_id, 'order_status': order_status}

            # TP/SL viajan con la entrada; se confirma además en la posición.
            sl_confirmed = await self.set_sl_tp_protection(
                clean_symbol, position_idx, decision.stop_loss_price, decision.take_profit_price
            )

            return {
                "status": "SUCCESS",
                "order_id": order_id,
                "client_order_id": client_order_id,
                "sl_confirmed": sl_confirmed,
                "order_status": order_status,
                "filled_qty": confirmed.get('cumExecQty', str(quantity)),
                "avg_price": confirmed.get('avgPrice')
            }
        else:
            print(f"❌ [Bybit Order Rejected] {clean_symbol}: {res.get('retMsg')}")
            return {"status": "ERROR", "reason": res.get('retMsg')}
