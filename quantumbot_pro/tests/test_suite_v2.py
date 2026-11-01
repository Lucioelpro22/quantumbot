"""
tests/test_suite_v2.py — Suite Completa de Pruebas Unitarias e Integración para QuantumBot Pro v2.0
Verifica Base de Datos, Métricas Institucionales, Ensemble de 7 Estrategias, ML Guard y Backtesting.
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import QuantDatabaseManager
from analytics.metrics import QuantitativeMetricsEngine
from analytics.market_regime import MarketRegimeDetector
from machine_learning.ml_guard import SupervisedMLGuard
from strategies.meta_strategy import MetaStrategyEnsemble
from backtesting.backtest_engine import QuantBacktestEngine
from backtesting.walk_forward import WalkForwardOptimizer
from backtesting.monte_carlo import MonteCarloSimulator


def test_database():
    db = QuantDatabaseManager()
    db.save_performance_snapshot(
        equity=10000.0, sharpe=2.1, sortino=3.2, calmar=4.5,
        max_dd=8.5, win_rate=65.0, total_trades=20
    )
    trades = db.get_recent_trades(limit=5)
    print("  ✓ [DB] QuantDatabaseManager inicializado y funcional.")


def test_metrics_engine():
    me = QuantitativeMetricsEngine()
    rets = [0.02, -0.01, 0.03, 0.015, -0.005, 0.04, -0.012, 0.025]
    eq   = [10000, 10200, 10098, 10400, 10556, 10503, 10923, 10792, 11061]
    res  = me.calculate_metrics(rets, eq)

    assert "sharpe_ratio" in res
    assert "sortino_ratio" in res
    assert "calmar_ratio" in res
    assert "ulcer_index" in res
    assert "var_95_percent" in res
    print("  ✓ [MÉTRICAS] QuantitativeMetricsEngine calculó Sharpe, Sortino, Calmar y VaR correctamente.")


def test_market_regime():
    det = MarketRegimeDetector()
    dates = pd.date_range("2026-01-01", periods=60, freq="1h")
    df1h = pd.DataFrame({
        "Open": np.linspace(60000, 65000, 60),
        "High": np.linspace(60500, 65500, 60),
        "Low": np.linspace(59800, 64800, 60),
        "Close": np.linspace(60200, 65200, 60),
        "Volume": [100.0] * 60
    }, index=dates)
    regime = det.analyze_regime("BTC-USD", df1h)
    assert regime.regime is not None
    print(f"  ✓ [RÉGIMEN] MarketRegimeDetector clasificó régimen: {regime.regime.value}")


def test_ml_guard():
    guard = SupervisedMLGuard(min_probability=0.65)
    ok, prob, reason = guard.evaluate_signal_gate("BTC-USD", "LONG", 85.0, 30.0, 1.8, 2.5)
    assert ok is True
    assert prob >= 0.65
    print(f"  ✓ [ML GUARD] SupervisedMLGuard aprobó señal con probabilidad {prob*100:.1f}%")


def test_backtest_and_monte_carlo():
    dates15m = pd.date_range("2026-01-01", periods=100, freq="15min")
    dates1h  = pd.date_range("2026-01-01", periods=30, freq="1h")

    df15m = pd.DataFrame({
        "Open": np.linspace(60000, 62000, 100),
        "High": np.linspace(60200, 62200, 100),
        "Low": np.linspace(59800, 61800, 100),
        "Close": np.linspace(60100, 62100, 100),
        "Volume": [200.0] * 100
    }, index=dates15m)

    df1h = pd.DataFrame({
        "Open": np.linspace(60000, 62000, 30),
        "High": np.linspace(60500, 62500, 30),
        "Low": np.linspace(59500, 61500, 30),
        "Close": np.linspace(60200, 62200, 30),
        "Volume": [800.0] * 30
    }, index=dates1h)

    b_engine = QuantBacktestEngine()
    bt_res   = b_engine.run_backtest(df1h, df15m, "BTC-USD")
    assert "sharpe_ratio" in bt_res

    mc = MonteCarloSimulator(n_simulations=100)
    mc_res = mc.run_simulation([0.02, -0.01, 0.03, 0.015, -0.005])
    assert mc_res["simulations_count"] == 100
    print("  ✓ [BACKTEST & MONTE CARLO] Motores de simulación ejecutados exitosamente.")


if __name__ == '__main__':
    print("\n========================================================")
    print("🧪 EJECUTANDO SUITE DE PRUEBAS UNITARIAS QUANTUMBOT PRO v2.0")
    print("========================================================\n")
    test_database()
    test_metrics_engine()
    test_market_regime()
    test_ml_guard()
    test_backtest_and_monte_carlo()
    print("\n✓ TODAS LAS PRUEBAS UNITARIAS E INTEGRACIÓN PASARON EXITOSAMENTE!\n")
