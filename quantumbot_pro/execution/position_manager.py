"""
execution/position_manager.py — Gestor de Posiciones Abiertas QuantumBot Pro v3.0
Aplica cierres parciales del 50% al alcanzar 1:1 R:R (o ROI >= 20% a 25x palanca) y ajusta SL a Breakeven.
Soporta compatibilidad multi-exchange (BingX & Bybit) con persistencia en SQLite para recuperación de estado tras reinicio.
"""

import asyncio
import os
import sys
import time
from typing import Dict, Any, Union

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bingx_client import BingXClient
from bybit_client import BybitClient
from database.db_manager import QuantDatabaseManager


class QuantumPositionManager:
    def __init__(self, client: Union[BingXClient, BybitClient], db_manager: QuantDatabaseManager = None):
        self.client = client
        self.db_manager = db_manager or QuantDatabaseManager()
        # Cargar estado persistente desde la base de datos para recuperación tras reinicio
        self.partial_closed = self.db_manager.get_partial_closed_positions()

    async def manage_open_positions(self, active_positions: Dict[str, Any]):
        if not active_positions:
            return

        loop = asyncio.get_running_loop()

        for symbol, pos in active_positions.items():
            pos_side   = pos.get("positionSide") or ("LONG" if pos.get("side") == "Buy" else "SHORT")
            pos_amt    = abs(float(pos.get("positionAmt") or pos.get("size", 0)))
            entry      = float(pos.get("avgPrice", 0))
            unrealized = float(pos.get("unrealizedProfit") or pos.get("unrealisedPnl", 0))
            leverage   = float(pos.get("leverage", 25))

            if pos_amt == 0 or entry == 0:
                continue

            initial_margin = (pos_amt * entry) / leverage
            roi_pct = (unrealized / initial_margin * 100.0) if initial_margin > 0 else 0.0

            pos_key = f"{symbol}_{pos_side}_{round(entry, 4)}"

            # 1. Cierre Parcial 50% y Breakeven a 1:1 R:R (ROI >= 20% a 25x apalancamiento)
            if roi_pct >= 20.0 and pos_key not in self.partial_closed:
                half_qty = round(pos_amt / 2.0, 4)
                close_side = "SELL" if pos_side == "LONG" else "BUY"

                print(f"⚡ [Quantum Partial Exit 1:1 R:R | ROI +{roi_pct:.1f}%] {symbol} {pos_side} 50% cerrado | Ganancia: ~${unrealized * 0.5:.2f}")

                def _execute_partial():
                    if hasattr(self.client, 'place_order'):
                        if isinstance(self.client, BybitClient):
                            pos_idx = 1 if pos_side == "LONG" else 2
                            clean_symbol = symbol.replace('-', '')
                            self.client.place_order(clean_symbol, close_side, pos_idx, "MARKET", half_qty)
                        else:
                            self.client.place_order(symbol, close_side, pos_side, "MARKET", half_qty)
                            sl_side = "SELL" if pos_side == "LONG" else "BUY"
                            be_price = round(entry * 1.001 if pos_side == "LONG" else entry * 0.999, 4)
                            self.client.request('POST', '/openApi/swap/v2/trade/order', {
                                'symbol': symbol, 'side': sl_side, 'positionSide': pos_side,
                                'type': 'STOP_MARKET', 'quantity': str(round(pos_amt - half_qty, 4)),
                                'stopPrice': str(be_price), 'workingType': 'MARK_PRICE'
                            })

                await loop.run_in_executor(None, _execute_partial)
                self.partial_closed.add(pos_key)
                self.db_manager.set_position_partial_closed(pos_key, symbol, pos_side, entry)
