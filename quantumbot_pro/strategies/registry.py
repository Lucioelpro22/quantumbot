"""Canonical identities of existing modules; weights are historical, not optimized."""
import math
from types import MappingProxyType

# VWAP_Volume_Delta is the actual module's emitted name. No silent fallback weight.
DEFAULT_WEIGHTS = MappingProxyType({
    'Oracle_Fibonacci_DCA_Engine': 0.20,
    'BlackEaglesCap_Wyckoff_PDI': 0.18,
    'Bot23_Oxford_MultiTF': 0.18,
    'Bot22_FVG_Fibonacci': 0.12,
    'SMC_OrderBlock_Liquidity': 0.12,
    'VWAP_Volume_Delta': 0.08,
    'MeanReversion_RSI_Bollinger': 0.05,
    'Volatility_Breakout_Donchian': 0.04,
    'Keltner_Volatility_Squeeze': 0.03,
})


def validate_weights(weights):
    """Require an explicit registry-bound budget; unused weight stays unallocated."""
    result = dict(weights)
    if set(result) - set(DEFAULT_WEIGHTS):
        raise ValueError('Unknown module weight; use canonical registry identity')
    if any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1
           for v in result.values()):
        raise ValueError('Weights must be finite values in [0, 1]')
    if math.fsum(result.values()) > 1 + 1e-12:
        raise ValueError('Total weight exceeds one')
    return result
