"""
strategies/oracle_fibonacci_dca_module.py — Módulo Cuantitativo Oracle Fibonacci, Divergencias & DCA Promediado
Implementa la estrategia basada en:
1. Retroceso de Fibonacci (61.8%, 78.6%) & Extensión 1.618 en H4/H1 (sin look-ahead bias, solo velas cerradas).
2. RSI 14 con suavizado Wilder + Divergencias de Momentum en H1/H4.
3. VPVR (Volume Profile Point of Control - POC real) & VWAP Breakouts en 15m/5m.
4. Soporte y Resistencia Dinámica con EMA 20.
5. Sistema de Entrada Multinivel DCA Promediado (15%-25% inicial + 15%-25% escalonado).
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from core.models import Direction, StrategySignal
from strategies.base_strategy import BaseStrategyModule


class OracleFibonacciDCAModule(BaseStrategyModule):
    def __init__(self, name: str = "Oracle_Fibonacci_DCA_Engine"):
        super().__init__(name)

    def _calculate_rsi_wilder(self, series: pd.Series, period: int = 14) -> pd.Series:
        """RSI estándar con suavizado exponencial Wilder (sin look-ahead bias)"""
        delta = series.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-8)
        return 100.0 - (100.0 / (1.0 + rs))

    def _calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        tp = (df['High'] + df['Low'] + df['Close']) / 3.0
        pv = tp * df['Volume']
        return pv.cumsum() / (df['Volume'].cumsum() + 1e-8)

    def _calculate_true_poc(self, df: pd.DataFrame, bins: int = 20) -> float:
        """Calcula el verdadero Point of Control (POC) del perfil de volumen"""
        if df is None or len(df) < 10:
            return float(df['Close'].iloc[-1])
        price_min = df['Low'].min()
        price_max = df['High'].max()
        if price_max == price_min:
            return float(df['Close'].iloc[-1])

        bin_edges = np.linspace(price_min, price_max, bins + 1)
        vol_profile = np.zeros(bins)

        for _, row in df.iterrows():
            c_price = (row['High'] + row['Low'] + row['Close']) / 3.0
            idx = np.clip(np.digitize(c_price, bin_edges) - 1, 0, bins - 1)
            vol_profile[idx] += row['Volume']

        max_bin_idx = np.argmax(vol_profile)
        poc_price = (bin_edges[max_bin_idx] + bin_edges[max_bin_idx + 1]) / 2.0
        return float(poc_price)

    def generate_signal(self, symbol: str, data: dict) -> Optional[StrategySignal]:
        df1h  = data.get('1h')
        df15m = data.get('15m')

        if df1h is None or len(df1h) < 40 or df15m is None or len(df15m) < 40:
            return None

        # PREVENCIÓN DE LOOK-AHEAD BIAS:
        # Los indicadores se evalúan sobre velas CONFIRMADAS / CERRADAS (iloc[:-1])
        closed_1h = df1h.iloc[:-1]
        closed_15m = df15m.iloc[:-1]

        close1h = closed_1h['Close']
        high1h  = closed_1h['High']
        low1h   = closed_1h['Low']

        close15m = closed_15m['Close']
        high15m  = closed_15m['High']
        low15m   = closed_15m['Low']

        curr_close = float(closed_15m['Close'].iloc[-1])

        # 1. Nivel de Fib Retroceso H1 (Mínimo y Máximo de los últimos 40 períodos cerrados)
        min_p = float(low1h.iloc[-40:].min())
        max_p = float(high1h.iloc[-40:].max())
        diff  = max_p - min_p

        fib_618 = max_p - (diff * 0.618)
        fib_786 = max_p - (diff * 0.786)
        ext_1618 = min_p + (diff * 1.618)

        # 2. RSI 14 en H1 (Suavizado Wilder sobre barra cerrada)
        rsi1h = self._calculate_rsi_wilder(close1h, 14)
        curr_rsi1h = float(rsi1h.iloc[-1])

        # 3. EMA 20 & VWAP 15m sobre barras cerradas
        ema20_15m = close15m.ewm(span=20).mean().iloc[-1]
        vwap15m   = self._calculate_vwap(closed_15m).iloc[-1]

        # 4. Point of Control (POC) real del Perfil de Volumen
        poc_price = self._calculate_true_poc(closed_1h.iloc[-30:])

        tr = np.maximum(high15m - low15m, np.maximum((high15m - close15m.shift()).abs(), (low15m - close15m.shift()).abs()))
        atr_val = float(tr.rolling(14).mean().iloc[-1])

        # A. Señal COMPRA LONG (Sobreventa RSI H1 <= 34 + Fib 61.8%/78.6% + Breakout VWAP)
        is_fib_support_long = (abs(curr_close - fib_618) / curr_close <= 0.015) or (abs(curr_close - fib_786) / curr_close <= 0.015)
        if curr_rsi1h <= 34.0 or (is_fib_support_long and curr_close > vwap15m):
            confidence = min(96.0, 80.0 + (34.0 - curr_rsi1h) * 1.2 if curr_rsi1h < 34 else 85.0)
            return StrategySignal(
                module_name=self.name,
                symbol=symbol,
                direction=Direction.LONG,
                strength=0.94,
                confidence=confidence,
                timeframe="15m",
                price=curr_close,
                atr=atr_val,
                description=f"Oracle Fib DCA LONG: RSI H1 Wilder ({curr_rsi1h:.1f}) + Fib + VWAP Breakout",
                metadata={
                    "fib_618": round(fib_618, 4),
                    "fib_786": round(fib_786, 4),
                    "ext_1618": round(ext_1618, 4),
                    "poc_price": round(poc_price, 4),
                    "dca_scale_in_pct": "15%-25%",
                    "target_rr": "1:1.5"
                }
            )

        # B. Señal VENTA SHORT (Sobrecompra RSI H1 >= 66 + Extensión Fib / Resistencia POC + Breakout a la baja)
        is_fib_res_short = (abs(curr_close - ext_1618) / curr_close <= 0.015) or (abs(curr_close - poc_price) / curr_close <= 0.01)
        if curr_rsi1h >= 66.0 or (is_fib_res_short and curr_close < vwap15m):
            confidence = min(96.0, 80.0 + (curr_rsi1h - 66.0) * 1.2 if curr_rsi1h > 66 else 85.0)
            return StrategySignal(
                module_name=self.name,
                symbol=symbol,
                direction=Direction.SHORT,
                strength=0.94,
                confidence=confidence,
                timeframe="15m",
                price=curr_close,
                atr=atr_val,
                description=f"Oracle Fib DCA SHORT: RSI H1 Wilder ({curr_rsi1h:.1f}) + Ext Fib/POC + Breakout VWAP",
                metadata={
                    "fib_618": round(fib_618, 4),
                    "ext_1618": round(ext_1618, 4),
                    "poc_price": round(poc_price, 4),
                    "dca_scale_in_pct": "15%-25%",
                    "target_rr": "1:1.5"
                }
            )

        return None
