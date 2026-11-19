"""Deterministic consensus accounting; scores are not calibrated probabilities.

One vote per registered module. Explicit shared evidence is counted once across
modules; absent provenance never constitutes proof of independent signals.
"""
import math
from collections import defaultdict

from core.models import Direction, StrategySignal, MarketRegimeState, ScoreBreakdown
from strategies.registry import DEFAULT_WEIGHTS, validate_weights


class MetaStrategyEnsemble:
    def __init__(self, weights=None, min_execution_score=80.0):
        if not math.isfinite(min_execution_score) or not 0 < min_execution_score <= 100:
            raise ValueError('Invalid execution threshold')
        self.min_execution_score = min_execution_score
        self.default_weights = dict(DEFAULT_WEIGHTS)
        self.weights = validate_weights(DEFAULT_WEIGHTS if weights is None else weights)

    def update_weights(self, new_weights):
        # Explicit bounded configuration, not renormalization of observed winners.
        self.weights = validate_weights(new_weights)

    def evaluate_ensemble(self, symbol: str, signals: list[StrategySignal],
                          regime: MarketRegimeState) -> ScoreBreakdown:
        def reject(reason):
            return ScoreBreakdown(symbol=symbol, direction=Direction.NEUTRAL,
                                  total_score=0.0, is_approved=False, rejection_reason=reason)
        if regime.symbol != symbol or not regime.is_tradable:
            return reject('REGIME_UNAVAILABLE_OR_NOT_TRADABLE')
        if not all(math.isfinite(v) for v in (regime.adx_value, regime.atr_percent, regime.bb_bandwidth)):
            return reject('INVALID_REGIME_METRICS')
        groups = defaultdict(list)
        ignored = set()
        for sig in signals:
            if sig.symbol != symbol or sig.module_name not in self.weights or self.weights[sig.module_name] == 0:
                ignored.add(sig.module_name)
                continue
            if (sig.direction not in (Direction.LONG, Direction.SHORT)
                    or not math.isfinite(sig.confidence) or not math.isfinite(sig.strength)
                    or not 0 <= sig.confidence <= 100 or not 0 <= sig.strength <= 1):
                ignored.add(sig.module_name)
                continue
            groups[sig.module_name].append(sig)
        votes = []
        for module, group in sorted(groups.items()):
            if len({sig.direction for sig in group}) != 1:
                ignored.add(module)
                continue
            # Multiple observations of one module cannot multiply its budget.
            sig = max(group, key=lambda s: (s.confidence * s.strength, s.timeframe,
                                           str(s.metadata.get('evidence_id', ''))))
            value = self.weights[module] * sig.confidence * sig.strength
            if value > 0:
                evidence = sig.metadata.get('evidence_id')
                if evidence is not None and (not isinstance(evidence, str) or not evidence):
                    ignored.add(module)
                    continue
                votes.append((module, sig.direction, value, evidence))
        evidence_groups = defaultdict(list)
        for module, direction, value, evidence in votes:
            key = ('evidence', evidence) if evidence is not None else ('module', module)
            evidence_groups[key].append((module, direction, value))
        counted = []
        for group in evidence_groups.values():
            if len({row[1] for row in group}) != 1:
                ignored.update(row[0] for row in group)
                continue
            # Same source event is not extra independent confirmation.
            chosen = max(group, key=lambda row: (row[2], row[0]))
            counted.append(chosen)
            ignored.update(row[0] for row in group if row != chosen)
        long_score = math.fsum(v for _, d, v in counted if d == Direction.LONG)
        short_score = math.fsum(v for _, d, v in counted if d == Direction.SHORT)
        if math.isclose(long_score, short_score, rel_tol=0, abs_tol=1e-12):
            return reject('NO_EVIDENCE_OR_DIRECTIONAL_TIE')
        direction = Direction.LONG if long_score > short_score else Direction.SHORT
        score = max(long_score, short_score)
        bonus = 0.0
        if ((direction == Direction.LONG and regime.regime.value == 'BULLISH_TREND')
                or (direction == Direction.SHORT and regime.regime.value == 'BEARISH_TREND')):
            bonus = 15.0
        elif regime.regime.value == 'VOLATILITY_EXPANSION':
            bonus = 8.0
        score = min(100.0, score + bonus)
        approved = score >= self.min_execution_score
        return ScoreBreakdown(
            symbol=symbol, direction=direction, total_score=score, regime_score=bonus,
            is_approved=approved,
            rejection_reason=None if approved else 'INSUFFICIENT_SCORE',
            contributing_modules=sorted(m for m, d, _ in counted if d == direction),
            ignored_modules=sorted(ignored),
        )
