"""
tests/test_engine.py — Test suite autónomo para QuantumBot Pro v1.0
Verifica modelos Pydantic, cálculo de Score Engine y asignación de Régimen de Mercado.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from core.models import Direction, RegimeType, StrategySignal, MarketRegimeState, ScoreBreakdown
from analytics.market_regime import MarketRegimeDetector
from analytics.score_engine import QuantumScoreEngine
from machine_learning.ml_filter import MLTradeFilter
from risk.risk_manager import QuantumRiskManager


def test_models():
    sig = StrategySignal(
        module_name="TestModule", symbol="BTC-USD", direction=Direction.LONG,
        strength=0.9, timeframe="15m", price=65000.0, atr=500.0, description="Test Signal"
    )
    assert sig.symbol == "BTC-USD"
    assert sig.direction == Direction.LONG
    assert sig.strength == 0.9


def test_score_engine():
    engine = QuantumScoreEngine(min_execution_score=80.0)
    regime = MarketRegimeState(
        symbol="BTC-USD", regime=RegimeType.BULLISH_TREND,
        adx_value=25.0, atr_percent=1.5, bb_bandwidth=2.0,
        is_tradable=True, reason="OK"
    )
    signals = [
        StrategySignal(
            module_name="Bot23_Oxford_MultiTF", symbol="BTC-USD", direction=Direction.LONG,
            strength=0.9, timeframe="1H", price=65000.0, atr=500.0, description="Oxford Long"
        ),
        StrategySignal(
            module_name="Bot22_FVG_Fibonacci", symbol="BTC-USD", direction=Direction.LONG,
            strength=0.9, timeframe="15m", price=65000.0, atr=500.0, description="FVG Long"
        )
    ]
    df15m = pd.DataFrame({
        'Close': np.linspace(64000, 65000, 30)
    })
    data = {'15m': df15m}

    score = engine.evaluate_signals("BTC-USD", Direction.LONG, signals, regime, data)
    assert score.total_score >= 60.0


def test_ml_filter():
    ml = MLTradeFilter(min_probability=0.65)
    approved, prob, reason = ml.predict_trade_probability("BTC-USD", "LONG", 85.0, 26.0, 1.8)
    assert approved is True
    assert prob >= 0.65


def test_risk_manager():
    rm = QuantumRiskManager(base_margin_usd=25.0, leverage=20, use_half_kelly=True)
    score = ScoreBreakdown(
        symbol="BTC-USD", direction=Direction.LONG, total_score=85.0, is_approved=True
    )
    decision = rm.calculate_risk_decision("BTC-USDT", Direction.LONG, 65000.0, 500.0, score, 0.75)
    assert decision.is_allowed is True
    assert decision.stop_loss_price < 65000.0
    assert decision.take_profit_price > 65000.0


if __name__ == '__main__':
    test_models()
    test_score_engine()
    test_ml_filter()
    test_risk_manager()
    print("✓ TODAS LAS PRUEBAS UNITARIAS DE QUANTUMBOT PRO PASARON CON ÉXITO!")
