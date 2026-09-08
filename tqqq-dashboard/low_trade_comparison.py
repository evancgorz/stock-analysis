"""Test low-attention alternatives that do not rebalance every day.

The key design choice is entry-locked exposure: volatility is measured before
the next-open entry, a weight or risk-on instrument is selected once, and that
choice is held until the existing exit signal. This isolates the practical
tradeoff between risk control and operator burden.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from research_engine import ResearchConfig, simulate_strategy
from strategy_comparison import (
    INITIAL_CAPITAL,
    _asset_return,
    _markdown_table,
    _prior_realized_volatility,
    _score_frame,
    build_walk_forward_table,
    load_comparison_data,
    simulate_policy,
    POLICIES,
)


TRANSACTION_COST_BPS = 5.0


@dataclass(frozen=True)
class LowTradeSpec:
    key: str
    label: str
    mode: str
    target_vol: float | None = None
    volatility_threshold: float | None = None
    fixed_weight: float | None = None
    min_weight: float = 0.25


LOW_TRADE_POLICIES: tuple[LowTradeSpec, ...] = (
    LowTradeSpec("current_tqqq", "Current strategy: 100% TQQQ risk-on", "current"),
    LowTradeSpec("entry_target_60", "Entry-locked TQQQ target 60%", "entry_target", target_vol=0.60),
    LowTradeSpec("entry_target_50", "Entry-locked TQQQ target 50%", "entry_target", target_vol=0.50),
    LowTradeSpec("entry_target_40", "Entry-locked TQQQ target 40%", "entry_target", target_vol=0.40),
    LowTradeSpec("entry_target_30", "Entry-locked TQQQ target 30%", "entry_target", target_vol=0.30),
    LowTradeSpec("entry_high_vol_half", "Entry-locked half-size above 60% volatility", "entry_filter", volatility_threshold=0.60, fixed_weight=0.50),
    LowTradeSpec("entry_leverage_ladder", "Entry-locked TQQQ/QLD volatility ladder", "entry_ladder", volatility_threshold=0.60),
    LowTradeSpec("entry_half", "Entry-locked 50% TQQQ / 50% VOO", "entry_fixed", fixed_weight=0.50),
)


EXIT_POLICIES: tuple[tuple[str, str, str], ...] = (
    ("exit_current", "Current ATH-activated 10% trailing exit", "ath_trailing_close"),
    ("exit_trend_failure", "Trend-failure exit: SPX closes below its SMA", "trend_failure"),
    ("exit_immediate_trail", "Immediate 10% TQQQ close trail", "immediate_trailing_close"),
)


def _git_revision() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def _entry_weights(spec: LowTradeSpec, prior_volatility: float) -> dict[str, float]:
    weights = {"tqqq": 0.0, "qld": 0.0, "voo": 1.0}
    if spec.mode == "entry_target":
        weight = 1.0 if not np.isfinite(prior_volatility) or prior_volatility <= 0 else min(1.0, float(spec.target_vol) / prior_volatility)
        weight = max(spec.min_weight, weight)
        weights["tqqq"] = weight
        weights["voo"] = 1.0 - weight
    elif spec.mode == "entry_filter":
        weight = 1.0 if not np.isfinite(prior_volatility) or prior_volatility <= float(spec.volatility_threshold) else float(spec.fixed_weight)
        weights["tqqq"] = weight
        weights["voo"] = 1.0 - weight
    elif spec.mode == "entry_ladder":
        if np.isfinite(prior_volatility) and prior_volatility > float(spec.volatility_threshold):
            weights["qld"] = 1.0
            weights["voo"] = 0.0
        else:
            weights["tqqq"] = 1.0
            weights["voo"] = 0.0
    elif spec.mode == "entry_fixed":
        weights["tqqq"] = float(spec.fixed_weight)
        weights["voo"] = 1.0 - float(spec.fixed_weight)
    else:
        raise ValueError(f"Unsupported low-trade mode: {spec.mode}")
    return weights


def simulate_entry_locked_policy(data: pd.DataFrame, reference_frame: pd.DataFrame, spec: LowTradeSpec) -> pd.DataFrame:
    volatility = _prior_realized_volatility(data, "tqqq")
    previous_weights = {"tqqq": 0.0, "qld": 0.0, "voo": 1.0}
    locked_weights: dict[str, float] | None = None
    previous_active = False
    equity = INITIAL_CAPITAL
    rows: list[dict[str, object]] = []

    for i, index in enumerate(data.index):
        active = reference_frame.loc[index, "active_asset"] == "TQQQ"
        prior_vol = float(volatility.loc[index]) if pd.notna(volatility.loc[index]) else np.nan
        if active and not previous_active:
            locked_weights = _entry_weights(spec, prior_vol)
        if not active:
            locked_weights = None
        weights = locked_weights or {"tqqq": 0.0, "qld": 0.0, "voo": 1.0}

        gap_return = 0.0
        if i > 0:
            previous = data.index[i - 1]
            for asset, weight in previous_weights.items():
                gap_return += weight * (_asset_return(data, asset, "open", index) / _asset_return(data, asset, "close", previous) - 1.0)
            equity *= 1.0 + gap_return

        turnover = sum(abs(weights[asset] - previous_weights[asset]) for asset in previous_weights)
        cost_return = -turnover * TRANSACTION_COST_BPS / 10000.0
        equity *= 1.0 + cost_return

        intraday_return = sum(
            weight * (_asset_return(data, asset, "close", index) / _asset_return(data, asset, "open", index) - 1.0)
            for asset, weight in weights.items()
        )
        equity *= 1.0 + intraday_return
        full_day_return = (1.0 + gap_return) * (1.0 + cost_return) * (1.0 + intraday_return) - 1.0
        fill_to_close_return = (1.0 + cost_return) * (1.0 + intraday_return) - 1.0
        voo_return = data.loc[index, "voo_close"] / data.loc[index, "voo_open"] - 1.0 if i == 0 else data.loc[index, "voo_close"] / data.loc[data.index[i - 1], "voo_close"] - 1.0
        rows.append(
            {
                "date": index,
                "strategy_return": full_day_return,
                "fill_to_close_return": fill_to_close_return,
                "voo_return": voo_return,
                "strategy_equity": equity,
                "risk_on": float(active),
                "tqqq_weight": weights["tqqq"],
                "qld_weight": weights["qld"],
                "voo_weight": weights["voo"],
                "turnover": turnover,
                "prior_tqqq_volatility": prior_vol,
                "active_signal_asset": "TQQQ" if active else "VOO",
                "locked_risk_asset": "QLD" if weights["qld"] > 0 else "TQQQ" if weights["tqqq"] > 0 else "VOO",
            }
        )
        previous_weights = weights
        previous_active = active
    return pd.DataFrame(rows).set_index("date")


def build_tables(data: pd.DataFrame, baseline_result) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.DataFrame]:
    rows: list[dict[str, object]] = []
    frames: dict[str, pd.DataFrame] = {}
    event_rows: list[dict[str, object]] = []
    for spec in LOW_TRADE_POLICIES:
        if spec.mode == "current":
            frame = simulate_policy(data, baseline_result.frame, next(s for s in POLICIES if s.key == "current_tqqq"))
        else:
            frame = simulate_entry_locked_policy(data, baseline_result.frame, spec)
        frames[spec.key] = frame
        score = _score_frame(frame)
        rebalance_days = int((frame["turnover"] > 1e-12).sum())
        rows.append({"Policy": spec.label, "Key": spec.key, "Mode": spec.mode, "Rebalance days": rebalance_days, "Turnover": float(frame["turnover"].sum()), "Rotation-equivalent turnover": float(frame["turnover"].sum() / 2.0), **score})
        for index, event in frame.loc[frame["turnover"] > 1e-12].iterrows():
            event_rows.append({"Policy": spec.label, "Policy key": spec.key, "Date": index.date(), "Turnover": float(event["turnover"]), "TQQQ weight": float(event["tqqq_weight"]), "QLD weight": float(event["qld_weight"]), "Locked risk asset": event.get("locked_risk_asset", "TQQQ" if event["tqqq_weight"] > 0 else "VOO"), "Prior TQQQ volatility %": float(event["prior_tqqq_volatility"] * 100) if pd.notna(event["prior_tqqq_volatility"]) else np.nan})
    return pd.DataFrame(rows), frames, pd.DataFrame(event_rows)


def _engine_result_frame(data: pd.DataFrame, result) -> pd.DataFrame:
    """Adapt an engine result to the comparison scorer's common schema."""
    frame = result.frame.copy()
    frame["risk_on"] = (frame["active_asset"] == "TQQQ").astype(float)
    frame["tqqq_weight"] = frame["risk_on"]
    frame["qld_weight"] = 0.0
    frame["voo_weight"] = 1.0 - frame["risk_on"]
    frame["prior_tqqq_volatility"] = _prior_realized_volatility(data, "tqqq").reindex(frame.index)
    frame["turnover"] = frame["tqqq_weight"].diff().abs().fillna(frame["tqqq_weight"].abs()) * 2.0
    frame["fill_to_close_return"] = frame["strategy_return"]
    frame["active_signal_asset"] = np.where(frame["risk_on"] > 0, "TQQQ", "VOO")
    frame["locked_risk_asset"] = frame["active_signal_asset"]
    return frame


