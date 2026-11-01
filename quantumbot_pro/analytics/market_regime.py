"""
analytics/market_regime.py — Motor Clasificador de 7 Regímenes de Mercado (Quantum Engine)
Analiza la estructura de mercado utilizando ADX, ATR%, Ancho de Banda de Bollinger (BBW)
y Canales de Keltner para identificar 7 regímenes dinámicos.
"""

import pandas as pd
import numpy as np
from core.models import RegimeType, MarketRegimeState


class MarketRegimeDetector:
    def __init__(self, adx_period: int = 14, bb_period: int = 20, bb_std: float = 2.0):
        self.adx_period = adx_period
        self.bb_period = bb_period
        self.bb_std = bb_std

    def _calculate_adx(self, df: pd.DataFrame) -> float:
        if len(df) < self.adx_period + 1:
            return 20.0
        high = df['High']
        low = df['Low']
        close = df['Close']

        plus_dm = high.diff()
        minus_dm = low.diff().abs()
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = np.maximum(tr1, np.maximum(tr2, tr3))

        tr_smooth = pd.Series(tr).rolling(self.adx_period).sum()
        plus_di = 100 * (pd.Series(plus_dm).rolling(self.adx_period).sum() / tr_smooth)
        minus_di = 100 * (pd.Series(minus_dm).rolling(self.adx_period).sum() / tr_smooth)

        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-8)
        adx = dx.rolling(self.adx_period).mean().iloc[-1]
        return float(adx) if not np.isnan(adx) else 20.0

    def analyze_regime(self, symbol: str, df1h: pd.DataFrame) -> MarketRegimeState:
        if df1h is None or len(df1h) < 30:
            return MarketRegimeState(
                symbol=symbol, regime=RegimeType.SIDEWAYS_CHOP,
                adx_value=15.0, atr_percent=1.0, bb_bandwidth=1.0,
                is_tradable=False, reason="Insuficientes datos de velas 1H"
            )

        close = df1h['Close']
        high  = df1h['High']
        low   = df1h['Low']

        # 1. Medir ADX (Fuerza de la tendencia)
        adx_val = self._calculate_adx(df1h)

        # 2. Medir ATR % (Volatilidad Normalizada)
        tr = np.maximum(high - low, np.maximum((high - close.shift()).abs(), (low - close.shift()).abs()))
        atr = tr.rolling(14).mean().iloc[-1]
        last_close = close.iloc[-1]
        atr_pct = (atr / last_close) * 100.0 if last_close > 0 else 1.0

        # 3. Medir Bollinger Bandwidth (BBW %)
        sma20 = close.rolling(self.bb_period).mean()
        std20 = close.rolling(self.bb_period).std()
        upper_bb = sma20 + (std20 * self.bb_std)
        lower_bb = sma20 - (std20 * self.bb_std)
        bb_bw = ((upper_bb - lower_bb) / sma20) * 100.0
        current_bw = float(bb_bw.iloc[-1]) if not np.isnan(bb_bw.iloc[-1]) else 1.0
        prev_bw = float(bb_bw.iloc[-5]) if len(bb_bw) >= 5 and not np.isnan(bb_bw.iloc[-5]) else current_bw

        # 4. Tendencia EMA 20 vs EMA 50
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]

        # Lógica de Clasificación de 7 Regímenes
        is_tradable = True
        reason = "Condiciones óptimas de mercado"

        if atr_pct >= 4.5:
            regime = RegimeType.HIGH_VOLATILITY
            is_tradable = False
            reason = f"Volatilidad extrema detectada (ATR: {atr_pct:.2f}%)"
        elif atr_pct <= 0.6:
            regime = RegimeType.LOW_VOLATILITY
            is_tradable = False
            reason = f"Baja volatilidad / Mercado inactivo (ATR: {atr_pct:.2f}%)"
        elif current_bw > prev_bw * 1.5:
            regime = RegimeType.VOLATILITY_EXPANSION
            reason = "Expansión de volatilidad en curso"
        elif current_bw < prev_bw * 0.6:
            regime = RegimeType.VOLATILITY_CONTRACTION
            reason = "Compresión de volatilidad (Squeeze)"
        elif adx_val < 18.0 or current_bw < 0.8:
            regime = RegimeType.SIDEWAYS_CHOP
            is_tradable = False
            reason = f"Mercado lateral sin tendencia (ADX: {adx_val:.1f}, BBW: {current_bw:.2f}%)"
        elif ema20 > ema50:
            regime = RegimeType.BULLISH_TREND
            reason = f"Tendencia alcista confirmada (ADX: {adx_val:.1f})"
        else:
            regime = RegimeType.BEARISH_TREND
            reason = f"Tendencia bajista confirmada (ADX: {adx_val:.1f})"

        return MarketRegimeState(
            symbol=symbol, regime=regime, adx_value=round(adx_val, 2),
            atr_percent=round(atr_pct, 2), bb_bandwidth=round(current_bw, 2),
            is_tradable=is_tradable, reason=reason
        )
