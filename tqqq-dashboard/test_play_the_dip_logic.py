import unittest

import pandas as pd

from play_the_dip_logic import build_play_the_dip_frame


class StrategyLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        dates = pd.date_range("2025-01-01", periods=6, freq="D")
        self.data = pd.DataFrame(
            {
                "tqqq_open": [100, 101, 102, 110, 111, 112],
                "tqqq_close": [101, 102, 103, 115, 116, 117],
                "voo_open": [400, 401, 402, 403, 404, 405],
                "voo_close": [401, 402, 403, 404, 405, 406],
                "spx_open": [100, 100, 100, 102, 102, 102],
                "spx_close": [100, 100, 100, 102, 102, 102],
            },
            index=dates,
        )

    def test_signal_is_executed_at_next_open(self) -> None:
        frame = build_play_the_dip_frame(self.data, 3, 0.01, -0.01)

        signal_day = self.data.index[3]
        execution_day = self.data.index[4]
        self.assertEqual(frame.loc[signal_day, "signal"], 1.0)
        self.assertEqual(frame.loc[signal_day, "position"], 0.0)
        self.assertEqual(frame.loc[execution_day, "position"], 1.0)

    def test_switch_day_uses_voo_overnight_and_tqqq_intraday(self) -> None:
        frame = build_play_the_dip_frame(self.data, 3, 0.01, -0.01)
        execution_day = self.data.index[4]
        expected = (404 / 404) * (116 / 111) - 1
        self.assertAlmostEqual(frame.loc[execution_day, "strategy_return"], expected)

    def test_cash_is_not_a_valid_defensive_asset(self) -> None:
        with self.assertRaises(ValueError):
            build_play_the_dip_frame(self.data, 3, 0.01, -0.01, "Cash")


if __name__ == "__main__":
    unittest.main()
