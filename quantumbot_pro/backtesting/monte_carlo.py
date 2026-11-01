"""
backtesting/monte_carlo.py — Motor de Simulación Monte Carlo (1,000+ Iteraciones)
Evalúa el riesgo de ruina y los intervalos de confianza del equity curve permutando el orden de
las operaciones y aplicando variaciones estocásticas de slippage y comisiones.
"""

import numpy as np
from typing import Dict, Any, List


class MonteCarloSimulator:
    def __init__(self, n_simulations: int = 1000, confidence_level: float = 0.95):
        self.n_simulations = n_simulations
        self.confidence_level = confidence_level

    def run_simulation(self, trade_returns: List[float], initial_capital: float = 10000.0) -> Dict[str, Any]:
        if not trade_returns or len(trade_returns) < 5:
            return {
                "status": "INSUFFICIENT_DATA",
                "reason": "Se requieren al menos 5 operaciones reales; no se generan retornos sintéticos."
            }

        rets = np.array(trade_returns)
        final_equities = []
        max_drawdowns = []

        for sim in range(self.n_simulations):
            # 1. Permutar orden aleatorio de trades (Resampling con reemplazo)
            perm_rets = np.random.choice(rets, size=len(rets), replace=True)

            # 2. Agregar varianza estocástica de slippage/spread (-0.002 a +0.002)
            stochastic_noise = np.random.normal(0.0, 0.001, size=len(rets))
            sim_rets = perm_rets + stochastic_noise

            # 3. Reconstruir curva de capital
            equity = initial_capital
            eq_curve = [equity]
            for r in sim_rets:
                equity += (25.0 * 20) * r  # Posición de $25 a 20x
                eq_curve.append(max(0.0, equity))

            eq_arr = np.array(eq_curve)
            running_max = np.maximum.accumulate(eq_arr)
            dds = (eq_arr - running_max) / (running_max + 1e-8)

            final_equities.append(eq_arr[-1])
            max_drawdowns.append(abs(np.min(dds)) * 100.0)

        p5_equity  = float(np.percentile(final_equities, 5))
        p50_equity = float(np.percentile(final_equities, 50))
        p95_equity = float(np.percentile(final_equities, 95))

        p5_dd  = float(np.percentile(max_drawdowns, 95))  # Peor caso de Drawdown al 95%
        p50_dd = float(np.percentile(max_drawdowns, 50))
        p95_dd = float(np.percentile(max_drawdowns, 5))

        ruin_count = sum(1 for eq in final_equities if eq <= initial_capital * 0.5)
        risk_of_ruin = (ruin_count / self.n_simulations) * 100.0

        return {
            "simulations_count": self.n_simulations,
            "risk_of_ruin_percent": round(risk_of_ruin, 2),
            "median_final_equity": round(p50_equity, 2),
            "worst_case_equity_5th_percentile": round(p5_equity, 2),
            "best_case_equity_95th_percentile": round(p95_equity, 2),
            "median_max_drawdown_percent": round(p50_dd, 2),
            "worst_case_max_drawdown_95th_percentile": round(p5_dd, 2),
            "best_case_max_drawdown_5th_percentile": round(p95_dd, 2)
        }
