"""
strategies/smc_orderblock_module.py — Módulo de Estrategia Smart Money Concepts (SMC) & Order Blocks
Detecta bloques de órdenes institucionales (Order Blocks - OB) y barridos de liquidez (Liquidity Sweeps / BOS).
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from strategies.base_strategy import BaseStrategyModule
from core.models import StrategySignal, Direction


class SMCOrderBlockModule(BaseStrategyModule):
    def __init__(self):
        super().__init__(name="SMC_OrderBlock_Liquidity")

    def generate_signal(self, yf_symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        df15m = data.get('15m')
        if df15m is None or len(df15m) < 40:
            return None

        close = df15m['Close']
        high  = df15m['High']
        low   = df15m['Low']
        vol   = df15m['Volume']

        tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()

        i = -2
        price = float(close.iloc[i])
        atr_v = float(atr14.iloc[i]) if not pd.isna(atr14.iloc[i]) else price * 0.008

        # Bullish Order Block (OB): Vela bajista previa a un quiebre alcista con volumen expansivo
        ob_bullish = (close.iloc[i-3] < df15m['Open'].iloc[i-3]) and \
                     (close.iloc[i] > high.iloc[i-3]) and \
                     (vol.iloc[i] > 1.3 * vol.rolling(20).mean().iloc[i])

        # Bearish Order Block (OB): Vela alcista previa a un quiebre bajista con volumen expansivo
        ob_bearish = (close.iloc[i-3] > df15m['Open'].iloc[i-3]) and \
                     (close.iloc[i] < low.iloc[i-3]) and \
                     (vol.iloc[i] > 1.3 * vol.rolling(20).mean().iloc[i])

        if ob_bullish:
            return StrategySignal(
                module_name=self.name, symbol=yf_symbol, direction=Direction.LONG,
                strength=0.88, timeframe="15m", price=price, atr=atr_v,
                description="SMC Bullish OrderBlock & Liquidity Expansion",
                metadata={"ob_type": "Bullish"}
            )

        elif ob_bearish:
            return StrategySignal(
                module_name=self.name, symbol=yf_symbol, direction=Direction.SHORT,
                strength=0.88, timeframe="15m", price=price, atr=atr_v,
                description="SMC Bearish OrderBlock & Liquidity Expansion",
                metadata={"ob_type": "Bearish"}
            )

        return None
