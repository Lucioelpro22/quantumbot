"""
bybit_client.py — Cliente REST HMAC SHA256 para la API V5 de Bybit (Demo Trading & Real)
Soporta consulta de balance UTA, posiciones activas, envío de órdenes a mercado y configuración de palanca/margen.
Incluye reintentos automáticos con exponencial backoff ante fallas de red/conexión.
Endpoints:
- Demo Trading: https://api-demo.bybit.com
- Testnet:     https://api-testnet.bybit.com
- Mainnet Real:https://api.bybit.com
"""

import time
import hmac
import hashlib
import json
import requests
from urllib.parse import urlencode
from typing import Dict, Any, Optional


class BybitClient:
    def __init__(self, api_key: str, secret_key: str, use_testnet: bool = True, use_demo: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.use_testnet = use_testnet
        self.use_demo = use_demo

        if use_demo:
            self.base_url = "https://api-demo.bybit.com"
        elif use_testnet:
            self.base_url = "https://api-testnet.bybit.com"
        else:
            self.base_url = "https://api.bybit.com"

        self.recv_window = "5000"

    def _generate_signature(self, timestamp: str, payload: str) -> str:
        param_str = timestamp + self.api_key + self.recv_window + payload
        hash_obj = hmac.new(self.secret_key.encode('utf-8'), param_str.encode('utf-8'), hashlib.sha256)
        return hash_obj.hexdigest()

    def _headers(self, timestamp: str, signature: str) -> Dict[str, str]:
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.recv_window,
            "Content-Type": "application/json"
        }

    def request(self, method: str, path: str, params: Dict[str, Any] = None, max_retries: int = 3) -> Dict[str, Any]:
        params = params or {}
        last_exception = None

        for attempt in range(1, max_retries + 1):
            timestamp = str(int(time.time() * 1000))
            url = f"{self.base_url}{path}"
            try:
                if method == 'GET':
                    query_str = urlencode(sorted(params.items()))
                    signature = self._generate_signature(timestamp, query_str)
                    full_url = f"{url}?{query_str}" if query_str else url
                    r = requests.get(full_url, headers=self._headers(timestamp, signature), timeout=10)
                else:
                    payload = json.dumps(params)
                    signature = self._generate_signature(timestamp, payload)
                    r = requests.post(url, data=payload, headers=self._headers(timestamp, signature), timeout=10)

                if r.status_code == 200:
                    return r.json()
                elif r.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                else:
                    return {"retCode": r.status_code, "retMsg": r.text}
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    time.sleep(0.5 * (2 ** attempt))
                    continue

        return {"retCode": -1, "retMsg": f"Connection Error after {max_retries} retries: {last_exception}"}

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
        self.request('POST', '/v5/position/set-leverage', params_lev)

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
