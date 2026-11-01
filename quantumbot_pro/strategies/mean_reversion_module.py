"""
strategies/mean_reversion_module.py — Módulo Cuantitativo de Reversión a la Media
Detecta desviaciones extremas de precio mediante Bandas de Bollinger (2.5 std) y RSI Extremo (<25 / >75).
"""

import pandas as pd
import numpy as np
from core.models import Direction, StrategySignal
from strategies.base_strategy import BaseStrategyModule


class MeanReversionModule(BaseStrategyModule):
    def __init__(self, name: str = "MeanReversion_RSI_Bollinger"):
        super().__init__(name)

    def generate_signal(self, symbol: str, data: dict) -> StrategySignal:
        df15m = data.get('15m')
        if df15m is None or len(df15m) < 30:
            return None

        close = df15m['Close']
        high  = df15m['High']
        low   = df15m['Low']

        # 1. Bandas de Bollinger 2.5 std
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper_bb = sma20 + (std20 * 2.5)
        lower_bb = sma20 - (std20 * 2.5)

        # 2. RSI 14
        delta = close.diff()
        gain  = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss  = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs    = gain / (loss + 1e-8)
        rsi   = 100 - (100 / (1 + rs))

        curr_close = close.iloc[-1]
        curr_rsi   = rsi.iloc[-1]
        curr_upper = upper_bb.iloc[-1]
        curr_lower = lower_bb.iloc[-1]

        # ATR
        tr = np.maximum(high - low, np.maximum((high - close.shift()).abs(), (low - close.shift()).abs()))
        atr = float(tr.rolling(14).mean().iloc[-1])

        # Señal LONG por sobreventa extrema
        if curr_close < curr_lower and curr_rsi < 28.0:
            confidence = min(95.0, 75.0 + (30.0 - curr_rsi) * 1.5)
            return StrategySignal(
                module_name=self.name, symbol=symbol, direction=Direction.LONG,
                strength=0.88, confidence=confidence, timeframe="15m",
                price=curr_close, atr=atr,
                description=f"Sobreventa Extrema Reversión a la Media (RSI: {curr_rsi:.1f}, BB Lower)"
            )

        # Señal SHORT por sobrecompra extrema
        if curr_close > curr_upper and curr_rsi > 72.0:
            confidence = min(95.0, 75.0 + (curr_rsi - 70.0) * 1.5)
            return StrategySignal(
                module_name=self.name, symbol=symbol, direction=Direction.SHORT,
                strength=0.88, confidence=confidence, timeframe="15m",
                price=curr_close, atr=atr,
                description=f"Sobrecompra Extrema Reversión a la Media (RSI: {curr_rsi:.1f}, BB Upper)"
            )

        return None
