"""
strategies/bot22_fvg_module.py — Módulo de Estrategia Fair Value Gaps (FVG) & Fibonacci (Bot 22)
Detecta brechas de liquidez institucional (FVG) y retrocesos en la estructura.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from strategies.base_strategy import BaseStrategyModule
from core.models import StrategySignal, Direction


class Bot22FVGModule(BaseStrategyModule):
    def __init__(self):
        super().__init__(name="Bot22_FVG_Fibonacci")

    def generate_signal(self, yf_symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        df15m = data.get('15m')
        if df15m is None or len(df15m) < 30:
            return None

        close = df15m['Close']
        high  = df15m['High']
        low   = df15m['Low']

        # ATR 14
        tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()

        i = -2
        price = float(close.iloc[i])
        atr_v = float(atr14.iloc[i]) if not pd.isna(atr14.iloc[i]) else price * 0.008

        # Bullish FVG: Low(i) > High(i-2)
        if low.iloc[i] > high.iloc[i-2]:
            gap = low.iloc[i] - high.iloc[i-2]
            return StrategySignal(
                module_name=self.name, symbol=yf_symbol, direction=Direction.LONG,
                strength=0.85, timeframe="15m", price=price, atr=atr_v,
                description=f"Bullish FVG (${gap:.2f})", metadata={"fvg_gap": gap}
            )

        # Bearish FVG: High(i) < Low(i-2)
        elif high.iloc[i] < low.iloc[i-2]:
            gap = low.iloc[i-2] - high.iloc[i]
            return StrategySignal(
                module_name=self.name, symbol=yf_symbol, direction=Direction.SHORT,
                strength=0.85, timeframe="15m", price=price, atr=atr_v,
                description=f"Bearish FVG (${gap:.2f})", metadata={"fvg_gap": gap}
            )

        return None
