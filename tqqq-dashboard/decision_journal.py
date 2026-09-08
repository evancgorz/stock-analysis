from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


JOURNAL_PATH = Path(__file__).resolve().parent / "decision_journal.jsonl"


def _read_entries() -> list[dict[str, Any]]:
    if not JOURNAL_PATH.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in JOURNAL_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _append(entry: dict[str, Any]) -> dict[str, Any]:
    entry = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(), **entry}
    canonical = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    entry["record_id"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    with JOURNAL_PATH.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def record_recommendation(entry: dict[str, Any]) -> dict[str, Any]:
    session = entry.get("session")
    action = entry.get("action")
    policy_key = entry.get("policy_key", "baseline")
    existing = _read_entries()
    matches = [
        item
        for item in existing
        if item.get("type") == "recommendation"
        and item.get("session") == session
        and item.get("action") == action
        and item.get("policy_key", "baseline") == policy_key
    ]
    if matches:
        return matches[0]
    return _append({"type": "recommendation", **entry})


def record_fill(entry: dict[str, Any]) -> dict[str, Any]:
    return _append({"type": "fill", **entry})


def load_journal() -> pd.DataFrame:
    entries = _read_entries()
    return pd.DataFrame(entries)


def assess_data_freshness(index: pd.DatetimeIndex, as_of: pd.Timestamp | None = None, max_business_days: int = 1) -> dict[str, Any]:
    if index.empty:
        return {"status": "invalid", "message": "No market sessions are available.", "latest_session": None}
    as_of = as_of or pd.Timestamp.now(tz="America/New_York")
    if as_of.tzinfo is not None:
        as_of = as_of.tz_localize(None)
    as_of = as_of.normalize()
    latest = pd.Timestamp(index[-1]).normalize()
    business_days = len(pd.bdate_range(latest, as_of)) - 1
    status = "fresh" if business_days <= max_business_days else "stale"
    return {
        "status": status,
        "message": "Latest completed session is within the freshness window." if status == "fresh" else "Market data is stale; do not issue a confirmed signal.",
        "latest_session": latest.date().isoformat(),
        "as_of": as_of.date().isoformat(),
        "business_days_old": int(business_days),
    }
