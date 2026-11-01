"""
strategies/volatility_module.py — Módulo Cuantitativo de Compresión y Explosión de Volatilidad (Keltner Squeeze)
Detecta compresión extrema dentro de Canales Keltner y explosión de impulso posterior.
"""

import pandas as pd
import numpy as np
from core.models import Direction, StrategySignal
from strategies.base_strategy import BaseStrategyModule


class VolatilityModule(BaseStrategyModule):
    def __init__(self, name: str = "Keltner_Volatility_Squeeze"):
        super().__init__(name)

    def generate_signal(self, symbol: str, data: dict) -> StrategySignal:
        df15m = data.get('15m')
        if df15m is None or len(df15m) < 30:
            return None

        close = df15m['Close']
        high  = df15m['High']
        low   = df15m['Low']

        # 1. Canales Keltner (EMA 20 + 1.5 ATR)
        ema20 = close.ewm(span=20).mean()
        tr = np.maximum(high - low, np.maximum((high - close.shift()).abs(), (low - close.shift()).abs()))
        atr14 = tr.rolling(14).mean()

        upper_keltner = ema20 + (1.5 * atr14)
        lower_keltner = ema20 - (1.5 * atr14)

        # 2. Bandas de Bollinger (20, 2.0)
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper_bb = sma20 + (2.0 * std20)
        lower_bb = sma20 - (2.0 * std20)

        # Squeeze = BB dentro de Keltner
        is_squeeze = (upper_bb.iloc[-2] < upper_keltner.iloc[-2]) and (lower_bb.iloc[-2] > lower_keltner.iloc[-2])
        is_release = (upper_bb.iloc[-1] > upper_keltner.iloc[-1]) or (lower_bb.iloc[-1] < lower_keltner.iloc[-1])

        curr_close = close.iloc[-1]
        curr_ema   = ema20.iloc[-1]
        atr_val    = float(atr14.iloc[-1])

        if is_squeeze or is_release:
            if curr_close > curr_ema and curr_close > upper_keltner.iloc[-1]:
                return StrategySignal(
                    module_name=self.name, symbol=symbol, direction=Direction.LONG,
                    strength=0.92, confidence=86.0, timeframe="15m",
                    price=curr_close, atr=atr_val,
                    description="Explosión de Volatilidad Alcista tras Compresión (Keltner Release)"
                )
            elif curr_close < curr_ema and curr_close < lower_keltner.iloc[-1]:
                return StrategySignal(
                    module_name=self.name, symbol=symbol, direction=Direction.SHORT,
                    strength=0.92, confidence=86.0, timeframe="15m",
                    price=curr_close, atr=atr_val,
                    description="Explosión de Volatilidad Bajista tras Compresión (Keltner Release)"
                )

        return None
