"""
strategies/meta_strategy.py — Meta-Estrategia Meta-Strategy Ensemble Engine de QuantumBot Pro v3.0
Consolida las señales de los 9 módulos especializados (incluyendo Oracle Fibonacci DCA & BlackEaglesCap Wyckoff PDI),
evalúa sus niveles de confianza (0-100), aplica la matriz de pesos dinámicos y emite la decisión final.
"""

from typing import List, Dict, Any
from core.models import Direction, StrategySignal, MarketRegimeState, ScoreBreakdown


class MetaStrategyEnsemble:
    def __init__(self, weights: Dict[str, float] = None, min_execution_score: float = 80.0):
        self.min_execution_score = min_execution_score
        self.default_weights = {
            "Oracle_Fibonacci_DCA_Engine": 0.20,
            "BlackEaglesCap_Wyckoff_PDI": 0.18,
            "Bot23_Oxford_MultiTF": 0.18,
            "Bot22_FVG_Fibonacci": 0.12,
            "SMC_OrderBlock_Liquidity": 0.12,
            "VWAP_CVD_Volume": 0.08,
            "MeanReversion_RSI_Bollinger": 0.05,
            "Volatility_Breakout_Donchian": 0.04,
            "Keltner_Volatility_Squeeze": 0.03
        }
        self.weights = weights if weights else self.default_weights

    def update_weights(self, new_weights: Dict[str, float]):
        total = sum(new_weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in new_weights.items()}

    def evaluate_ensemble(self, symbol: str, signals: List[StrategySignal], regime: MarketRegimeState) -> ScoreBreakdown:
        if not regime.is_tradable:
            return ScoreBreakdown(
                symbol=symbol, direction=Direction.NEUTRAL, total_score=0.0, is_approved=False
            )

        long_score  = 0.0
        short_score = 0.0

        for sig in signals:
            mod_weight = self.weights.get(sig.module_name, 0.10)
            weighted_val = mod_weight * (sig.confidence / 100.0) * sig.strength * 100.0

            if sig.direction == Direction.LONG:
                long_score += weighted_val
            elif sig.direction == Direction.SHORT:
                short_score += weighted_val

        # Bonificación por Régimen de Mercado (+15 puntos)
        if regime.regime.value == "BULLISH_TREND":
            long_score += 15.0
        elif regime.regime.value == "BEARISH_TREND":
            short_score += 15.0
        elif regime.regime.value == "VOLATILITY_EXPANSION":
            long_score += 8.0
            short_score += 8.0

        target_direction = Direction.NEUTRAL
        final_score = 0.0

        if long_score >= short_score and long_score > 0:
            target_direction = Direction.LONG
            final_score = min(100.0, long_score)
        elif short_score > long_score:
            target_direction = Direction.SHORT
            final_score = min(100.0, short_score)

        is_approved = final_score >= self.min_execution_score and target_direction != Direction.NEUTRAL

        return ScoreBreakdown(
            symbol=symbol, direction=target_direction,
            total_score=round(final_score, 1),
            is_approved=is_approved
        )
