"""
backtesting/walk_forward.py — Optimización Walk-Forward y Validación Fuera de Muestra (Out-of-Sample)
Divide el período histórico en múltiples ventanas móviles In-Sample (Entrenamiento 70%)
y Out-of-Sample (Prueba 30%) para garantizar que el bot no esté sobreajustado (overfitted).
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List
from backtesting.backtest_engine import QuantBacktestEngine


class WalkForwardOptimizer:
    def __init__(self, in_sample_pct: float = 0.70, n_windows: int = 5):
        self.in_sample_pct = in_sample_pct
        self.n_windows = n_windows
        self.engine = QuantBacktestEngine()

    def run_walk_forward(self, df1h: pd.DataFrame, df15m: pd.DataFrame, symbol: str = "BTC-USD") -> Dict[str, Any]:
        if df15m is None or len(df15m) < 400:
            return {"status": "ERROR", "reason": "Insuficientes datos para Walk-Forward (mínimo 400 velas 15m)"}

        window_size = len(df15m) // self.n_windows
        in_sample_metrics = []
        out_of_sample_metrics = []

        for w in range(self.n_windows):
            start_idx = w * window_size
            end_idx = min(len(df15m), start_idx + window_size)

            sub_15m = df15m.iloc[start_idx:end_idx]
            split_point = int(len(sub_15m) * self.in_sample_pct)

            in_sample_15m  = sub_15m.iloc[:split_point]
            out_sample_15m = sub_15m.iloc[split_point:]

            # Escalar velas 1H correspondientes
            in_sample_1h  = df1h.iloc[:min(len(df1h), (start_idx + split_point) // 4 + 1)]
            out_sample_1h = df1h.iloc[:min(len(df1h), end_idx // 4 + 1)]

            # 1. Backtest In-Sample
            is_res = self.engine.run_backtest(in_sample_1h, in_sample_15m, symbol)
            in_sample_metrics.append(is_res)

            # 2. Backtest Out-of-Sample (Validación real)
            oos_res = self.engine.run_backtest(out_sample_1h, out_sample_15m, symbol)
            out_of_sample_metrics.append(oos_res)

        avg_is_sharpe  = float(np.mean([m['sharpe_ratio'] for m in in_sample_metrics]))
        avg_oos_sharpe = float(np.mean([m['sharpe_ratio'] for m in out_of_sample_metrics]))
        avg_oos_pf     = float(np.mean([m['profit_factor'] for m in out_of_sample_metrics]))
        avg_oos_dd     = float(np.mean([m['max_drawdown_percent'] for m in out_of_sample_metrics]))

        # Ratio de Eficiencia Walk-Forward (OOS Sharpe / IS Sharpe)
        wfe_ratio = (avg_oos_sharpe / avg_is_sharpe) if avg_is_sharpe > 0 else 1.0

        is_passed = (wfe_ratio >= 0.60) and (avg_oos_pf >= 1.25) and (avg_oos_dd <= 20.0)

        return {
            "status": "PASSED" if is_passed else "FAILED",
            "walk_forward_efficiency_ratio": round(wfe_ratio, 2),
            "avg_in_sample_sharpe": round(avg_is_sharpe, 2),
            "avg_out_of_sample_sharpe": round(avg_oos_sharpe, 2),
            "avg_out_of_sample_profit_factor": round(avg_oos_pf, 2),
            "avg_out_of_sample_max_drawdown": round(avg_oos_dd, 2),
            "is_overfitted": wfe_ratio < 0.50,
            "windows_evaluated": self.n_windows
        }
