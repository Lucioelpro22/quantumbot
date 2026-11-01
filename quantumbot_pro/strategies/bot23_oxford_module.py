"""
strategies/bot23_oxford_module.py — Módulo de Estrategia Oxford Multi-TF 1H/15m (Bot 23)
Combina el sesgo institucional de 1H con retests de alta precisión en 15m.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from strategies.base_strategy import BaseStrategyModule
from core.models import StrategySignal, Direction


class Bot23OxfordModule(BaseStrategyModule):
    def __init__(self):
        super().__init__(name="Bot23_Oxford_MultiTF")

    def generate_signal(self, yf_symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        df1h  = data.get('1h')
        df15m = data.get('15m')
        if df1h is None or df15m is None or len(df1h) < 30 or len(df15m) < 30:
            return None

        # 1H Trend
        c1h = df1h['Close']
        e9_1h  = c1h.ewm(span=9).mean()
        e21_1h = c1h.ewm(span=21).mean()

        # 15m Retest
        c15 = df15m['Close']
        delta = c15.diff()
        gain  = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs    = gain / (loss + 1e-8)
        rsi15 = 100 - (100 / (1 + rs))

        high = df15m['High']
        low  = df15m['Low']
        tr = pd.concat([(high - low), (high - c15.shift(1)).abs(), (low - c15.shift(1)).abs()], axis=1).max(axis=1)
        atr15 = tr.rolling(14).mean()

        i = -2
        price = float(c15.iloc[i])
        atr_v = float(atr15.iloc[i]) if not pd.isna(atr15.iloc[i]) else price * 0.008
        r15_v = float(rsi15.iloc[i])

        e9_v  = float(e9_1h.iloc[-2])
        e21_v = float(e21_1h.iloc[-2])

        # 1H Trend Alcista + 15m Retest
        if e9_v > e21_v and 40.0 <= r15_v <= 65.0:
            return StrategySignal(
                module_name=self.name, symbol=yf_symbol, direction=Direction.LONG,
                strength=0.90, timeframe="1H+15M", price=price, atr=atr_v,
                description=f"Oxford 1H+15M LONG (1H Bull + 15m RSI={r15_v:.1f})",
                metadata={"rsi15": r15_v}
            )

        # 1H Trend Bajista + 15m Retest
        elif e9_v < e21_v and 35.0 <= r15_v <= 60.0:
            return StrategySignal(
                module_name=self.name, symbol=yf_symbol, direction=Direction.SHORT,
                strength=0.90, timeframe="1H+15M", price=price, atr=atr_v,
                description=f"Oxford 1H+15M SHORT (1H Bear + 15m RSI={r15_v:.1f})",
                metadata={"rsi15": r15_v}
            )

        return None
