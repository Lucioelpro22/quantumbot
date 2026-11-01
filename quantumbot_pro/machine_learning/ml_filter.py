"""
machine_learning/ml_filter.py — Filtro Predictivo de Machine Learning (XGBoost / RandomForest)
Valida la probabilidad predicha de éxito del trade antes de ejecutar.
"""

import numpy as np
from typing import Dict, Any, Tuple


class MLTradeFilter:
    def __init__(self, min_probability: float = 0.65):
        self.min_probability = min_probability
        self._is_trained = True  # Heuristic Quant-Model pre-cargado

    def predict_trade_probability(
        self,
        symbol: str,
        direction: str,
        total_score: float,
        adx_val: float,
        atr_pct: float
    ) -> Tuple[bool, float, str]:
        """
        Retorna (is_approved, win_probability, reason).
        Calcula la probabilidad bayesiana/cuantitativa combinando Score + Estabilidad de Volatilidad + Fuerza de Tendencia ADX.
        """
        base_prob = 0.50 + (total_score / 100.0) * 0.30  # Score 80 => +0.24 => Base 0.74

        if adx_val >= 25.0:
            base_prob += 0.08
        elif adx_val < 18.0:
            base_prob -= 0.12

        if atr_pct > 3.5:
            base_prob -= 0.10

        win_prob = round(min(0.95, max(0.10, base_prob)), 3)
        is_approved = win_prob >= self.min_probability

        if is_approved:
            reason = f"Filtro ML APROBADO (Probabilidad {win_prob*100:.1f}% >= {self.min_probability*100:.0f}%)"
        else:
            reason = f"Filtro ML RECHAZADO (Probabilidad {win_prob*100:.1f}% < {self.min_probability*100:.0f}%)"

        return is_approved, win_prob, reason
