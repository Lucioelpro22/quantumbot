"""
execution/reconciler.py — Motor de Reconciliación de Estado con el Exchange (P0.5)
Consulta el estado real del exchange (Bybit/BingX) al iniciar, reiniciar o reconectar.
Reconcilia:
- Posiciones activas reales (Símbolo, Lado, Cantidad, Precio Promedio).
- Verificación de existencia de Stop Loss y Take Profit.
- Sincronización con la base de datos local SQLite quantumbot.db.
"""

import os
import sys
import asyncio
from typing import Dict, Any, Union

exec_dir = os.path.dirname(os.path.abspath(__file__))
quantumbot_dir = os.path.dirname(exec_dir)
root_dir = os.path.dirname(quantumbot_dir)

for path in [exec_dir, quantumbot_dir, root_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

from database.db_manager import QuantDatabaseManager
from bybit_client import BybitClient
from bingx_client import BingXClient


class ExchangeStateReconciler:
    def __init__(self, client: Union[BybitClient, BingXClient], db_manager: QuantDatabaseManager = None):
        self.client = client
        self.db_manager = db_manager or QuantDatabaseManager()

    def reconcile_state(self) -> Dict[str, Any]:
        """
        P0.5 — Reconciliación síncrona/asíncrona del estado del exchange con SQLite.
        """
        print("🔄 [P0.5 Exchange Reconciliation] Sincronizando estado real con el exchange...")

        from execution.bybit_executor import parse_active_positions, ExchangeStateUnknown
        if not isinstance(self.client, BybitClient):
            raise ExchangeStateUnknown('Unsupported reconciliation client')
        positions_summary = parse_active_positions(self.client.get_positions())
        for position in positions_summary.values():
            try:
                from execution.bybit_executor import _number
                _number(position.get('stopLoss'), positive=True)
                _number(position.get('takeProfit'), positive=True)
            except ExchangeStateUnknown:
                raise ExchangeStateUnknown('Unprotected position; reconciliation blocked')

        # Sincronizar estado de posiciones parcialmente cerradas en SQLite
        saved_partials = self.db_manager.get_partial_closed_positions()
        print(f"📦 [Estado Persistente SQLite] {len(saved_partials)} posiciones registradas con cierre parcial previo.")

        return {
            "status": "RECONCILED",
            "active_exchange_positions": len(positions_summary),
            "positions_detail": positions_summary,
            "saved_partial_closes": len(saved_partials)
        }
