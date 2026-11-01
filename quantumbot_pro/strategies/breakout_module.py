"""
strategies/breakout_module.py — Módulo Cuantitativo de Ruptura de Volatilidad (Breakout)
Detecta rupturas institucionales de rangos Donchian de 20 períodos confirmadas por expansión de volumen.
"""

import pandas as pd
import numpy as np
from core.models import Direction, StrategySignal
from strategies.base_strategy import BaseStrategyModule


class BreakoutModule(BaseStrategyModule):
    def __init__(self, name: str = "Volatility_Breakout_Donchian"):
        super().__init__(name)

    def generate_signal(self, symbol: str, data: dict) -> StrategySignal:
        df15m = data.get('15m')
        if df15m is None or len(df15m) < 30:
            return None

        close  = df15m['Close']
        high   = df15m['High']
        low    = df15m['Low']
        volume = df15m['Volume']

        # 1. Canales Donchian de 20 períodos
        donchian_high = high.shift(1).rolling(20).max()
        donchian_low  = low.shift(1).rolling(20).min()

        # 2. Volumen Promedio
        vol_sma20 = volume.rolling(20).mean()

        curr_close = close.iloc[-1]
        curr_vol   = volume.iloc[-1]
        mean_vol   = vol_sma20.iloc[-1]
        dh_val     = donchian_high.iloc[-1]
        dl_val     = donchian_low.iloc[-1]

        tr = np.maximum(high - low, np.maximum((high - close.shift()).abs(), (low - close.shift()).abs()))
        atr = float(tr.rolling(14).mean().iloc[-1])

        # Ruptura Alcista con Volumen
        if curr_close > dh_val and curr_vol > mean_vol * 1.4:
            vol_ratio = curr_vol / (mean_vol + 1e-8)
            confidence = min(95.0, 75.0 + (vol_ratio - 1.0) * 10.0)
            return StrategySignal(
                module_name=self.name, symbol=symbol, direction=Direction.LONG,
                strength=0.90, confidence=confidence, timeframe="15m",
                price=curr_close, atr=atr,
                description=f"Ruptura Alcista Donchian (Volumen: {vol_ratio:.1f}x Promedio)"
            )

        # Ruptura Bajista con Volumen
        if curr_close < dl_val and curr_vol > mean_vol * 1.4:
            vol_ratio = curr_vol / (mean_vol + 1e-8)
            confidence = min(95.0, 75.0 + (vol_ratio - 1.0) * 10.0)
            return StrategySignal(
                module_name=self.name, symbol=symbol, direction=Direction.SHORT,
                strength=0.90, confidence=confidence, timeframe="15m",
                price=curr_close, atr=atr,
                description=f"Ruptura Bajista Donchian (Volumen: {vol_ratio:.1f}x Promedio)"
            )

        return None
