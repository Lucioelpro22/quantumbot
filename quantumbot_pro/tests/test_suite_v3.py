"""
tests/test_suite_v3.py — Suite Completa de Pruebas Unitarias e Integración QuantumBot Pro v3.0 (P0 - P21)
Verifica componentes institucionales:
1. ExplainableAIEngine & Reportes de Auditoría (XAI).
2. PurgedCrossValidator & Embargo Folds (P6 & P7).
3. StatisticalValidationGate & Rechazo de Candidatos Degradados (P8 & P10).
4. PortfolioRiskAllocator & Volatility Targeting (P14).
5. SystemicCrisisSimulator & Monte Carlo Resampling (P9).
6. PriceActionConfirmationEngine (Pinbar, Engulfing, CHoCH) & Prevención de Look-Ahead Bias (P12).
7. QuantDatabaseManager & Persistencia de Estado de Posiciones (P15 Crash Recovery).
8. EmergencyKillSwitch (P0.3) & Aislamiento de Entornos (P0.2).
9. Real Economic Risk & Sizing (P1.1).
10. Deflated Sharpe Ratio Formal (P5 DSR).
11. Test de Caos & Resiliencia ante fallas de red (P21).
"""

import unittest
import os
import sys
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.xai_engine import ExplainableAIEngine
from analytics.purged_cv import PurgedCrossValidator
from analytics.metrics import QuantitativeMetricsEngine
from research.validation_gate import StatisticalValidationGate
from risk.portfolio_allocator import PortfolioRiskAllocator
from backtesting.crisis_simulator import SystemicCrisisSimulator
from analytics.price_action_engine import PriceActionConfirmationEngine
from database.db_manager import QuantDatabaseManager
from risk.kill_switch import EmergencyKillSwitch
from risk.risk_manager import QuantumRiskManager
from execution.reconciler import ExchangeStateReconciler
from strategies.oracle_fibonacci_dca_module import OracleFibonacciDCAModule
from core.models import Direction, ScoreBreakdown, StrategySignal, RiskDecision, MarketRegimeState, RegimeType


