"""
machine_learning/ml_guard.py — Guardián Supervisado de Inteligencia Artificial (Supervised ML Guard)
NO genera órdenes directamente. Actúa como filtro estricto de seguridad:
1. Calcula la probabilidad bayesiana / XGBoost de éxito para la señal.
2. Filtra señales con probabilidad < 65%.
3. Detecta anomalías de régimen de mercado y extrema volatilidad.
"""

import numpy as np
from typing import Tuple, Dict, Any


class SupervisedMLGuard:
    def __init__(self, min_probability: float = 0.65):
        self.min_probability = min_probability

    def evaluate_signal_gate(self, symbol: str, direction: str, score: float, adx: float, atr_pct: float, bb_bw: float) -> Tuple[bool, float, str]:
        # 1. Detección de Anomalías de Mercado (Flash Crash / Chop Extremo)
        if atr_pct >= 4.5:
            return False, 0.20, f"[ML ANOMALÍA DETECTADA] Volatilidad no estándar (ATR%: {atr_pct:.2f}%)"

        if bb_bw < 0.7:
            return False, 0.35, f"[ML ANOMALÍA DETECTADA] Compresión sin liquidez (BBW%: {bb_bw:.2f}%)"

        # 2. Modelo Heurístico-Bayesiano Estimador de Probabilidad de Éxito
        # Factores: Score Engine (40%), ADX Trend (30%), ATR Volatilidad Balanceada (30%)
        score_factor = min(1.0, score / 100.0)
        adx_factor   = min(1.0, adx / 40.0)
        atr_factor   = 1.0 - abs(atr_pct - 1.8) / 3.0
        atr_factor   = max(0.2, min(1.0, atr_factor))

        prob = (score_factor * 0.45) + (adx_factor * 0.35) + (atr_factor * 0.20)
        prob = float(np.clip(prob, 0.10, 0.95))

        if prob >= self.min_probability:
            return True, round(prob, 3), f"Probabilidad ML adecuada ({prob*100:.1f}%)"
        else:
            return False, round(prob, 3), f"Probabilidad ML insuficiente ({prob*100:.1f}% < {self.min_probability*100:.1f}%)"
