import csv
import tempfile
import unittest
from pathlib import Path

from core.models import Direction, ScoreBreakdown
from demo_profitability import evaluate
from risk.risk_manager import QuantumRiskManager


class DemoSafetyTests(unittest.TestCase):
    def test_risk_sizing_respects_budget(self):
        manager = QuantumRiskManager(leverage=3, max_risk_per_trade_pct=0.0025)
        score = ScoreBreakdown(symbol="BTCUSDT", direction=Direction.LONG, total_score=90, is_approved=True)
        decision = manager.calculate_risk_decision(
            "BTCUSDT", Direction.LONG, 100.0, 2.0, score, 0.8, account_equity=1000.0
        )
        risk = manager.calculate_account_economic_risk(
            100.0, decision.stop_loss_price, decision.quantity
        )
        self.assertTrue(decision.is_allowed)
        self.assertLessEqual(risk, 2.51)

    def test_missing_equity_blocks_trade(self):
        manager = QuantumRiskManager(leverage=3)
        score = ScoreBreakdown(symbol="BTCUSDT", direction=Direction.LONG, total_score=90, is_approved=True)
        decision = manager.calculate_risk_decision(
            "BTCUSDT", Direction.LONG, 100.0, 2.0, score, 0.8, account_equity=0.0
        )
        self.assertFalse(decision.is_allowed)

    def test_small_demo_sample_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ledger.csv"
            fields = ["order_id", "timestamp_ms", "symbol", "side", "pnl_usd", "return_pct", "open_fee", "close_fee"]
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
                for i in range(10):
                    writer.writerow({"order_id": str(i), "timestamp_ms": str(1700000000000 + i * 86400000),
                                     "symbol": "BTCUSDT", "side": "Buy", "pnl_usd": "1",
                                     "return_pct": "0.1", "open_fee": "0", "close_fee": "0"})
            self.assertEqual(evaluate(path)["verdict"], "INSUFFICIENT_OR_FAIL")


if __name__ == "__main__":
    unittest.main()
