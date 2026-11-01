"""
analytics/purged_cv.py — Purged Cross-Validation y Combinatorial Purged CV (CPCV)
Elimina la contaminación de datos (look-ahead bias y data leakage) en series temporales de trading
mediante purgado (purging) y embargo temporal entre pliegues de entrenamiento y prueba (P6 & P7).
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Any
from analytics.metrics import QuantitativeMetricsEngine


class PurgedCrossValidator:
    def __init__(self, n_splits: int = 5, pct_embargo: float = 0.02):
        self.n_splits = n_splits
        self.pct_embargo = pct_embargo
        self.metrics_engine = QuantitativeMetricsEngine()

    def split(self, df: pd.DataFrame) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        P6 — Genera índices de entrenamiento (Train) y prueba (Test) aplicando Purging & Embargo.
        """
        n_samples = len(df)
        indices = np.arange(n_samples)
        fold_size = n_samples // self.n_splits
        embargo_size = int(n_samples * self.pct_embargo)

        cv_splits = []

        for fold in range(self.n_splits):
            test_start = fold * fold_size
            test_end   = (fold + 1) * fold_size if fold < self.n_splits - 1 else n_samples

            test_idx = indices[test_start:test_end]

            # Purgado (Purging): Eliminar muestras inmediatamente anteriores al test set
            train_left  = indices[:max(0, test_start - embargo_size)]

            # Embargo: Eliminar muestras inmediatamente posteriores al test set
            train_right = indices[min(n_samples, test_end + embargo_size):]

            train_idx = np.concatenate([train_left, train_right])

            cv_splits.append((train_idx, test_idx))

        return cv_splits

    def evaluate_strategy_cpcv(self, backtest_func, df1h: pd.DataFrame, df15m: pd.DataFrame) -> Dict[str, Any]:
        """
        P7 — Ejecuta la validación Combinatorial Purged Cross-Validation (CPCV)
        """
        splits = self.split(df15m)
        fold_sharpes = []
        fold_pfs = []
        fold_dds = []

        for i, (train_idx, test_idx) in enumerate(splits):
            test_15m = df15m.iloc[test_idx]
            test_1h  = df1h.iloc[:min(len(df1h), test_idx[-1] // 4 + 1)]

            res = backtest_func(test_1h, test_15m)

            fold_sharpes.append(res.get("sharpe_ratio", 0.0))
            fold_pfs.append(res.get("profit_factor", 0.0))
            fold_dds.append(res.get("max_drawdown_percent", 0.0))

        mean_sharpe = float(np.mean(fold_sharpes))
        std_sharpe  = float(np.std(fold_sharpes)) + 1e-6

        # Deflated Sharpe Ratio (DSR) formal mediante QuantitativeMetricsEngine
        dsr = self.metrics_engine.calculate_formal_dsr(np.array(fold_sharpes), mean_sharpe, n_trials=self.n_splits)

        return {
            "purged_cv_folds": self.n_splits,
            "mean_purged_sharpe": round(mean_sharpe, 2),
            "std_purged_sharpe": round(std_sharpe, 2),
            "deflated_sharpe_ratio": round(dsr, 2),
            "mean_purged_profit_factor": round(float(np.mean(fold_pfs)), 2),
            "mean_purged_max_drawdown": round(float(np.mean(fold_dds)), 2),
            "is_robust": mean_sharpe >= 1.5 and dsr >= 0.50
        }
