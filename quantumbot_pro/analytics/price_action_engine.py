"""
analytics/price_action_engine.py — Motor de Confirmación de Acción del Precio (Price Action Engine)
Evalúa patrones de Velas Japonesas y Estructura de Mercado en 5m/15m (sobre velas cerradas confirmadas, sin repintado):
1. Pinbar / Rejección de Mecha (Wick Rejection >= 55% del rango total).
2. Vela Envolvente (Engulfing Candle - cuerpo envuelve completamente la vela previa).
3. Vela Elefante / Momentum Candle (cuerpo grande con volumen superior al promedio).
4. CHoCH / BMS (Change of Character / Ruptura de Micro-Estructura en 5m/15m).
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple


class PriceActionConfirmationEngine:
    def __init__(self, min_wick_ratio: float = 0.55):
        self.min_wick_ratio = min_wick_ratio

    def evaluate_price_action(self, df_15m: pd.DataFrame, direction: str) -> Tuple[bool, str, float]:
        """
        Evalúa si la reacción del precio en velas CERRADAS de 15m/5m confirma la entrada.
        Retorna: (is_confirmed: bool, pattern_detected: str, confirmation_score: float)
        """
        if df_15m is None or len(df_15m) < 6:
            return False, "Insuficientes velas para evaluar Acción del Precio", 0.0

        # PREVENCIÓN DE LOOK-AHEAD BIAS & REPINTADO:
        # Se evalúan barras confirmadas/cerradas (iloc[-2] es la última vela CERRADA, iloc[-3] la previa)
        closed_df = df_15m.iloc[:-1]

        last_closed = closed_df.iloc[-1]
        prev_closed = closed_df.iloc[-2]

        open_c  = float(last_closed['Open'])
        high_c  = float(last_closed['High'])
        low_c   = float(last_closed['Low'])
        close_c = float(last_closed['Close'])
        vol_c   = float(last_closed['Volume']) if 'Volume' in last_closed else 1.0

        p_open  = float(prev_closed['Open'])
        p_close = float(prev_closed['Close'])

        rng = max(0.0001, high_c - low_c)
        body = abs(close_c - open_c)
        body_pct = body / rng

        avg_vol = closed_df['Volume'].iloc[-10:].mean() if 'Volume' in closed_df else vol_c
        vol_ratio = (vol_c / avg_vol) if avg_vol > 0 else 1.0

        # ── 1. CONFIRMACIÓN PARA COMPRAS (LONG) ──────────────────────────────────
        if direction.upper() in ("LONG", "BUY", "1"):
            # A. Rejección de Mecha Inferior (Pinbar Alcista / Hammer)
            lower_wick = min(open_c, close_c) - low_c
            lower_wick_ratio = lower_wick / rng
            if lower_wick_ratio >= self.min_wick_ratio and close_c >= open_c:
                score = min(100.0, 70.0 + lower_wick_ratio * 40.0)
                return True, f"Pinbar Alcista (Mecha inferior {lower_wick_ratio*100:.1f}%)", round(score, 1)

            # B. Vela Envolvente Alcista (Bullish Engulfing)
            is_prev_bearish = p_close < p_open
            if is_prev_bearish and close_c > p_open and open_c <= p_close:
                score = min(100.0, 80.0 + (vol_ratio * 10.0))
                return True, f"Vela Envolvente Alcista (Engulfing + Vol x{vol_ratio:.1f})", round(score, 1)

            # C. Vela Elefante / Momentum Alcista
            if close_c > open_c and body_pct >= 0.70 and vol_ratio >= 1.3:
                score = min(100.0, 75.0 + vol_ratio * 12.0)
                return True, f"Vela Elefante / Momentum Alcista (Cuerpo {body_pct*100:.0f}% + Vol x{vol_ratio:.1f})", round(score, 1)

            # D. Micro-CHoCH Alcista (Ruptura de máximo anterior)
            prev_high = float(closed_df['High'].iloc[-3:-1].max())
            if close_c > prev_high:
                return True, f"Micro-CHoCH Alcista (Quiebre de máximo previo ${prev_high:.2f})", 85.0

        # ── 2. CONFIRMACIÓN PARA VENTAS (SHORT) ──────────────────────────────────
        elif direction.upper() in ("SHORT", "SELL", "-1"):
            # A. Rejección de Mecha Superior (Pinbar Bajista / Shooting Star)
            upper_wick = high_c - max(open_c, close_c)
            upper_wick_ratio = upper_wick / rng
            if upper_wick_ratio >= self.min_wick_ratio and close_c <= open_c:
                score = min(100.0, 70.0 + upper_wick_ratio * 40.0)
                return True, f"Pinbar Bajista (Mecha superior {upper_wick_ratio*100:.1f}%)", round(score, 1)

            # B. Vela Envolvente Bajista (Bearish Engulfing)
            is_prev_bullish = p_close > p_open
            if is_prev_bullish and close_c < p_open and open_c >= p_close:
                score = min(100.0, 80.0 + (vol_ratio * 10.0))
                return True, f"Vela Envolvente Bajista (Engulfing + Vol x{vol_ratio:.1f})", round(score, 1)

            # C. Vela Elefante / Momentum Bajista
            if close_c < open_c and body_pct >= 0.70 and vol_ratio >= 1.3:
                score = min(100.0, 75.0 + vol_ratio * 12.0)
                return True, f"Vela Elefante / Momentum Bajista (Cuerpo {body_pct*100:.0f}% + Vol x{vol_ratio:.1f})", round(score, 1)

            # D. Micro-CHoCH Bajista (Ruptura de mínimo anterior)
            prev_low = float(closed_df['Low'].iloc[-3:-1].min())
            if close_c < prev_low:
                return True, f"Micro-CHoCH Bajista (Quiebre de mínimo previo ${prev_low:.2f})", 85.0

        return False, "Sin patrón de Acción del Precio suficiente en la reacción del nivel", 0.0
