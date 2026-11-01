"""
analytics/score_engine.py — Motor de Puntuación Cuantitativo Quantum (Score 0 - 100)
Consolida confluencias multi-módulo y genera un puntaje de decisión estricto.
Solo autoriza ejecuciones si Total Score >= 80.
"""

from typing import List, Dict, Optional
import pandas as pd

from core.models import (
    StrategySignal, MarketRegimeState, ScoreBreakdown, Direction, RegimeType
)


class QuantumScoreEngine:
    def __init__(self, min_execution_score: float = 80.0):
        self.min_execution_score = min_execution_score

    def evaluate_signals(
        self,
        symbol: str,
        direction: Direction,
        signals: List[StrategySignal],
        regime: MarketRegimeState,
        data: Dict[str, pd.DataFrame]
    ) -> ScoreBreakdown:
        if direction == Direction.NEUTRAL or not regime.is_tradable:
            return ScoreBreakdown(
                symbol=symbol, direction=direction, total_score=0.0,
                is_approved=False, rejection_reason=f"Régimen no operable: {regime.reason}"
            )

        macro_score = 0.0
        smc_score = 0.0
        fvg_score = 0.0
        momentum_score = 0.0
        volume_score = 0.0
        orderbook_score = 0.0
        regime_score = 0.0

        # 1. Régimen de Mercado (10 pts)
        if (direction == Direction.LONG and regime.regime == RegimeType.BULLISH_TREND) or \
           (direction == Direction.SHORT and regime.regime == RegimeType.BEARISH_TREND):
            regime_score = 10.0

        # 2. Evaluación de Módulos de Señal
        for sig in signals:
            if sig.direction == direction:
                if "Oxford" in sig.module_name:
                    macro_score = min(20.0, macro_score + 20.0 * sig.strength)
                elif "FVG" in sig.module_name:
                    fvg_score = min(15.0, fvg_score + 15.0 * sig.strength)
                elif "SMC" in sig.module_name:
                    smc_score = min(15.0, smc_score + 15.0 * sig.strength)
                elif "VWAP" in sig.module_name:
                    volume_score = min(15.0, volume_score + 15.0 * sig.strength)

        # 3. Momentum RSI/MACD adicional (15 pts max)
        df15m = data.get('15m')
        if df15m is not None and len(df15m) >= 20:
            c15 = df15m['Close']
            ema5 = c15.ewm(span=5).mean()
            ema13 = c15.ewm(span=13).mean()
            if (direction == Direction.LONG and float(ema5.iloc[-2]) > float(ema13.iloc[-2])) or \
               (direction == Direction.SHORT and float(ema5.iloc[-2]) < float(ema13.iloc[-2])):
                momentum_score = 15.0

        # 4. Orderbook Liquidity Base Score (10 pts)
        orderbook_score = 8.0

        total_score = (
            macro_score + smc_score + fvg_score +
            momentum_score + volume_score + orderbook_score + regime_score
        )

        is_approved = total_score >= self.min_execution_score
        rejection_reason = None if is_approved else f"Score insuficiente: {total_score:.1f} < {self.min_execution_score:.1f}"

        return ScoreBreakdown(
            symbol=symbol, direction=direction,
            macro_trend_score=macro_score, smc_orderblock_score=smc_score,
            fair_value_gap_score=fvg_score, momentum_score=momentum_score,
            volume_vwap_score=volume_score, orderbook_score=orderbook_score,
            market_regime_score=regime_score, total_score=total_score,
            is_approved=is_approved, rejection_reason=rejection_reason
        )
