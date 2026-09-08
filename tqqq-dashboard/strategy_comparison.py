"""Compare fixed, predeclared satellite policies against the current TQQQ rule.

This module deliberately keeps the existing signal and next-open timing fixed.
The alternatives change only the risk-on exposure or the risk-on instrument so
that a lower drawdown is not accidentally purchased by changing several rules
at once.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import yfinance as yf

from play_the_dip_logic import INITIAL_CAPITAL, annualized_return, download_market_data, sharpe_ratio
from research_engine import ResearchConfig, generate_walk_forward_folds, score_window, simulate_strategy


TRANSACTION_COST_BPS = 5.0
SLIPPAGE_BPS = 0.0
ASSETS = ("tqqq", "qld", "voo")


@dataclass(frozen=True)
class PolicySpec:
    key: str
    label: str
    mode: str
    target_vol: float | None = None
    min_weight: float = 0.25
    volatility_threshold: float | None = None
    fixed_weight: float | None = None


POLICIES: tuple[PolicySpec, ...] = (
    PolicySpec("current_tqqq", "Current strategy: 100% TQQQ risk-on", "current"),
    PolicySpec("tqqq_target_60", "TQQQ volatility target 60%", "tqqq_target", target_vol=0.60),
    PolicySpec("tqqq_target_50", "TQQQ volatility target 50%", "tqqq_target", target_vol=0.50),
    PolicySpec("tqqq_target_40", "TQQQ volatility target 40%", "tqqq_target", target_vol=0.40),
    PolicySpec("tqqq_target_30", "TQQQ volatility target 30%", "tqqq_target", target_vol=0.30),
    PolicySpec("tqqq_high_vol_half", "TQQQ half-size when prior volatility exceeds 60%", "tqqq_filter", volatility_threshold=0.60, fixed_weight=0.50),
    PolicySpec("tqqq_half", "50% TQQQ / 50% VOO risk-on", "fixed_tqqq", fixed_weight=0.50),
    PolicySpec("qld_same_signal", "QLD instead of TQQQ, same signal and timing", "qld"),
    PolicySpec("tqqq_qld_mix", "50% TQQQ / 50% QLD risk-on", "mix_tqqq_qld"),
    PolicySpec("leverage_ladder", "TQQQ in calm conditions, QLD in high volatility", "ladder", volatility_threshold=0.60),
)


def _git_revision() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def _load_qld(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    raw = yf.download(
        "QLD",
        start=start.strftime("%Y-%m-%d"),
        end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError("No QLD data returned from yfinance.")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    frame = raw.rename(
        columns={
            "Open": "qld_open",
            "High": "qld_high",
            "Low": "qld_low",
            "Close": "qld_close",
        }
    )
    frame.index = pd.to_datetime(frame.index)
    return frame[["qld_open", "qld_high", "qld_low", "qld_close"]].dropna().sort_index()


def load_comparison_data(
    start: pd.Timestamp,
    end: pd.Timestamp,
    snapshot: Path | None = None,
) -> pd.DataFrame:
    if snapshot is not None and snapshot.exists():
        base = pd.read_csv(snapshot, index_col=0, parse_dates=True)
        base.index.name = None
        base = base.loc[(base.index >= start) & (base.index <= end)]
    else:
        base = download_market_data(start, end)
    qld = _load_qld(start, end)
    data = base.join(qld, how="inner").dropna().sort_index()
    if data.empty:
        raise ValueError("No common data remains after adding QLD.")
    return data


def _asset_return(data: pd.DataFrame, asset: str, field: str, index: pd.Timestamp) -> float:
    return float(data.loc[index, f"{asset}_{field}"])


def _prior_realized_volatility(data: pd.DataFrame, asset: str = "tqqq", lookback: int = 20) -> pd.Series:
    daily_returns = data[f"{asset}_close"].pct_change()
    return daily_returns.rolling(lookback).std().shift(1) * np.sqrt(252)


def _weights_for_policy(
    spec: PolicySpec,
    active_risk_on: bool,
    prior_volatility: float,
) -> dict[str, float]:
    weights = {"tqqq": 0.0, "qld": 0.0, "voo": 1.0}
    if not active_risk_on:
        return weights

    if spec.mode == "current":
        weights["tqqq"] = 1.0
        weights["voo"] = 0.0
    elif spec.mode == "tqqq_target":
        if not np.isfinite(prior_volatility) or prior_volatility <= 0:
            weight = 1.0
        else:
            weight = min(1.0, float(spec.target_vol) / prior_volatility)
        weight = max(float(spec.min_weight), weight)
        weights["tqqq"] = weight
        weights["voo"] = 1.0 - weight
    elif spec.mode == "tqqq_filter":
        weight = 1.0 if not np.isfinite(prior_volatility) or prior_volatility <= float(spec.volatility_threshold) else float(spec.fixed_weight)
        weights["tqqq"] = weight
        weights["voo"] = 1.0 - weight
    elif spec.mode == "fixed_tqqq":
        weights["tqqq"] = float(spec.fixed_weight)
        weights["voo"] = 1.0 - float(spec.fixed_weight)
    elif spec.mode == "qld":
        weights["qld"] = 1.0
        weights["voo"] = 0.0
    elif spec.mode == "mix_tqqq_qld":
        weights["tqqq"] = 0.5
        weights["qld"] = 0.5
        weights["voo"] = 0.0
    elif spec.mode == "ladder":
        if np.isfinite(prior_volatility) and prior_volatility > float(spec.volatility_threshold):
            weights["qld"] = 1.0
            weights["voo"] = 0.0
        else:
            weights["tqqq"] = 1.0
            weights["voo"] = 0.0
    else:
        raise ValueError(f"Unknown policy mode: {spec.mode}")
    return weights


def _score_frame(frame: pd.DataFrame, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None) -> dict[str, float | int]:
    mask = pd.Series(True, index=frame.index)
    if start is not None:
        mask &= frame.index >= start
    if end is not None:
        mask &= frame.index <= end
    window = frame.loc[mask]
    if window.empty:
        return {"Return %": 0.0, "VOO return %": 0.0, "Excess vs VOO %": 0.0, "CAGR %": 0.0, "Volatility %": 0.0, "Sharpe": 0.0, "Sortino": 0.0, "Max drawdown %": 0.0, "Calmar": 0.0, "Recovery days": 0.0, "Risk-on time %": 0.0, "Average TQQQ weight %": 0.0, "Turnover": 0.0, "Sessions": 0}
    strategy_returns = window["strategy_return"].astype(float)
    voo_returns = window["voo_return"].astype(float)
    strategy_wealth = INITIAL_CAPITAL * (1.0 + strategy_returns).cumprod()
    voo_wealth = INITIAL_CAPITAL * (1.0 + voo_returns).cumprod()
    drawdown = strategy_wealth / strategy_wealth.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    trough_date = drawdown.idxmin()
    prior_peak = float(strategy_wealth.loc[:trough_date].max())
    recovery = strategy_wealth.loc[trough_date:][strategy_wealth.loc[trough_date:] >= prior_peak]
    recovery_days = float((recovery.index[0] - trough_date).days) if not recovery.empty else -1.0
    downside = strategy_returns.where(strategy_returns < 0).std()
    sortino = float(strategy_returns.mean() / downside * np.sqrt(252)) if downside and np.isfinite(downside) else 0.0
    cagr = annualized_return(strategy_wealth)
    return {
        "Return %": float((strategy_wealth.iloc[-1] / INITIAL_CAPITAL - 1.0) * 100),
        "VOO return %": float((voo_wealth.iloc[-1] / INITIAL_CAPITAL - 1.0) * 100),
        "Excess vs VOO %": float((strategy_wealth.iloc[-1] / INITIAL_CAPITAL - voo_wealth.iloc[-1] / INITIAL_CAPITAL) * 100),
        "CAGR %": float(cagr * 100),
        "Volatility %": float(strategy_returns.std() * np.sqrt(252) * 100),
        "Sharpe": float(sharpe_ratio(strategy_returns)),
        "Sortino": sortino,
        "Max drawdown %": max_drawdown * 100,
        "Calmar": float(cagr / abs(max_drawdown)) if max_drawdown < 0 else 0.0,
        "Recovery days": recovery_days,
        "Risk-on time %": float(window["risk_on"].mean() * 100),
        "Average TQQQ weight %": float(window["tqqq_weight"].mean() * 100),
        "Turnover": float(window["turnover"].sum()),
        "Sessions": int(len(window)),
    }


def simulate_policy(data: pd.DataFrame, reference_frame: pd.DataFrame, spec: PolicySpec) -> pd.DataFrame:
    if spec.mode == "current":
        frame = reference_frame.copy()
        frame["strategy_return"] = frame["strategy_return"].astype(float)
        frame["voo_return"] = data["voo_close"].pct_change().fillna(data["voo_close"] / data["voo_open"] - 1.0)
        frame["strategy_equity"] = INITIAL_CAPITAL * (1.0 + frame["strategy_return"]).cumprod()
        frame["risk_on"] = (frame["active_asset"] == "TQQQ").astype(float)
        frame["tqqq_weight"] = frame["risk_on"]
        frame["qld_weight"] = 0.0
        frame["voo_weight"] = 1.0 - frame["risk_on"]
        frame["prior_tqqq_volatility"] = _prior_realized_volatility(data, "tqqq").reindex(frame.index)
        frame["turnover"] = frame["tqqq_weight"].diff().abs().fillna(frame["tqqq_weight"].abs()) * 2.0
        frame["fill_to_close_return"] = frame["strategy_return"]
        return frame

    volatility = _prior_realized_volatility(data, "tqqq")
    previous_weights = {"tqqq": 0.0, "qld": 0.0, "voo": 1.0}
    equity = INITIAL_CAPITAL
    rows: list[dict[str, object]] = []
    for i, index in enumerate(data.index):
        active_risk_on = reference_frame.loc[index, "active_asset"] == "TQQQ"
        prior_vol = float(volatility.loc[index]) if pd.notna(volatility.loc[index]) else np.nan
        weights = _weights_for_policy(spec, active_risk_on, prior_vol)

        gap_return = 0.0
        if i > 0:
            previous = data.index[i - 1]
            for asset, weight in previous_weights.items():
                gap_return += weight * (_asset_return(data, asset, "open", index) / _asset_return(data, asset, "close", previous) - 1.0)
            equity *= 1.0 + gap_return

        turnover = sum(abs(weights[asset] - previous_weights[asset]) for asset in ASSETS)
        cost_return = -turnover * (TRANSACTION_COST_BPS + SLIPPAGE_BPS) / 10000.0
        equity *= 1.0 + cost_return

        intraday_return = 0.0
        for asset, weight in weights.items():
            intraday_return += weight * (_asset_return(data, asset, "close", index) / _asset_return(data, asset, "open", index) - 1.0)
        equity *= 1.0 + intraday_return
        full_day_return = (1.0 + gap_return) * (1.0 + cost_return) * (1.0 + intraday_return) - 1.0
        fill_to_close_return = (1.0 + cost_return) * (1.0 + intraday_return) - 1.0
        rows.append(
            {
                "date": index,
                "strategy_return": full_day_return,
                "fill_to_close_return": fill_to_close_return,
                "voo_return": data.loc[index, "voo_close"] / data.loc[index, "voo_open"] - 1.0 if i == 0 else data.loc[index, "voo_close"] / data.loc[index, "voo_open"] * data.loc[index, "voo_open"] / data.loc[data.index[i - 1], "voo_close"] - 1.0,
                "strategy_equity": equity,
                "risk_on": float(active_risk_on),
                "tqqq_weight": weights["tqqq"],
                "qld_weight": weights["qld"],
                "voo_weight": weights["voo"],
                "turnover": turnover,
                "prior_tqqq_volatility": prior_vol,
                "active_signal_asset": "TQQQ" if active_risk_on else "VOO",
            }
        )
        previous_weights = weights
    return pd.DataFrame(rows).set_index("date")


def build_episode_ledger(
    data: pd.DataFrame,
    reference_result,
    policy_frame: pd.DataFrame,
    policy: PolicySpec,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for episode in reference_result.episodes.to_dict("records"):
        entry_date = pd.Timestamp(episode["Entry fill date"])
        exit_date = pd.Timestamp(episode["Exit fill date"])
        if exit_date not in policy_frame.index:
            exit_date = policy_frame.index[-1]
        window = policy_frame.loc[(policy_frame.index >= entry_date) & (policy_frame.index <= exit_date)]
        if window.empty:
            continue
        returns = window["fill_to_close_return"].astype(float).copy()
        if len(returns) > 1:
            returns.iloc[1:] = window["strategy_return"].iloc[1:].astype(float)
        policy_return = float((1.0 + returns).prod() - 1.0)
        entry_price = float(data.loc[entry_date, "voo_open"])
        if episode["Status"] == "Closed":
            voo_hold = float(data.loc[exit_date, "voo_open"] / entry_price - 1.0)
        else:
            voo_hold = float(data.loc[exit_date, "voo_close"] / entry_price - 1.0)
        rows.append(
            {
                "Policy": policy.label,
                "Status": episode["Status"],
                "Entry fill date": entry_date.date(),
                "Exit fill date": exit_date.date(),
                "Strategy return %": policy_return * 100,
                "VOO hold return %": voo_hold * 100,
                "Excess vs VOO %": (policy_return - voo_hold) * 100,
                "Relative wealth %": ((1.0 + policy_return) / (1.0 + voo_hold) - 1.0) * 100,
                "TQQQ weight average %": float(window["tqqq_weight"].mean() * 100),
                "QLD weight average %": float(window["qld_weight"].mean() * 100),
                "Prior volatility max %": float(window["prior_tqqq_volatility"].max() * 100) if window["prior_tqqq_volatility"].notna().any() else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_policy_tables(data: pd.DataFrame, baseline_result) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.DataFrame]:
    rows: list[dict[str, object]] = []
    frames: dict[str, pd.DataFrame] = {}
    episodes: list[pd.DataFrame] = []
    baseline_frame = baseline_result.frame.copy()
    for policy in POLICIES:
        frame = simulate_policy(data, baseline_frame, policy)
        frames[policy.key] = frame
        score = _score_frame(frame)
        rows.append({"Policy": policy.label, "Key": policy.key, "Mode": policy.mode, **score})
        episode = build_episode_ledger(data, baseline_result, frame, policy)
        if not episode.empty:
            episodes.append(episode)
    return pd.DataFrame(rows), frames, pd.concat(episodes, ignore_index=True) if episodes else pd.DataFrame()


def build_walk_forward_table(data: pd.DataFrame, frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    folds = generate_walk_forward_folds(data.index, initial_years=5, test_years=1)
    rows: list[dict[str, object]] = []
    for number, fold in enumerate(folds, start=1):
        for key, frame in frames.items():
            score = _score_frame(frame, fold["test_start"], fold["test_end"])
            rows.append(
                {
                    "Fold": number,
                    "Policy key": key,
                    "Train end": fold["train_end"].date(),
                    "Test start": fold["test_start"].date(),
                    "Test end": fold["test_end"].date(),
                    "Test excess %": score["Excess vs VOO %"],
                    "Test CAGR %": score["CAGR %"],
                    "Test max drawdown %": score["Max drawdown %"],
                    "Test Sharpe": score["Sharpe"],
                    "Test turnover": score["Turnover"],
                }
            )
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = ["| " + " | ".join(str(column) for column in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in frame.itertuples(index=False, name=None):
        values = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                values.append(f"{value:.2f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def build_report(output: Path, data: pd.DataFrame, policy_table: pd.DataFrame, walk_forward: pd.DataFrame) -> None:
    baseline = policy_table.loc[policy_table["Key"] == "current_tqqq"].iloc[0]
    pareto = policy_table.loc[
        (policy_table["Key"] != "current_tqqq")
        & (policy_table["CAGR %"] >= baseline["CAGR %"])
        & (policy_table["Max drawdown %"] >= baseline["Max drawdown %"])
    ]
    pareto_count = int(len(pareto))
    fold_summary = (
        walk_forward.groupby("Policy key")["Test excess %"]
        .agg(["count", lambda values: float((values > 0).mean() * 100), "mean", "min"])
        .rename(columns={"<lambda_0>": "positive_fold_pct", "mean": "mean_excess", "min": "worst_excess"})
    )
    fold_pivot = walk_forward.pivot(index="Fold", columns="Policy key", values="Test excess %")
    fold_advantage = []
    for key in ("tqqq_target_60", "tqqq_target_50", "tqqq_high_vol_half", "leverage_ladder"):
        if key in fold_pivot.columns:
            difference = fold_pivot[key] - fold_pivot["current_tqqq"]
            fold_advantage.append(
                f"{key}: better than current in {(difference > 1e-9).sum()}/{len(difference)} folds; mean difference {difference.mean():.2f} percentage points"
            )
    lines = [
        "# Satellite strategy comparison",
        "",
        f"Data: {data.index[0].date()} through {data.index[-1].date()} ({len(data):,} common sessions including QLD)",
        f"Execution: completed daily signal, next-session open; {TRANSACTION_COST_BPS:g} bps per traded weight-leg equivalent; no intraday stop assumption",
        "",
        "## Conclusion",
        "",
        f"This fixed comparison produced {pareto_count} alternatives with at least the current CAGR and a less severe maximum drawdown. That is encouraging, but it is not proof of a durable edge: the policies were tested on the same historical sample, and the volatility rules still need a genuinely untouched validation period and real fill data.",
        "",
        "The most credible improvement to investigate next is volatility-aware sizing or a TQQQ/QLD ladder. These reduce exposure when prior TQQQ volatility is high, which is economically plausible and supported by volatility-management research, but the historical results must still survive a frozen walk-forward test and real execution.",
        "",
        "## Policy comparison",
        "",
        _markdown_table(policy_table[["Policy", "CAGR %", "Max drawdown %", "Sharpe", "Sortino", "Excess vs VOO %", "Risk-on time %", "Average TQQQ weight %", "Turnover"]]),
        "",
        "## Walk-forward consistency",
        "",
        _markdown_table(fold_summary.reset_index().rename(columns={"Policy key": "Policy key"})),
        "",
        "Fold-by-fold comparison against current strategy: " + "; ".join(fold_advantage) + ".",
        "",
        "## Pareto result",
        "",
        f"Policies that matched or exceeded the current strategy's CAGR while having a less severe maximum drawdown: {len(pareto)}.",
        (_markdown_table(pareto[["Policy", "CAGR %", "Max drawdown %", "Sharpe"]]) if not pareto.empty else "None in this fixed-rule comparison."),
        "",
        "## Interpretation",
        "",
        "- QLD and QQQ reduce leverage risk, but they should be expected to give up some upside in the strongest trends.",
        "- Volatility targeting can reduce drawdown and improve Sharpe, but it can also cut exposure before a sharp rebound. It is a risk-control candidate, not a guaranteed return enhancer.",
        "- The ladder is attractive operationally because it uses a small number of discrete states rather than continuously changing weights.",
        "- The test holds the signal and timing constant. It does not yet prove that a separately optimized signal would be better.",
        "",
        "## Research context",
        "",
        "TQQQ and QLD are daily-target leveraged ETFs; their multi-day results can differ materially from a simple 3x or 2x multiple because of daily reset and compounding.[1][2] Research on volatility-managed portfolios provides a rationale for reducing exposure when volatility rises, while later work cautions that out-of-sample implementation can be unstable.[3][4] Time-series momentum research supports testing trend persistence, but its original evidence is broader futures markets rather than a guarantee for this ETF rule.[5]",
        "",
        "## Decision",
        "",
        "Keep the current strategy as the reference. Promote no alternative yet. Advance only the volatility-target and TQQQ/QLD-ladder candidates to a second-stage test with preregistered parameters, separate development/validation dates, actual fill records, and a stated drawdown limit.",
        "",
        "## Sources",
        "",
        "1. [ProShares TQQQ](https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq) — daily 3x Nasdaq-100 objective and multi-day divergence warning.",
        "2. [ProShares QLD](https://www.proshares.com/our-etfs/leveraged-and-inverse/qld) — daily 2x Nasdaq-100 objective and compounding warning.",
        "3. [Moreira and Muir, Volatility Managed Portfolios, NBER](https://www.nber.org/papers/w22208) — rationale for reducing risk when volatility is high.",
        "4. [Cederburg et al., On the performance of volatility-managed portfolios](https://www.sciencedirect.com/science/article/pii/S0304405X2030132X) — out-of-sample and implementation caution.",
        "5. [Moskowitz, Ooi, and Pedersen, Time Series Momentum](https://fairmodel.econ.yale.edu/ec439/mosk.pdf) — original trend-persistence evidence across liquid futures.",
    ]
    (output / "strategy_comparison.md").write_text("\n".join(lines), encoding="utf-8")


def run(start: str, end: str, output: Path, snapshot: Path | None = None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    data = load_comparison_data(pd.Timestamp(start), pd.Timestamp(end), snapshot)
    baseline_result = simulate_strategy(data, ResearchConfig(cost_bps_per_leg=TRANSACTION_COST_BPS))
    policy_table, frames, episodes = build_policy_tables(data, baseline_result)
    walk_forward = build_walk_forward_table(data, frames)
    policy_table.to_csv(output / "policy_comparison.csv", index=False)
    walk_forward.to_csv(output / "policy_walk_forward.csv", index=False)
    episodes.to_csv(output / "policy_episode_ledger.csv", index=False)
    metadata = {
        "code_revision": _git_revision(),
        "start": data.index[0].date().isoformat(),
        "end": data.index[-1].date().isoformat(),
        "rows": int(len(data)),
        "transaction_cost_bps": TRANSACTION_COST_BPS,
        "slippage_bps": SLIPPAGE_BPS,
        "policy_definitions": [spec.__dict__ for spec in POLICIES],
        "data_sha256_csv": hashlib.sha256(data.to_csv(date_format="%Y-%m-%d").encode("utf-8")).hexdigest(),
    }
    (output / "comparison_manifest.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    build_report(output, data, policy_table, walk_forward)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare fixed satellite policies against the current TQQQ strategy.")
    parser.add_argument("--start", default="2010-09-09")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--output", default="../research_reports/strategy_comparison")
    parser.add_argument("--snapshot", default="../research_reports/latest/data_snapshot.csv")
    args = parser.parse_args()
    run(args.start, args.end, Path(args.output), Path(args.snapshot))
