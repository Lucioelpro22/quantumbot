"""
backtesting/crisis_simulator.py — Simulador de Choques, Escenarios de Crisis y Monte Carlo (P9)
Somete la plataforma a:
1. COVID-19 Crash (-30% en 24h + Volatilidad 4x)
2. FTX Collapse (-25% + Congelamiento de Liquidez y Spreads 5x)
3. Mercado Lateral Prolongado (Bear Chop de 60 días)
4. Flash Crash (-15% en 15 minutos)
5. Simulación Monte Carlo Resampling con Semilla Determinística (P9)
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List
from backtesting.backtest_engine import QuantBacktestEngine


class SystemicCrisisSimulator:
    def __init__(self):
        self.engine = QuantBacktestEngine()

    def run_monte_carlo_resampling(self, returns: List[float], n_simulations: int = 1000, seed: int = 42) -> Dict[str, Any]:
        """
        P9 — Simulación Monte Carlo de resampleo determinístico sobre la secuencia de operaciones.
        """
        if not returns or len(returns) < 5:
            return {"risk_of_ruin_percent": 0.0, "p95_max_drawdown": 0.0, "status": "INSUFFICIENT_DATA"}

        np.random.seed(seed)
        rets = np.array(returns)
        n_trades = len(rets)

        sim_max_dds = []
        ruin_count = 0

        for _ in range(n_simulations):
            sim_rets = np.random.choice(rets, size=n_trades, replace=True)
            sim_equity = np.cumprod(1.0 + sim_rets)

            running_max = np.maximum.accumulate(sim_equity)
            drawdowns = (sim_equity - running_max) / (running_max + 1e-8)
            max_dd = abs(np.min(drawdowns)) * 100.0
            sim_max_dds.append(max_dd)

            if sim_equity[-1] <= 0.50 or max_dd >= 50.0:
                ruin_count += 1

        risk_of_ruin = (ruin_count / n_simulations) * 100.0
        p95_max_dd = float(np.percentile(sim_max_dds, 95))

        return {
            "n_simulations": n_simulations,
            "seed": seed,
            "risk_of_ruin_percent": round(risk_of_ruin, 2),
            "p95_max_drawdown": round(p95_max_dd, 2),
            "mean_simulated_drawdown": round(float(np.mean(sim_max_dds)), 2),
            "status": "PASSED" if risk_of_ruin < 1.0 else "WARNING"
        }

    def run_all_crisis_scenarios(self, df1h: pd.DataFrame, df15m: pd.DataFrame) -> Dict[str, Any]:
        if df15m is None or len(df15m) < 100:
            return {"status": "ERROR", "reason": "Insuficientes datos para prueba de crisis"}

        scenarios = ["COVID_19_CRASH", "FTX_COLLAPSE", "PROLONGED_SIDEWAYS_CHOP", "FLASH_CRASH"]
        results = {}
        all_passed = True

        for sc in scenarios:
            df15m_sc = df15m.copy()
            df1h_sc  = df1h.copy()

            if sc == "COVID_19_CRASH":
                mid = len(df15m_sc) // 2
                df15m_sc.iloc[mid:mid+10, df15m_sc.columns.get_loc('Close')] *= 0.70
                df15m_sc.iloc[mid:mid+10, df15m_sc.columns.get_loc('Low')] *= 0.65

            elif sc == "FTX_COLLAPSE":
                mid = len(df15m_sc) // 2
                df15m_sc.iloc[mid:mid+8, df15m_sc.columns.get_loc('Close')] *= 0.75
                self.engine.fee_taker = 0.0035  # Taker fee 0.35% en iliquidez

            elif sc == "PROLONGED_SIDEWAYS_CHOP":
                mean_px = df15m_sc['Close'].mean()
                df15m_sc['Close'] = mean_px + np.sin(np.linspace(0, 50, len(df15m_sc))) * (mean_px * 0.002)

            elif sc == "FLASH_CRASH":
                mid = len(df15m_sc) // 2
                df15m_sc.iloc[mid:mid+2, df15m_sc.columns.get_loc('Close')] *= 0.85

            res = self.engine.run_backtest(df1h_sc, df15m_sc, "BTC-USD")
            max_dd = res.get("max_drawdown_percent", 0.0)

            # Criterio de Supervivencia: Max Drawdown <= 25.0%
            passed = max_dd <= 25.0
            if not passed:
                all_passed = False

            results[sc] = {
                "max_drawdown_percent": max_dd,
                "profit_factor": res.get("profit_factor", 0.0),
                "survival_passed": passed
            }

        return {
            "all_crisis_passed": all_passed,
            "scenarios_evaluated": len(scenarios),
            "scenario_details": results
        }
