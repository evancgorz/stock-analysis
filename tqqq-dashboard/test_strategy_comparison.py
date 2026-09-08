import unittest

import pandas as pd

from research_engine import ResearchConfig, simulate_strategy
from strategy_comparison import PolicySpec, _prior_realized_volatility, _weights_for_policy, simulate_policy


class StrategyComparisonTests(unittest.TestCase):
    def _data(self) -> pd.DataFrame:
        index = pd.date_range("2020-01-01", periods=35, freq="B")
        close = pd.Series(range(100, 135), index=index, dtype=float)
        data = pd.DataFrame(
            {
                "tqqq_open": close - 0.1,
                "tqqq_close": close,
                "tqqq_high": close + 0.2,
                "tqqq_low": close - 0.2,
                "qld_open": close - 0.05,
                "qld_close": close,
                "qld_high": close + 0.1,
                "qld_low": close - 0.1,
                "voo_open": close + 299.9,
                "voo_close": close + 300,
                "spx_close": close,
            },
            index=index,
        )
        return data

    def test_volatility_uses_only_completed_prior_sessions(self) -> None:
        data = self._data()
        volatility = _prior_realized_volatility(data, "tqqq", lookback=5)
        truncated = _prior_realized_volatility(data.iloc[:-1], "tqqq", lookback=5)
        self.assertAlmostEqual(float(volatility.iloc[-2]), float(truncated.iloc[-1]))

    def test_weight_policy_stays_inside_account_bounds(self) -> None:
        weights = _weights_for_policy(
            PolicySpec("test", "test", "tqqq_target", target_vol=0.40),
            active_risk_on=True,
            prior_volatility=1.20,
        )
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertGreaterEqual(weights["tqqq"], 0.25)
        self.assertLessEqual(weights["tqqq"], 1.0)

    def test_current_policy_reproduces_reference_returns(self) -> None:
        data = self._data()
        reference = simulate_strategy(data, ResearchConfig(sma_window=3, cost_bps_per_leg=5.0))
        frame = simulate_policy(data, reference.frame, PolicySpec("current", "current", "current"))
        pd.testing.assert_series_equal(
            frame["strategy_return"],
            reference.frame["strategy_return"],
            check_names=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )


if __name__ == "__main__":
    unittest.main()
