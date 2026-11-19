"""Bybit protocol helpers with unconditional denial at the transport boundary.

No HTTP implementation, credentials, network retries or mainnet routing remain.
Methods are retained for offline protocol fixtures, not operational permission.
"""
from typing import Dict, Any
from operational_policy import require_operational_access


class BybitClient:
    def __init__(self, api_key=None, secret_key=None, use_testnet=True, use_demo=True):
        require_operational_access("bybit_client")

    def request(self, method, path, params=None, max_retries=0):
        require_operational_access("bybit_transport")

    def get_balance(self) -> Dict[str, Any]:
        """Consulta balance de la cuenta de Trading Unificada (UTA)"""
        return self.request('GET', '/v5/account/wallet-balance', {'accountType': 'UNIFIED', 'coin': 'USDT'})

    def get_positions(self, category: str = "linear", symbol: str = None) -> Dict[str, Any]:
        """Consulta posiciones abiertas activas"""
        params = {'category': category, 'settleCoin': 'USDT'}
        if symbol:
            params['symbol'] = symbol
        return self.request('GET', '/v5/position/list', params)

    def get_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        return self.request('GET', '/v5/order/realtime', {
            'category': 'linear', 'symbol': symbol, 'orderId': order_id
        })

    def get_instrument(self, symbol: str) -> Dict[str, Any]:
        return self.request('GET', '/v5/market/instruments-info', {
            'category': 'linear', 'symbol': symbol
        })

    def get_closed_pnl(self, start_ms: int = None, end_ms: int = None, cursor: str = None) -> Dict[str, Any]:
        params = {'category': 'linear', 'limit': 100}
        if start_ms is not None: params['startTime'] = start_ms
        if end_ms is not None: params['endTime'] = end_ms
        if cursor: params['cursor'] = cursor
        return self.request('GET', '/v5/position/closed-pnl', params)

    def setup_symbol(self, symbol: str, is_isolated: bool = True, leverage: int = 25) -> Dict[str, Any]:
        """Configura Apalancamiento y Margen Aislado"""
        params_lev = {'category': 'linear', 'symbol': symbol, 'buyLeverage': str(leverage), 'sellLeverage': str(leverage)}
        leverage_result = self.request('POST', '/v5/position/set-leverage', params_lev)
        if leverage_result.get('retCode') not in (0, 110043):
            return leverage_result

        trade_mode = 1 if is_isolated else 0
        params_mode = {'category': 'linear', 'symbol': symbol, 'tradeMode': trade_mode, 'buyLeverage': str(leverage), 'sellLeverage': str(leverage)}
        return self.request('POST', '/v5/position/switch-isolated', params_mode)

    def place_order(self, symbol: str, side: str, position_idx: int, order_type: str, qty: float,
                    price: float = None, reduce_only: bool = False) -> Dict[str, Any]:
        """
        positionIdx: 0 (One-Way), 1 (Hedge Buy/Long), 2 (Hedge Sell/Short)
        """
        params = {
            'category': 'linear',
            'symbol': symbol,
            'side': side.capitalize(),
            'orderType': order_type.upper(),
            'qty': str(qty),
            'positionIdx': position_idx,
            'timeInForce': 'GTC'
        }
        if reduce_only:
            params['reduceOnly'] = True
            params['closeOnTrigger'] = True
        if price:
            params['price'] = str(price)
        return self.request('POST', '/v5/order/create', params)

    def set_trading_stop(self, symbol: str, position_idx: int, stop_loss: float,
                         take_profit: float = None) -> Dict[str, Any]:
        params = {
            'category': 'linear', 'symbol': symbol, 'positionIdx': position_idx,
            'tpslMode': 'Full', 'stopLoss': str(stop_loss),
            'slTriggerBy': 'MarkPrice', 'tpOrderType': 'Market', 'slOrderType': 'Market'
        }
        if take_profit is not None and take_profit > 0:
            params['takeProfit'] = str(take_profit)
            params['tpTriggerBy'] = 'MarkPrice'
        return self.request('POST', '/v5/position/trading-stop', params)

    def close_position(self, symbol: str, side: str, position_idx: int, qty: float) -> Dict[str, Any]:
        close_side = 'Sell' if side == 'Buy' else 'Buy'
        return self.place_order(symbol, close_side, position_idx, 'Market', qty, reduce_only=True)
