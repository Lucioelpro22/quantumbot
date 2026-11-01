"""
core/models.py — Esquemas de Datos Pydantic v2 para QuantumBot Pro v2.0
Establece modelos estrictos con tipos de datos e inmutabilidad para live, backtest y ML.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class RegimeType(str, Enum):
    BULLISH_TREND = "BULLISH_TREND"
    BEARISH_TREND = "BEARISH_TREND"
    SIDEWAYS_CHOP = "SIDEWAYS_CHOP"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    VOLATILITY_CONTRACTION = "VOLATILITY_CONTRACTION"


class MarketRegimeState(BaseModel):
    symbol: str
    regime: RegimeType
    adx_value: float
    atr_percent: float
    bb_bandwidth: float
    is_tradable: bool
    reason: str


class StrategySignal(BaseModel):
    module_name: str
    symbol: str
    direction: Direction
    strength: float = Field(ge=0.0, le=1.0, description="Fuerza normalizada 0.0 - 1.0")
    confidence: float = Field(default=80.0, ge=0.0, le=100.0, description="Nivel de confianza 0 - 100")
    timeframe: str
    price: float
    atr: float
    description: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScoreBreakdown(BaseModel):
    symbol: str
    direction: Direction
    total_score: float = Field(ge=0.0, le=100.0)
    macro_score: float = 0.0
    smc_score: float = 0.0
    fvg_score: float = 0.0
    momentum_score: float = 0.0
    vwap_volume_score: float = 0.0
    mean_reversion_score: float = 0.0
    breakout_score: float = 0.0
    regime_score: float = 0.0
    is_approved: bool = False


class RiskDecision(BaseModel):
    symbol: str
    direction: Direction
    is_allowed: bool
    quantity: float
    stop_loss_price: float
    take_profit_price: float
    leverage: int = 20
    reason: str
    score: float
    ml_probability: float
    suggested_margin_usd: float


class ActivePosition(BaseModel):
    symbol: str
    position_side: Direction
    entry_price: float
    current_price: float
    quantity: float
    unrealized_pnl: float
    roi_percent: float
    leverage: int
    is_isolated: bool