def build_exit_tables(data: pd.DataFrame, baseline_result) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    rows: list[dict[str, object]] = []
    frames: dict[str, pd.DataFrame] = {}
    for key, label, exit_mode in EXIT_POLICIES:
        if key == "exit_current":
            result = baseline_result
        else:
            result = simulate_strategy(
                data,
                ResearchConfig(cost_bps_per_leg=TRANSACTION_COST_BPS, exit_mode=exit_mode),
            )
        frame = _engine_result_frame(data, result)
        frames[key] = frame
        score = _score_frame(frame)
        rows.append(
            {
                "Policy": label,
                "Key": key,
                "Exit mode": exit_mode,
                "Rebalance days": int((frame["turnover"] > 1e-12).sum()),
                "Rotation-equivalent turnover": float(frame["turnover"].sum() / 2.0),
                "Fills": int(len(result.fills)),
                **score,
            }
        )
    return pd.DataFrame(rows), frames


def build_report(
    output: Path,
    data: pd.DataFrame,
    table: pd.DataFrame,
    walk_forward: pd.DataFrame,
    exit_table: pd.DataFrame,
    exit_walk_forward: pd.DataFrame,
) -> None:
    baseline = table.loc[table["Key"] == "current_tqqq"].iloc[0]
    candidates = table.loc[
        (table["Key"] != "current_tqqq")
        & (table["CAGR %"] >= baseline["CAGR %"])
        & (table["Max drawdown %"] >= baseline["Max drawdown %"])
    ]
    fold_summary = walk_forward.groupby("Policy key")["Test excess %"].agg(["count", lambda values: float((values > 0).mean() * 100), "mean", "min"]).rename(columns={"<lambda_0>": "positive_fold_pct", "mean": "mean_excess", "min": "worst_excess"})
    exit_fold_summary = exit_walk_forward.groupby("Policy key")["Test excess %"].agg(["count", lambda values: float((values > 0).mean() * 100), "mean", "min"]).rename(columns={"<lambda_0>": "positive_fold_pct", "mean": "mean_excess", "min": "worst_excess"})
    current_exit = exit_table.loc[exit_table["Key"] == "exit_current"].iloc[0]
    trend_failure = exit_table.loc[exit_table["Key"] == "exit_trend_failure"].iloc[0]
    immediate_trail = exit_table.loc[exit_table["Key"] == "exit_immediate_trail"].iloc[0]
    lines = [
        "# Low-trading satellite strategy comparison",
        "",
        f"Data: {data.index[0].date()} through {data.index[-1].date()} ({len(data):,} common sessions including QLD)",
        f"Execution: same completed daily signal and next-session open; {TRANSACTION_COST_BPS:g} bps per traded weight-leg equivalent",
        "",
        "## Conclusion",
        "",
        "Entry-locked policies materially reduce operational activity because the volatility decision is made once at the TQQQ entry and held until the existing exit signal. They are the right family to pursue for an investor who does not want daily management.",
        "",
        f"The current strategy has {int(baseline['Rebalance days'])} rebalance days. The entry-locked volatility candidates also use the same entry/exit events, so they do not add continuous daily rebalancing. Their historical risk/return results are shown below; none should be promoted without a clean validation period.",
        "",
        "## Comparison",
        "",
        _markdown_table(table[["Policy", "Rebalance days", "Rotation-equivalent turnover", "CAGR %", "Max drawdown %", "Sharpe", "Excess vs VOO %"]]),
        "",
        "## Walk-forward consistency",
        "",
        _markdown_table(fold_summary.reset_index()),
        "",
        "## Low-attention exit-rule experiment",
        "",
        "The entry-locked sizing tests keep the current exit rule fixed. Because exit timing is the other major source of operator burden, this separate experiment changes only the exit rule while leaving the entry signal, next-open execution, and cost model fixed.",
        "",
        _markdown_table(exit_table[["Policy", "Rebalance days", "Fills", "CAGR %", "Max drawdown %", "Sharpe", "Excess vs VOO %"]]),
        "",
        _markdown_table(exit_fold_summary.reset_index()),
        "",
        f"The trend-failure exit produced {int(trend_failure['Rebalance days'])} rebalance days over the full sample (about {int(trend_failure['Rebalance days']) / max((data.index[-1] - data.index[0]).days / 365.25, 1):.1f} per year), versus {int(current_exit['Rebalance days'])} for the current rule. It improved historical CAGR from {current_exit['CAGR %']:.2f}% to {trend_failure['CAGR %']:.2f}% and reduced maximum drawdown from {current_exit['Max drawdown %']:.2f}% to {trend_failure['Max drawdown %']:.2f}%, but it is more reactive and must pass the same frozen validation process.",
        "",
        f"The immediate trailing exit reduced maximum drawdown to {immediate_trail['Max drawdown %']:.2f}% but also reduced CAGR to {immediate_trail['CAGR %']:.2f}% and required {int(immediate_trail['Rebalance days'])} rebalance days. It is a risk-control option, not the lead return candidate.",
        "",
        "## Practical recommendation",
        "",
        "Use a two-track shortlist. For the fewest decisions, advance entry-locked 60% sizing as the primary risk-reduction challenger and entry-locked 50% sizing as the more conservative challenger; both preserve the current 18 event days and make no daily adjustments. Separately, advance trend-failure exit as the return/risk challenger if roughly three rotation days per year is acceptable. Do not choose it from the full-sample result alone.",
        "",
        "Avoid continuous daily volatility targeting for this use case. It had attractive historical statistics, but it requires hundreds of rebalance days and violates the operational constraint.",
        "",
        "## Caveats",
        "",
        "The backtest holds the signal and exit logic constant. Volatility is trailing 20-session realized TQQQ volatility, shifted so only information available before entry is used. A weight change is modeled as a buy/sell exposure adjustment and includes transaction costs, but actual order count, spreads, taxes, and partial-fill behavior still need paper records.",
    ]
    (output / "low_trade_comparison.md").write_text("\n".join(lines), encoding="utf-8")


