"""
execution/bingx_executor.py — Enrutador Asincrónico de Órdenes BingX (VST Demo & Real)
Maneja la autenticación HMAC SHA256, ejecución de órdenes a mercado y cancelación de TP/SL.
"""

import asyncio
import os
import sys
import requests
from typing import Dict, Any, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bingx_client import BingXClient
from core.models import RiskDecision


class AsyncBingXExecutor:
    def __init__(self, api_key: str, secret_key: str, use_vst: bool = True):
        self.client = BingXClient(api_key, secret_key, use_vst=use_vst)
        self.use_vst = use_vst

    async def get_account_balance(self) -> float:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, self.client.get_balance)
        if res.get('code') == 0:
            return float(res['data'][0].get('equity', 0.0))
        return 0.0

    async def get_active_positions(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, self.client.get_positions)
        positions = {}
        if res.get('code') == 0:
            for p in res.get('data', []):
                amt = abs(float(p.get('positionAmt', 0)))
                if amt > 0:
                    positions[p['symbol']] = p
        return positions

    async def execute_trade_decision(self, decision: RiskDecision) -> Dict[str, Any]:
        if not decision.is_allowed:
            return {"status": "REJECTED", "reason": decision.reason}

        loop = asyncio.get_running_loop()
        symbol   = decision.symbol
        side     = "BUY" if decision.direction.value == "LONG" else "SELL"
        pos_side = decision.direction.value
        qty      = decision.quantity

        # 1. Configurar palanca e ISOLATED
        await loop.run_in_executor(
            None, self.client.setup_symbol, symbol, "ISOLATED", decision.leverage
        )

        # 2. Enviar orden MARKET
        order_res = await loop.run_in_executor(
            None, self.client.place_order, symbol, side, pos_side, "MARKET", qty
        )

        if order_res.get('code') == 0:
            # 3. Adjuntar Stop Loss y Take Profit
            sl_side = "SELL" if pos_side == "LONG" else "BUY"

            def _attach_tp_sl():
                self.client.request('POST', '/openApi/swap/v2/trade/order', {
                    'symbol': symbol, 'side': sl_side, 'positionSide': pos_side,
                    'type': 'STOP_MARKET', 'quantity': str(qty),
                    'stopPrice': str(decision.stop_loss_price), 'workingType': 'MARK_PRICE'
                })
                self.client.request('POST', '/openApi/swap/v2/trade/order', {
                    'symbol': symbol, 'side': sl_side, 'positionSide': pos_side,
                    'type': 'TAKE_PROFIT_MARKET', 'quantity': str(qty),
                    'stopPrice': str(decision.take_profit_price), 'workingType': 'MARK_PRICE'
                })

            await loop.run_in_executor(None, _attach_tp_sl)
            return {"status": "SUCCESS", "order": order_res}
        else:
            return {"status": "ERROR", "reason": order_res.get('msg')}