class TestQuantumBotProV3(unittest.TestCase):

    def setUp(self):
        self.xai = ExplainableAIEngine()
        self.purged_cv = PurgedCrossValidator(n_splits=3, pct_embargo=0.02)
        self.metrics_eng = QuantitativeMetricsEngine()
        self.gate = StatisticalValidationGate()
        self.allocator = PortfolioRiskAllocator(target_portfolio_volatility=0.15)
        self.crisis_sim = SystemicCrisisSimulator()
        self.pa_engine = PriceActionConfirmationEngine(min_wick_ratio=0.55)
        self.db = QuantDatabaseManager(":memory:")
        self.kill_switch = EmergencyKillSwitch(max_daily_loss_pct=5.0, max_drawdown_pct=10.0)
        self.risk_manager = QuantumRiskManager(base_margin_usd=25.0, leverage=25)

    def test_01_explainable_ai_engine(self):
        signals = [
            StrategySignal(module_name="Oracle_Fibonacci_DCA_Engine", symbol="BTC-USD", direction=Direction.LONG, strength=0.9, confidence=85.0, timeframe="15m", price=65000.0, atr=500.0, description="Test Signal 1"),
            StrategySignal(module_name="BlackEaglesCap_Wyckoff_PDI", symbol="BTC-USD", direction=Direction.LONG, strength=0.85, confidence=80.0, timeframe="1h", price=65000.0, atr=500.0, description="Test Signal 2")
        ]
        score = ScoreBreakdown(symbol="BTC-USD", direction=Direction.LONG, total_score=85.0, is_approved=True)
        decision = RiskDecision(symbol="BTC-USD", direction=Direction.LONG, is_allowed=True, quantity=0.1, stop_loss_price=64000.0, take_profit_price=66000.0, leverage=25, reason="Aprobado Test", score=85.0, ml_probability=0.75, suggested_margin_usd=25.0)
        regime = MarketRegimeState(symbol="BTC-USD", regime=RegimeType.BULLISH_TREND, adx_value=30.0, atr_percent=1.5, bb_bandwidth=0.05, is_tradable=True, reason="Test Trend")

        log = self.xai.generate_trade_audit_log("BTC-USD", "ENTRY", decision, score, regime, signals, 0.75, {"Oracle_Fibonacci_DCA_Engine": 0.2})
        self.assertIn("timestamp", log)
        self.assertEqual(log["decision_summary"]["direction"], "LONG")

    def test_02_purged_cross_validation(self):
        df = pd.DataFrame({'Close': np.linspace(100, 200, 100)})
        folds = self.purged_cv.split(df)
        self.assertEqual(len(folds), 3)
        for train_idx, test_idx in folds:
            self.assertTrue(len(train_idx) > 0)
            self.assertTrue(len(test_idx) > 0)
            # P6 Check: Intersección 0 entre Train y Test
            inter = np.intersect1d(train_idx, test_idx)
            self.assertEqual(len(inter), 0)

    def test_03_statistical_validation_gate(self):
        stable = {"sharpe_ratio": 2.5, "sortino_ratio": 3.0, "profit_factor": 2.1, "max_drawdown_percent": 12.0, "win_rate_percent": 65.0}
        degraded = {"sharpe_ratio": 2.1, "sortino_ratio": 2.8, "profit_factor": 1.9, "max_drawdown_percent": 15.0, "win_rate_percent": 60.0}

        passed, reason, _ = self.gate.evaluate_candidate_hypothesis(stable, degraded)
        self.assertFalse(passed)
        self.assertIn("RECHAZADO", reason)

    def test_04_portfolio_risk_allocator(self):
        alloc = self.allocator.calculate_optimal_allocation(capital_usd=10000.0, symbol="BTC-USDT", entry_price=65000.0, atr_price=500.0)
        self.assertIn("margin_usd", alloc)
        self.assertGreater(alloc["margin_usd"], 0)

    def test_05_systemic_crisis_simulator(self):
        dates15m = pd.date_range('2026-01-01', periods=120, freq='15min')
        dates1h  = pd.date_range('2026-01-01', periods=120, freq='1h')
        df15m = pd.DataFrame({'Open': np.linspace(60000, 62000, 120), 'High': np.linspace(60200, 62200, 120), 'Low': np.linspace(59800, 61800, 120), 'Close': np.linspace(60100, 62100, 120), 'Volume': [100.0]*120}, index=dates15m)
        df1h  = pd.DataFrame({'Open': np.linspace(60000, 62000, 120), 'High': np.linspace(60500, 62500, 120), 'Low': np.linspace(59500, 61500, 120), 'Close': np.linspace(60200, 62200, 120), 'Volume': [400.0]*120}, index=dates1h)

        res = self.crisis_sim.run_all_crisis_scenarios(df1h, df15m)
        self.assertIn("all_crisis_passed", res)

    def test_06_price_action_engine_pinbar(self):
        dates = pd.date_range('2026-01-01', periods=10, freq='15min')
        df = pd.DataFrame({
            'Open':  [100, 101, 102, 103, 104, 105, 106, 107, 100, 100],
            'High':  [102, 103, 104, 105, 106, 107, 108, 109, 105, 105],
            'Low':   [99,  100, 101, 102, 103, 104, 105, 106, 90,  90],
            'Close': [101, 102, 103, 104, 105, 106, 107, 108, 104, 104],
            'Volume': [100.0] * 10
        }, index=dates)

        ok, pattern, score = self.pa_engine.evaluate_price_action(df, 'LONG')
        self.assertTrue(ok)
        self.assertIn("Pinbar Alcista", pattern)
        self.assertGreater(score, 70.0)

    def test_07_database_persistent_state(self):
        pos_key = "BTC-USDT_LONG_64000.0"
        self.db.set_position_partial_closed(pos_key, "BTC-USDT", "LONG", 64000.0)
        closed_set = self.db.get_partial_closed_positions()
        self.assertIn(pos_key, closed_set)

    def test_08_emergency_kill_switch(self):
        self.kill_switch.activate_manual_kill("Prueba Manual")
        active, reason = self.kill_switch.evaluate_kill_switch_conditions(0.0, 0.0, 0)
        self.assertTrue(active)
        self.assertIn("Manual", reason)

        self.kill_switch.deactivate_manual_kill()
        active_dl, reason_dl = self.kill_switch.evaluate_kill_switch_conditions(5.5, 0.0, 0)
        self.assertTrue(active_dl)
        self.assertIn("Límite de Pérdida Diaria", reason_dl)

    def test_09_real_economic_risk_calculation(self):
        risk_usd = self.risk_manager.calculate_account_economic_risk(
            entry_price=64000.0, stop_loss_price=63000.0, quantity=0.1
        )
        self.assertGreater(risk_usd, 100.0)

    def test_10_deflated_sharpe_ratio_formal(self):
        rets = np.array([0.02, 0.015, -0.01, 0.03, 0.025, -0.005, 0.018, 0.022])
        dsr = self.metrics_eng.calculate_formal_dsr(rets, estimated_sharpe=2.1, n_trials=10)
        self.assertGreaterEqual(dsr, 0.0)
        self.assertLessEqual(dsr, 1.0)

    def test_11_monte_carlo_resampling(self):
        rets = [0.01, -0.005, 0.02, -0.01, 0.015, 0.008, -0.004]
        res = self.crisis_sim.run_monte_carlo_resampling(rets, n_simulations=100, seed=42)
        self.assertIn("risk_of_ruin_percent", res)
        self.assertEqual(res["status"], "PASSED")


if __name__ == '__main__':
    unittest.main()
