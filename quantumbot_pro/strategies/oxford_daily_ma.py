"""Adaptación fiel del modelo Oxford M4U2: media móvil diaria long/cash."""
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd

from core.models import Direction, StrategySignal
from strategies.base_strategy import BaseStrategyModule


@dataclass(frozen=True)
class OxfordBacktestResult:
    symbol: str
    observations: int
    trades: int
    total_return_pct: float
    buy_hold_return_pct: float
    annualized_return_pct: float
    annualized_volatility_pct: float
    sharpe: float
    max_drawdown_pct: float
    profit_factor: float


def build_oxford_series(close: pd.Series, ma_days: int = 5,
                        round_trip_cost_bps: float = 12.0) -> pd.DataFrame:
    if ma_days < 2:
        raise ValueError("ma_days debe ser al menos 2")
    close = pd.to_numeric(close, errors="coerce").dropna().astype(float)
    frame = pd.DataFrame({"close": close})
    frame["return"] = frame["close"].pct_change()
    frame["ma"] = frame["close"].rolling(ma_days).mean()
    frame["signal"] = (frame["close"] > frame["ma"]).astype(int)
    frame["position"] = frame["signal"].shift(1).fillna(0)  # sin look-ahead
    frame["turnover"] = frame["position"].diff().abs().fillna(frame["position"])
    cost_per_side = round_trip_cost_bps / 20_000.0
    frame["strategy_return"] = frame["position"] * frame["return"] - frame["turnover"] * cost_per_side
    frame["buy_hold_equity"] = (1.0 + frame["return"].fillna(0)).cumprod()
    frame["strategy_equity"] = (1.0 + frame["strategy_return"].fillna(0)).cumprod()
    return frame.dropna(subset=["ma"])


def evaluate_oxford(close: pd.Series, symbol: str, ma_days: int = 5,
                    round_trip_cost_bps: float = 12.0) -> OxfordBacktestResult:
    frame = build_oxford_series(close, ma_days, round_trip_cost_bps)
    returns = frame["strategy_return"].dropna()
    if len(returns) < 30:
        raise ValueError("Se requieren al menos 30 observaciones válidas")
    years = len(returns) / 365.0
    total = float(frame["strategy_equity"].iloc[-1] / frame["strategy_equity"].iloc[0] - 1)
    buy_hold = float(frame["buy_hold_equity"].iloc[-1] / frame["buy_hold_equity"].iloc[0] - 1)
    annualized = (1.0 + total) ** (1.0 / years) - 1.0 if total > -1 and years > 0 else -1.0
    volatility = float(returns.std(ddof=1) * np.sqrt(365))
    sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(365)) if returns.std(ddof=1) > 0 else 0.0
    equity = frame["strategy_equity"]
    drawdown = equity / equity.cummax() - 1.0
    wins, losses = returns[returns > 0].sum(), abs(returns[returns < 0].sum())
    return OxfordBacktestResult(
        symbol=symbol, observations=len(returns), trades=int(frame["turnover"].sum() / 2),
        total_return_pct=round(total * 100, 2), buy_hold_return_pct=round(buy_hold * 100, 2),
        annualized_return_pct=round(annualized * 100, 2),
        annualized_volatility_pct=round(volatility * 100, 2), sharpe=round(sharpe, 3),
        max_drawdown_pct=round(abs(float(drawdown.min())) * 100, 2),
        profit_factor=round(float(wins / losses) if losses else 999.0, 3),
    )


class OxfordDailyMAModule(BaseStrategyModule):
    def __init__(self, ma_days: int = 5):
        super().__init__(name="Oxford_Daily_MA_LongCash")
        self.ma_days = ma_days

    def generate_signal(self, yf_symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        if yf_symbol not in ("BTC-USD", "ETH-USD"):
            return None
        daily = data.get("1d")
        if daily is None or len(daily) < self.ma_days + 2:
            return None
        close = daily["Close"]
        ma = close.rolling(self.ma_days).mean()
        i = -2  # última vela diaria cerrada
        price, ma_value = float(close.iloc[i]), float(ma.iloc[i])
        if np.isnan(ma_value) or price <= ma_value:
            return None  # cash; el modelo fuente no abre shorts
        distance = (price / ma_value - 1.0) * 100.0
        return StrategySignal(
            module_name=self.name, symbol=yf_symbol, direction=Direction.LONG,
            strength=min(1.0, 0.65 + max(0.0, distance) / 20.0), confidence=70.0,
            timeframe="1D", price=price, atr=0.0,
            description=f"Oxford M4U2 LONG: cierre {distance:.2f}% sobre SMA({self.ma_days})",
            metadata={"ma_days": self.ma_days, "ma": ma_value, "distance_pct": distance},
        )