def run(start: str, end: str, output: Path, snapshot: Path | None = None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    data = load_comparison_data(pd.Timestamp(start), pd.Timestamp(end), snapshot)
    baseline = simulate_strategy(data, ResearchConfig(cost_bps_per_leg=TRANSACTION_COST_BPS))
    table, frames, events = build_tables(data, baseline)
    folds = build_walk_forward_table(data, frames)
    exit_table, exit_frames = build_exit_tables(data, baseline)
    exit_folds = build_walk_forward_table(data, exit_frames)
    table.to_csv(output / "policy_comparison.csv", index=False)
    folds.to_csv(output / "policy_walk_forward.csv", index=False)
    events.to_csv(output / "rebalance_events.csv", index=False)
    exit_table.to_csv(output / "exit_policy_comparison.csv", index=False)
    exit_folds.to_csv(output / "exit_policy_walk_forward.csv", index=False)
    (output / "comparison_manifest.json").write_text(json.dumps({"code_revision": _git_revision(), "start": data.index[0].date().isoformat(), "end": data.index[-1].date().isoformat(), "rows": int(len(data)), "transaction_cost_bps": TRANSACTION_COST_BPS, "data_sha256_csv": hashlib.sha256(data.to_csv(date_format="%Y-%m-%d").encode("utf-8")).hexdigest()}, indent=2, sort_keys=True), encoding="utf-8")
    build_report(output, data, table, folds, exit_table, exit_folds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare entry-locked low-trading satellite policies.")
    parser.add_argument("--start", default="2010-09-09")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--output", default="../research_reports/low_trade_comparison")
    parser.add_argument("--snapshot", default="../research_reports/latest/data_snapshot.csv")
    args = parser.parse_args()
    run(args.start, args.end, Path(args.output), Path(args.snapshot))
