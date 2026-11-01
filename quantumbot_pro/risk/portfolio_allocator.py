"""
risk/portfolio_allocator.py — Gestor de Cartera Institucional (Institutional Portfolio Allocator)
Decide la asignación de capital pensando como un Gestor de Fondos Cuantitativo:
Capital ➔ Riesgo Disponible ➔ Matriz de Correlación ➔ Volatilidad Objetivo ➔ Asignación Óptima.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List


class PortfolioRiskAllocator:
    def __init__(self, target_portfolio_volatility: float = 0.15, max_risk_per_trade_pct: float = 0.015):
        self.target_portfolio_volatility = target_portfolio_volatility  # 15% Volatilidad Anualizada Target
        self.max_risk_per_trade_pct = max_risk_per_trade_pct              # 1.5% Máximo riesgo por operación

    def calculate_optimal_allocation(self, capital_usd: float, symbol: str, entry_price: float,
                                     atr_price: float, correlation_matrix: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Calcula la asignación óptima de margen en USD y unidades respetando el presupuesto de riesgo global.
        """
        if capital_usd <= 0 or entry_price <= 0:
            return {"margin_usd": 25.0, "quantity": 0.0, "risk_pct": 0.0}

        # 1. Presupuesto Máximo de Riesgo ($USD)
        risk_budget_usd = capital_usd * self.max_risk_per_trade_pct

        # 2. Distancia al Stop Loss basado en ATR (1.5x ATR)
        stop_distance_usd = max(atr_price * 1.5, entry_price * 0.01)

        # 3. Tamaño en Unidades según Presupuesto de Riesgo
        units = risk_budget_usd / stop_distance_usd if stop_distance_usd > 0 else 0.0
        position_notional_usd = units * entry_price

        # 4. Ajuste por Volatilidad Objetivo y Apalancamiento ISOLATED 20x
        required_margin_usd = min(100.0, max(15.0, position_notional_usd / 20.0))

        # Re-calcular unidades finales según el margen real
        final_notional_usd = required_margin_usd * 20.0
        final_units = final_notional_usd / entry_price

        return {
            "symbol": symbol,
            "margin_usd": round(required_margin_usd, 2),
            "notional_usd": round(final_notional_usd, 2),
            "quantity": round(final_units, 4),
            "risk_budget_usd": round(risk_budget_usd, 2),
            "stop_distance_usd": round(stop_distance_usd, 4),
            "effective_risk_pct": round((risk_budget_usd / capital_usd) * 100.0, 2)
        }
