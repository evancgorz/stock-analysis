from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pandas as pd

from decision_journal import assess_data_freshness, record_recommendation
from play_the_dip_logic import STRATEGY_VERSION, download_market_data
from research_engine import ResearchConfig, simulate_strategy


def build_recommendation(frame: pd.DataFrame, freshness: dict[str, object]) -> dict[str, object]:
    latest = frame.iloc[-1]
    active = str(latest["active_asset"])
    target = str(latest["target_asset"])
    if freshness["status"] != "fresh":
        action = "No confirmed action: stale data"
    elif active == "TQQQ" and target == "VOO":
        action = "Exit TQQQ to VOO next session"
    elif active == "VOO" and target == "TQQQ":
        action = "Enter TQQQ next session"
    elif active == "TQQQ":
        action = "Hold TQQQ"
    else:
        action = "Hold VOO"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "strategy_version": STRATEGY_VERSION,
        "session": frame.index[-1].date().isoformat(),
        "action": action,
        "active_asset": active,
        "target_asset": target,
        "signal_event": str(latest["event"] or ""),
        "distance_to_sma": float(latest["distance_to_sma"]),
        "phase": str(latest["phase"]),
        "freshness": freshness,
    }


def run(end_date: str | None = None) -> dict[str, object]:
    end = pd.Timestamp(end_date) if end_date else pd.Timestamp.today().normalize()
    data = download_market_data(end - pd.DateOffset(years=3), end)
    result = simulate_strategy(data, ResearchConfig())
    freshness = assess_data_freshness(result.frame.index, as_of=end)
    recommendation = build_recommendation(result.frame, freshness)
    if freshness["status"] == "fresh":
        record_recommendation(recommendation)
    return recommendation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate and journal the latest daily strategy recommendation.")
    parser.add_argument("--end", default=None, help="Expected completed session date, YYYY-MM-DD")
    args = parser.parse_args()
    print(json.dumps(run(args.end), indent=2, sort_keys=True))
