"""Review-only module accounting; historical win rate cannot auto-promote weights."""
from strategies.registry import DEFAULT_WEIGHTS, validate_weights
from analytics.strategy_review import review_closed_trades


class StrategyAutoCalibrator:
    def __init__(self, initial_weights=None, decay_factor=0.85):
        self.default_weights = validate_weights(DEFAULT_WEIGHTS if initial_weights is None else initial_weights)
        self.weights = self.default_weights.copy()
        # Kept only for API compatibility; not used to mutate a budget.
        self.decay_factor = decay_factor
        self.last_review = None

    def review_trade_history(self, trade_history, *, provenance):
        self.last_review = review_closed_trades(trade_history, provenance=provenance)
        return self.last_review

    def calibrate_from_trade_history(self, trade_history):
        # Old callers cannot silently launch data-driven weight tuning. An
        # explicit review requires attributed records and declared provenance.
        self.last_review = {'status': 'MANUAL_REVIEW_REQUIRED',
                            'reason': 'Automatic weight changes disabled; use review_trade_history',
                            'strategy_validated': False}
        return self.weights.copy()
