"""Pure operating-policy helpers for the low-attention strategy cockpit."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OperatingPolicy:
    key: str
    label: str
    description: str
    exit_mode: str
    target_volatility: float | None = None
    research_status: str = "Research challenger"


OPERATING_POLICIES: tuple[OperatingPolicy, ...] = (
    OperatingPolicy(
        key="baseline",
        label="Frozen baseline — full TQQQ",
        description="Use the frozen signal specification and allocate the full account to TQQQ while risk-on.",
        exit_mode="ath_trailing_close",
        research_status="Frozen research baseline",
    ),
    OperatingPolicy(
        key="entry_locked_60",
        label="Low-trading — entry-locked 60% target",
        description="Set TQQQ exposure once at entry from prior 20-session volatility, keep at least 25%, and make no daily sizing changes.",
        exit_mode="ath_trailing_close",
        target_volatility=0.60,
    ),
    OperatingPolicy(
        key="trend_failure",
        label="Responsive exit — full TQQQ",
        description="Use full TQQQ while risk-on and exit after the S&P 500 closes below its SMA.",
        exit_mode="trend_failure",
    ),
)


def get_policy(key: str) -> OperatingPolicy:
    return next((policy for policy in OPERATING_POLICIES if policy.key == key), OPERATING_POLICIES[0])


def annualized_realized_volatility(data: pd.DataFrame, lookback: int = 20) -> pd.Series:
    return data["tqqq_close"].pct_change().rolling(lookback).std() * np.sqrt(252)


def target_tqqq_weight(
    data: pd.DataFrame,
    result,
    policy: OperatingPolicy,
) -> tuple[float, float | None, str]:
    latest = result.frame.iloc[-1]
    if str(latest["target_asset"]) != "TQQQ":
        return 0.0, None, "The confirmed model target is VOO."
    if policy.target_volatility is None:
        return 1.0, None, "This policy uses full TQQQ exposure while risk-on."

    volatility = annualized_realized_volatility(data)
    active_asset = str(latest["active_asset"])
    entry_date: pd.Timestamp | None = None
    if active_asset == "TQQQ" and not result.fills.empty:
        entries = result.fills.loc[result.fills["new_asset"] == "TQQQ"]
        if not entries.empty:
            entry_date = pd.Timestamp(entries.iloc[-1]["fill_date"])

    if entry_date is not None and entry_date in volatility.index:
        prior_index = volatility.index.get_loc(entry_date) - 1
        realized = float(volatility.iloc[prior_index]) if prior_index >= 0 and pd.notna(volatility.iloc[prior_index]) else np.nan
        basis = f"Locked from volatility available before the {entry_date.date()} entry."
    else:
        realized = float(volatility.iloc[-1]) if pd.notna(volatility.iloc[-1]) else np.nan
        basis = "Calculated from the latest completed 20-session window for the pending entry."

    if not np.isfinite(realized) or realized <= 0:
        return 1.0, None, "Insufficient volatility history; the policy falls back to full exposure."
    weight = max(0.25, min(1.0, float(policy.target_volatility) / realized))
    return float(weight), realized, basis


def next_condition(
    latest: pd.Series,
    policy: OperatingPolicy,
    upper_band: float,
    lower_band: float,
) -> str:
    sma = float(latest["spx_sma"])
    target = str(latest["target_asset"])
    if target == "TQQQ":
        if policy.exit_mode == "trend_failure":
            return f"Exit only after the S&P 500 closes below its SMA ({sma:,.2f} currently)."
        stop = latest.get("tqqq_trailing_stop_level", np.nan)
        if pd.notna(stop):
            return f"Exit if TQQQ closes at or below the active trailing level ({float(stop):,.2f} currently)."
        return "No exit is armed yet; a fresh S&P 500 all-time high must activate the trailing rule."

    phase = str(latest.get("phase", ""))
    if "reset" in phase.lower():
        return f"First re-arm after the S&P 500 closes below {sma * (1.0 + lower_band):,.2f}."
    return f"Enter only after the S&P 500 closes above {sma * (1.0 + upper_band):,.2f}."


def build_action_plan(
    data: pd.DataFrame,
    result,
    policy: OperatingPolicy,
    freshness: dict[str, object],
    account_value: float,
    current_tqqq_pct: float,
    upper_band: float,
    lower_band: float,
) -> dict[str, object]:
    latest = result.frame.iloc[-1]
    active = str(latest["active_asset"])
    target = str(latest["target_asset"])
    weight, realized_volatility, sizing_basis = target_tqqq_weight(data, result, policy)
    confirmed = freshness.get("status") == "fresh"

    if not confirmed:
        action = "DO NOT TRADE"
        action_kind = "stale"
        timing = "Refresh completed market data"
    elif active == "TQQQ" and target == "VOO":
        action = "EXIT TQQQ → VOO"
        action_kind = "exit"
        timing = "Next market open"
    elif active == "VOO" and target == "TQQQ":
        action = "ENTER TQQQ"
        action_kind = "enter"
        timing = "Next market open"
    elif target == "TQQQ":
        action = "HOLD TARGET ALLOCATION"
        action_kind = "hold_risk"
        timing = "No fresh order"
    else:
        action = "HOLD VOO"
        action_kind = "hold_voo"
        timing = "No fresh order"

    target_tqqq_dollars = float(account_value) * weight
    target_voo_dollars = float(account_value) - target_tqqq_dollars
    current_tqqq_dollars = float(account_value) * float(current_tqqq_pct) / 100.0
    tqqq_change = target_tqqq_dollars - current_tqqq_dollars
    tolerance = max(float(account_value) * 0.005, 1.0)
    if not confirmed:
        order_text = "No order: market data is not fresh enough to confirm an action."
    elif abs(tqqq_change) <= tolerance:
        order_text = "No material allocation change is needed."
    elif action_kind not in {"enter", "exit"}:
        order_text = "Your entered allocation differs from the model, but there is no fresh trade signal; review the mismatch before placing a catch-up order."
    elif tqqq_change > 0:
        order_text = f"Move approximately ${tqqq_change:,.0f} from VOO to TQQQ."
    else:
        order_text = f"Move approximately ${abs(tqqq_change):,.0f} from TQQQ to VOO."

    return {
        "action": action,
        "action_kind": action_kind,
        "confirmed": confirmed,
        "timing": timing,
        "signal_session": result.frame.index[-1].date().isoformat(),
        "active_asset": active,
        "target_asset": target,
        "target_tqqq_weight": weight,
        "target_voo_weight": 1.0 - weight,
        "target_tqqq_dollars": target_tqqq_dollars,
        "target_voo_dollars": target_voo_dollars,
        "tqqq_change_dollars": tqqq_change,
        "order_text": order_text,
        "realized_volatility": realized_volatility,
        "sizing_basis": sizing_basis,
        "next_condition": next_condition(latest, policy, upper_band, lower_band),
        "signal_event": str(latest.get("event", "") or "No new event"),
        "phase": str(latest.get("phase", "")),
    }
