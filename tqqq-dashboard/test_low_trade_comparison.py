import unittest

import pandas as pd

from low_trade_comparison import LowTradeSpec, simulate_entry_locked_policy


class LowTradeComparisonTests(unittest.TestCase):
    def _data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        index = pd.date_range("2020-01-01", periods=25, freq="B")
        close = pd.Series(range(100, 125), index=index, dtype=float)
        data = pd.DataFrame(
            {
                "tqqq_open": close - 0.1,
                "tqqq_close": close,
                "qld_open": close - 0.05,
                "qld_close": close,
                "voo_open": close + 299.9,
                "voo_close": close + 300,
            },
            index=index,
        )
        active = ["VOO"] * 5 + ["TQQQ"] * 10 + ["VOO"] * 10
        reference = pd.DataFrame({"active_asset": active}, index=index)
        return data, reference

    def test_entry_locked_weight_does_not_rebalance_each_day(self) -> None:
        data, reference = self._data()
        frame = simulate_entry_locked_policy(
            data,
            reference,
            LowTradeSpec("fixed", "fixed", "entry_fixed", fixed_weight=0.50),
        )
        self.assertEqual(int((frame["turnover"] > 1e-12).sum()), 2)
        self.assertEqual(frame.loc[frame["risk_on"] > 0, "tqqq_weight"].nunique(), 1)
        self.assertAlmostEqual(float(frame.loc[frame["risk_on"] > 0, "tqqq_weight"].iloc[0]), 0.50)
        self.assertTrue((frame.loc[frame["risk_on"] == 0, "tqqq_weight"] == 0.0).all())


if __name__ == "__main__":
    unittest.main()
