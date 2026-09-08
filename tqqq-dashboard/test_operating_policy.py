import unittest

import pandas as pd

from operating_policy import build_action_plan, get_policy, target_tqqq_weight
from research_engine import ResearchConfig, simulate_strategy
from test_research_engine import sample_data


class OperatingPolicyTests(unittest.TestCase):
    def test_stale_data_suppresses_trade_instruction(self) -> None:
        data = sample_data(30)
        result = simulate_strategy(data, ResearchConfig(sma_window=3, cost_bps_per_leg=0.0))
        plan = build_action_plan(
            data,
            result,
            get_policy("baseline"),
            {"status": "stale"},
            account_value=100_000,
            current_tqqq_pct=0,
            upper_band=0.01,
            lower_band=-0.01,
        )
        self.assertEqual(plan["action"], "DO NOT TRADE")
        self.assertFalse(plan["confirmed"])

    def test_full_exposure_policy_targets_all_tqqq_when_risk_on(self) -> None:
        data = sample_data(30)
        result = simulate_strategy(data, ResearchConfig(sma_window=3, cost_bps_per_leg=0.0))
        result.frame.loc[result.frame.index[-1], "target_asset"] = "TQQQ"
        weight, volatility, _ = target_tqqq_weight(data, result, get_policy("baseline"))
        self.assertEqual(weight, 1.0)
        self.assertIsNone(volatility)

    def test_entry_locked_policy_keeps_weight_inside_declared_bounds(self) -> None:
        data = sample_data(35)
        result = simulate_strategy(data, ResearchConfig(sma_window=3, cost_bps_per_leg=0.0))
        result.frame.loc[result.frame.index[-1], "target_asset"] = "TQQQ"
        weight, _, _ = target_tqqq_weight(data, result, get_policy("entry_locked_60"))
        self.assertGreaterEqual(weight, 0.25)
        self.assertLessEqual(weight, 1.0)

    def test_hold_state_does_not_issue_an_unmodeled_catch_up_order(self) -> None:
        data = sample_data(30)
        result = simulate_strategy(data, ResearchConfig(sma_window=3, cost_bps_per_leg=0.0))
        result.frame.loc[result.frame.index[-1], ["active_asset", "target_asset"]] = ["TQQQ", "TQQQ"]
        plan = build_action_plan(
            data,
            result,
            get_policy("baseline"),
            {"status": "fresh"},
            account_value=100_000,
            current_tqqq_pct=0,
            upper_band=0.01,
            lower_band=-0.01,
        )
        self.assertEqual(plan["timing"], "No fresh order")
        self.assertIn("no fresh trade signal", str(plan["order_text"]))


if __name__ == "__main__":
    unittest.main()
