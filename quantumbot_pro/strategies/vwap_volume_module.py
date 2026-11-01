"""
strategies/vwap_volume_module.py — Módulo de Estrategia VWAP, CVD & Orderbook Volume Delta
Calcula la posición del precio respecto al VWAP y la aceleración de volumen acumulado (CVD).
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from strategies.base_strategy import BaseStrategyModule
from core.models import StrategySignal, Direction


class VWAPVolumeModule(BaseStrategyModule):
    def __init__(self):
        super().__init__(name="VWAP_Volume_Delta")

    def _calc_vwap(self, df: pd.DataFrame) -> pd.Series:
        tp = (df['High'] + df['Low'] + df['Close']) / 3.0
        vwap = (tp * df['Volume']).cumsum() / (df['Volume'].cumsum() + 1e-8)
        return vwap

    def generate_signal(self, yf_symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        df15m = data.get('15m')
        if df15m is None or len(df15m) < 30:
            return None

        close = df15m['Close']
        high  = df15m['High']
        low   = df15m['Low']
        vol   = df15m['Volume']

        vwap_ser = self._calc_vwap(df15m)
        tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()

        i = -2
        price    = float(close.iloc[i])
        vwap_val = float(vwap_ser.iloc[i])
        atr_v    = float(atr14.iloc[i]) if not pd.isna(atr14.iloc[i]) else price * 0.008

        vol_avg = float(vol.rolling(20).mean().iloc[i])
        curr_vol = float(vol.iloc[i])

        # Quiebre Alcista sobre VWAP con Volumen > 1.35x Promedio
        if price > vwap_val and float(close.iloc[i-1]) <= float(vwap_ser.iloc[i-1]) and curr_vol >= 1.35 * vol_avg:
            return StrategySignal(
                module_name=self.name, symbol=yf_symbol, direction=Direction.LONG,
                strength=0.82, timeframe="15m", price=price, atr=atr_v,
                description=f"VWAP Crossover LONG (${price:.2f} > VWAP ${vwap_val:.2f})",
                metadata={"vwap": vwap_val}
            )

        # Quiebre Bajista bajo VWAP con Volumen > 1.35x Promedio
        elif price < vwap_val and float(close.iloc[i-1]) >= float(vwap_ser.iloc[i-1]) and curr_vol >= 1.35 * vol_avg:
            return StrategySignal(
                module_name=self.name, symbol=yf_symbol, direction=Direction.SHORT,
                strength=0.82, timeframe="15m", price=price, atr=atr_v,
                description=f"VWAP Crossover SHORT (${price:.2f} < VWAP ${vwap_val:.2f})",
                metadata={"vwap": vwap_val}
            )

        return None
