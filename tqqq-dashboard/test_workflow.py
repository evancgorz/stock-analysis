import unittest

import pandas as pd

from daily_signal import build_recommendation
from decision_journal import assess_data_freshness


class WorkflowTests(unittest.TestCase):
    def test_stale_data_never_produces_a_confirmed_action(self) -> None:
        index = pd.date_range("2026-01-01", periods=2, freq="B")
        freshness = assess_data_freshness(index, as_of=pd.Timestamp("2026-01-12"), max_business_days=1)
        frame = pd.DataFrame(
            {
                "active_asset": ["VOO", "VOO"],
                "target_asset": ["TQQQ", "TQQQ"],
                "event": ["", "Buy level reached"],
                "distance_to_sma": [0.0, 0.02],
                "phase": ["Armed for next buy signal", "Holding TQQQ"],
            },
            index=index,
        )
        recommendation = build_recommendation(frame, freshness)
        self.assertEqual(freshness["status"], "stale")
        self.assertTrue(str(recommendation["action"]).startswith("No confirmed action"))

    def test_fresh_enter_signal_is_explicit(self) -> None:
        index = pd.date_range("2026-01-01", periods=2, freq="B")
        freshness = assess_data_freshness(index, as_of=index[-1], max_business_days=1)
        frame = pd.DataFrame(
            {
                "active_asset": ["VOO", "VOO"],
                "target_asset": ["VOO", "TQQQ"],
                "event": ["", "Buy level reached"],
                "distance_to_sma": [0.0, 0.02],
                "phase": ["Armed for next buy signal", "Holding TQQQ"],
            },
            index=index,
        )
        recommendation = build_recommendation(frame, freshness)
        self.assertEqual(recommendation["action"], "Enter TQQQ next session")


if __name__ == "__main__":
    unittest.main()
