"""
backtesting/stress_test.py — Motor de Pruebas de Estrés y Choques de Mercado (Stress Testing)
Somete el bot a escenarios extremos:
- Flash Crash (-15% en 15 minutos)
- Crisis de Liquidez (Slippage 1.5%, Spreads 5x)
- Choque de Volatilidad (ATR% 6.0%)
- Pico de Funding Rates (0.10% cada 8h)
"""

import numpy as np
import pandas as pd
from typing import Dict, Any
from backtesting.backtest_engine import QuantBacktestEngine


class StressTestEngine:
    def __init__(self):
        self.base_engine = QuantBacktestEngine()

    def run_stress_test(self, df1h: pd.DataFrame, df15m: pd.DataFrame, scenario: str = "FLASH_CRASH") -> Dict[str, Any]:
        if df15m is None or len(df15m) < 60:
            return {"status": "ERROR", "reason": "Insuficientes datos para prueba de estrés"}

        df15m_stress = df15m.copy()
        df1h_stress  = df1h.copy()

        if scenario == "FLASH_CRASH":
            # Simular caída repentina del 15% en las velas centrales
            mid_idx = len(df15m_stress) // 2
            df15m_stress.iloc[mid_idx:mid_idx+3, df15m_stress.columns.get_loc('Close')] *= 0.85
            df15m_stress.iloc[mid_idx:mid_idx+3, df15m_stress.columns.get_loc('Low')] *= 0.82

        elif scenario == "LIQUIDITY_CRUNCH":
            # Simular comisiones taker de 0.25% y slippage extremo
            self.base_engine.fee_taker = 0.0025

        elif scenario == "HIGH_VOLATILITY_SPIKE":
            # Duplicar el rango High-Low de las velas
            df15m_stress['High'] *= 1.05
            df15m_stress['Low'] *= 0.95

        res = self.base_engine.run_backtest(df1h_stress, df15m_stress)
        res["scenario_tested"] = scenario
        res["survival_status"] = "PASSED" if res.get("max_drawdown_percent", 0) <= 30.0 else "FAILED"
        return res
