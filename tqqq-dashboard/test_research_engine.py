import unittest

import pandas as pd

from research_engine import (
    ResearchConfig,
    generate_walk_forward_folds,
    score_episodes,
    simulate_strategy,
)


def sample_data(periods: int = 30) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=periods, freq="B")
    spx = [100.0] * 5 + [102.0 + i * 0.5 for i in range(periods - 5)]
    tqqq_close = [100.0 + i * 0.2 for i in range(periods)]
    tqqq_open = [value - 0.1 for value in tqqq_close]
    voo_close = [400.0 + i * 0.1 for i in range(periods)]
    voo_open = [value - 0.05 for value in voo_close]
    if periods >= 10:
        spx[-3:] = [90.0, 89.0, 88.0]
        tqqq_close[-3:] = [80.0, 79.0, 78.0]
        tqqq_open = [value - 0.1 for value in tqqq_close]
    return pd.DataFrame(
        {
            "tqqq_open": tqqq_open,
            "tqqq_close": tqqq_close,
            "voo_open": voo_open,
            "voo_close": voo_close,
            "spx_close": spx,
        },
        index=index,
    )


class ResearchEngineTests(unittest.TestCase):
    def test_next_open_fill_and_episode_use_the_old_asset_exit_price(self) -> None:
        data = sample_data()
        result = simulate_strategy(data, ResearchConfig(sma_window=3, cost_bps_per_leg=0.0))
        self.assertFalse(result.fills.empty)
        exits = result.fills.loc[result.fills["new_asset"] == "VOO"]
        self.assertFalse(exits.empty)
        exit_row = exits.iloc[0]
        self.assertEqual(float(exit_row["old_fill_price"]), float(data.loc[pd.Timestamp(exit_row["fill_date"]), "tqqq_open"]))
        self.assertAlmostEqual(float(result.episodes.iloc[0]["Exit fill"]), float(exit_row["old_fill_price"]))

    def test_costs_reduce_account_equity(self) -> None:
        data = sample_data()
        free = simulate_strategy(data, ResearchConfig(sma_window=3, cost_bps_per_leg=0.0))
        charged = simulate_strategy(data, ResearchConfig(sma_window=3, cost_bps_per_leg=25.0))
        self.assertLess(charged.frame["strategy_equity"].iloc[-1], free.frame["strategy_equity"].iloc[-1])

    def test_future_rows_do_not_change_prior_decisions(self) -> None:
        data = sample_data()
        prefix = data.iloc[:20]
        full_result = simulate_strategy(data, ResearchConfig(sma_window=3, cost_bps_per_leg=0.0))
        prefix_result = simulate_strategy(prefix, ResearchConfig(sma_window=3, cost_bps_per_leg=0.0))
        pd.testing.assert_series_equal(
            full_result.frame.loc[prefix.index, "target_asset"],
            prefix_result.frame["target_asset"],
            check_names=False,
        )

    def test_walk_forward_folds_are_chronological(self) -> None:
        index = pd.date_range("2010-01-01", periods=12 * 252, freq="B")
        folds = generate_walk_forward_folds(index, initial_years=5, test_years=1)
        self.assertGreater(len(folds), 2)
        self.assertTrue(all(row["train_end"] < row["test_start"] for row in folds))
        self.assertTrue(all(folds[i]["test_end"] < folds[i + 1]["test_start"] for i in range(len(folds) - 1)))

    def test_empty_episode_summary_is_explicit(self) -> None:
        summary = score_episodes(pd.DataFrame())
        self.assertEqual(summary["Episodes"], 0)
        self.assertEqual(summary["Compounded relative wealth %"], 0.0)


if __name__ == "__main__":
    unittest.main()
