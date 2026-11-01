import unittest
import numpy as np
import pandas as pd

from strategies.oxford_daily_ma import build_oxford_series, evaluate_oxford


class OxfordDailyMATests(unittest.TestCase):
    def test_signal_is_delayed_one_day(self):
        close = pd.Series([10, 10, 10, 10, 11, 12, 9], index=pd.date_range("2024-01-01", periods=7))
        frame = build_oxford_series(close, ma_days=5, round_trip_cost_bps=0)
        self.assertEqual(int(frame.loc[pd.Timestamp("2024-01-05"), "signal"]), 1)
        self.assertEqual(int(frame.loc[pd.Timestamp("2024-01-05"), "position"]), 0)
        self.assertEqual(int(frame.loc[pd.Timestamp("2024-01-06"), "position"]), 1)

    def test_costs_reduce_equity(self):
        close = pd.Series(100 * np.cumprod(np.r_[1.0, np.repeat(1.01, 79)]),
                          index=pd.date_range("2024-01-01", periods=80))
        free = build_oxford_series(close, 5, 0)["strategy_equity"].iloc[-1]
        costly = build_oxford_series(close, 5, 12)["strategy_equity"].iloc[-1]
        self.assertLess(costly, free)

    def test_evaluation_has_real_trade_count(self):
        values = 100 + np.sin(np.arange(200) / 4) * 10 + np.arange(200) * 0.1
        result = evaluate_oxford(pd.Series(values), "BTC-USD")
        self.assertGreater(result.trades, 0)


if __name__ == "__main__":
    unittest.main()
