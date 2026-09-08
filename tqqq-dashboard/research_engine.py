"""Event-driven research engine for the dedicated VOO/TQQQ account.

The engine is intentionally small and explicit. Signals are made after a
completed daily bar; orders are filled later according to the selected
execution scenario. The same engine produces portfolio equity, fills, and the
paired VOO episode ledger so research pages cannot silently use different
accounting rules.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from typing import Literal

import numpy as np
import pandas as pd

from play_the_dip_logic import DEFENSIVE_ASSET, INITIAL_CAPITAL, annualized_return, sharpe_ratio


Asset = Literal["VOO", "TQQQ"]
FillType = Literal["open", "close"]


REQUIRED_COLUMNS = {
    "tqqq_open",
    "tqqq_close",
    "voo_open",
    "voo_close",
    "spx_close",
}


@dataclass(frozen=True)
class ExecutionScenario:
    key: str
    label: str
    delay_sessions: int
    fill_type: FillType
    modeled_intraday: bool = False


EXECUTION_SCENARIOS: dict[str, ExecutionScenario] = {
    "next_open": ExecutionScenario("next_open", "Next session open", 1, "open"),
    "next_close": ExecutionScenario("next_close", "Next session close", 1, "close"),
    "second_open": ExecutionScenario("second_open", "Second following session open", 2, "open"),
}


@dataclass(frozen=True)
class ResearchConfig:
    sma_window: int = 200
    upper_band: float = 0.01
    lower_band: float = -0.01
    trail_pct: float = 0.10
    exit_mode: str = "ath_trailing_close"
    execution: str = "next_open"
    cost_bps_per_leg: float = 5.0
    slippage_bps_per_leg: float = 0.0
    initial_capital: float = INITIAL_CAPITAL
    tqqq_weight: float = 1.0
    signal_source: str = "spx_close"
    reset_mode: str = "band"
    cooldown_sessions: int = 5

    @property
    def scenario(self) -> ExecutionScenario:
        if self.execution not in EXECUTION_SCENARIOS:
            raise ValueError(f"Unknown execution scenario: {self.execution}")
        return EXECUTION_SCENARIOS[self.execution]


@dataclass
class SimulationResult:
    frame: pd.DataFrame
    fills: pd.DataFrame
    episodes: pd.DataFrame
    config: ResearchConfig
    metadata: dict[str, object]


def validate_market_data(data: pd.DataFrame) -> list[str]:
    issues: list[str] = []
    missing = sorted(REQUIRED_COLUMNS - set(data.columns))
    if missing:
        issues.append(f"Missing columns: {', '.join(missing)}")
    if not isinstance(data.index, pd.DatetimeIndex):
        issues.append("Index must be a DatetimeIndex")
    elif not data.index.is_monotonic_increasing:
        issues.append("Index is not sorted")
    elif data.index.has_duplicates:
        issues.append("Index contains duplicate sessions")
    for column in sorted(REQUIRED_COLUMNS & set(data.columns)):
        if data[column].isna().any():
            issues.append(f"{column} contains missing observations")
        if (data[column] <= 0).any():
            issues.append(f"{column} contains non-positive prices")
    return issues


def _asset_open(data: pd.DataFrame, asset: Asset, index: pd.Timestamp) -> float:
    return float(data.loc[index, "tqqq_open" if asset == "TQQQ" else "voo_open"])


def _asset_close(data: pd.DataFrame, asset: Asset, index: pd.Timestamp) -> float:
    return float(data.loc[index, "tqqq_close" if asset == "TQQQ" else "voo_close"])


def _fill_price(data: pd.DataFrame, asset: Asset, index: pd.Timestamp, fill_type: FillType) -> float:
    return _asset_open(data, asset, index) if fill_type == "open" else _asset_close(data, asset, index)


def _add_return(equity: float, value: float) -> float:
    return equity * (1.0 + value)


def _episode_metrics(
    data: pd.DataFrame,
    entry: dict[str, object],
    exit_fill: dict[str, object] | None,
    entry_equity: float,
    exit_equity: float,
    config: ResearchConfig,
) -> dict[str, object]:
    entry_date = pd.Timestamp(entry["fill_date"])
    exit_date = pd.Timestamp(exit_fill["fill_date"]) if exit_fill else data.index[-1]
    fill_type = config.scenario.fill_type
    entry_price = float(entry["fill_price"])
    exit_price = float(exit_fill["old_fill_price"]) if exit_fill else _asset_close(data, "TQQQ", data.index[-1])
    status = "Closed" if exit_fill else "Open"

    voo_entry = _fill_price(data, "VOO", entry_date, fill_type)
    voo_exit = _fill_price(data, "VOO", exit_date, fill_type) if exit_fill else _asset_close(data, "VOO", data.index[-1])
    tqqq_gross = exit_price / entry_price - 1.0
    voo_hold = voo_exit / voo_entry - 1.0
    strategy_net = exit_equity / entry_equity - 1.0

    window = data.loc[(data.index >= entry_date) & (data.index <= exit_date)]
    close_excursion = window["tqqq_close"] / entry_price - 1.0
    high_excursion = window["tqqq_high"] / entry_price - 1.0 if "tqqq_high" in window.columns else close_excursion
    low_excursion = window["tqqq_low"] / entry_price - 1.0 if "tqqq_low" in window.columns else close_excursion

    return {
        "Status": status,
        "Entry signal date": entry["signal_date"],
        "Entry fill date": entry_date.date(),
        "Exit signal date": exit_fill["signal_date"] if exit_fill else None,
        "Exit fill date": exit_date.date(),
        "Entry fill": round(entry_price, 4),
        "Exit fill": round(exit_price, 4),
        "TQQQ gross return %": tqqq_gross * 100,
        "VOO hold return %": voo_hold * 100,
        "Strategy net return %": strategy_net * 100,
        "Excess vs VOO %": (strategy_net - voo_hold) * 100,
        "Relative wealth %": ((1.0 + strategy_net) / (1.0 + voo_hold) - 1.0) * 100,
        "Incremental dollars": config.initial_capital * (strategy_net - voo_hold),
        "Duration sessions": int(len(window)),
        "TQQQ max favorable %": float(high_excursion.max() * 100),
        "TQQQ max adverse %": float(low_excursion.min() * 100),
        "Exit reason": exit_fill["reason"] if exit_fill else "Open at evaluation end",
        "Execution": config.scenario.key,
        "Cost bps per leg": config.cost_bps_per_leg,
        "Slippage bps per leg": config.slippage_bps_per_leg,
    }


def _score_series(frame: pd.DataFrame, start: pd.Timestamp | None, end: pd.Timestamp | None, capital: float) -> dict[str, float | int]:
    mask = pd.Series(True, index=frame.index)
    if start is not None:
        mask &= frame.index >= start
    if end is not None:
        mask &= frame.index <= end
    window = frame.loc[mask].copy()
    if window.empty:
        return {
            "Return %": 0.0,
            "VOO return %": 0.0,
            "Excess vs VOO %": 0.0,
            "Annualized %": 0.0,
            "Sharpe": 0.0,
            "Max drawdown %": 0.0,
            "Recovery sessions": 0,
            "TQQQ time %": 0.0,
            "Turnover": 0.0,
            "Sessions": 0,
        }
    strategy_wealth = capital * (1.0 + window["strategy_return"]).cumprod()
    voo_wealth = capital * (1.0 + window["voo_return"]).cumprod()
    peak = strategy_wealth.cummax()
    drawdown = strategy_wealth / peak - 1.0
    trough_date = drawdown.idxmin()
    prior_peak = float(strategy_wealth.loc[:trough_date].max())
    recovery_dates = strategy_wealth.loc[trough_date:][strategy_wealth.loc[trough_date:] >= prior_peak]
    recovery_sessions = int((recovery_dates.index[0] - trough_date).days) if not recovery_dates.empty else -1
    strategy_return = float(strategy_wealth.iloc[-1] / capital - 1.0)
    voo_return = float(voo_wealth.iloc[-1] / capital - 1.0)
    return {
        "Return %": strategy_return * 100,
        "VOO return %": voo_return * 100,
        "Excess vs VOO %": (strategy_return - voo_return) * 100,
        "Annualized %": annualized_return(strategy_wealth) * 100,
        "Sharpe": sharpe_ratio(window["strategy_return"]),
        "Max drawdown %": float(drawdown.min() * 100),
        "Recovery sessions": recovery_sessions,
        "TQQQ time %": float(window["tqqq_weight"].mean() * 100),
        "Turnover": float(window["turnover"].sum()),
        "Sessions": int(len(window)),
    }


def score_window(result: SimulationResult, start: str | pd.Timestamp | None = None, end: str | pd.Timestamp | None = None) -> dict[str, float | int]:
    start_ts = pd.Timestamp(start) if start is not None else None
    end_ts = pd.Timestamp(end) if end is not None else None
    return _score_series(result.frame, start_ts, end_ts, result.config.initial_capital)


def simulate_strategy(data: pd.DataFrame, config: ResearchConfig) -> SimulationResult:
    issues = validate_market_data(data)
    if issues:
        raise ValueError("Invalid market data: " + "; ".join(issues))
    if not 0.0 <= config.tqqq_weight <= 1.0:
        raise ValueError("tqqq_weight must be between 0 and 1")
    if config.reset_mode not in {"band", "trend_recross", "cooldown"}:
        raise ValueError(f"Unknown reset mode: {config.reset_mode}")
    if config.cooldown_sessions < 1:
        raise ValueError("cooldown_sessions must be positive")

    data = data.sort_index().copy()
    scenario = config.scenario
    if config.signal_source not in data.columns:
        raise ValueError(f"Signal source is not present in data: {config.signal_source}")
    data["signal_close"] = data[config.signal_source]
    data["signal_sma"] = data["signal_close"].rolling(config.sma_window).mean()
    data["distance_to_sma"] = data["signal_close"] / data["signal_sma"] - 1.0
    data["prior_ath"] = data["signal_close"].cummax().shift(1)
    data["is_new_ath"] = data["signal_close"] > data["prior_ath"]

    actual_asset: Asset = "VOO"
    pending: dict[str, object] | None = None
    target_long = False
    awaiting_reset = False
    buy_armed = True
    ath_reached = False
    peak_tqqq = np.nan
    cooldown_remaining = 0
    equity = float(config.initial_capital)
    open_episode: dict[str, object] | None = None
    entry_equity = float(config.initial_capital)
    rows: list[dict[str, object]] = []
    fills: list[dict[str, object]] = []
    episodes: list[dict[str, object]] = []

    def execute_switch(index: int, signal_date: pd.Timestamp, target_asset: Asset, reason: str) -> dict[str, object] | None:
        nonlocal actual_asset, equity, open_episode, entry_equity
        if actual_asset == target_asset:
            return None
        fill_date = data.index[index]
        old_asset = actual_asset
        old_fill_price = _fill_price(data, old_asset, fill_date, scenario.fill_type)
        new_fill_price = _fill_price(data, target_asset, fill_date, scenario.fill_type)
        turnover_weight = config.tqqq_weight if target_asset != "VOO" or old_asset == "TQQQ" else 0.0
        total_cost_rate = 2.0 * turnover_weight * (config.cost_bps_per_leg + config.slippage_bps_per_leg) / 10000.0
        equity_before_cost = equity
        equity *= max(0.0, 1.0 - total_cost_rate)
        actual_asset = target_asset
        fill = {
            "signal_date": signal_date.date(),
            "fill_date": fill_date.date(),
            "old_asset": old_asset,
            "new_asset": target_asset,
            "fill_type": scenario.fill_type,
            "fill_price": new_fill_price,
            "old_fill_price": old_fill_price,
            "new_fill_price": new_fill_price,
            "reason": reason,
            "equity_before_cost": equity_before_cost,
            "equity_after_cost": equity,
            "cost_rate": total_cost_rate,
            "turnover_weight": turnover_weight,
        }
        fills.append(fill)
        if target_asset == "TQQQ":
            open_episode = fill
            entry_equity = equity
        elif open_episode is not None:
            episodes.append(_episode_metrics(data, open_episode, fill, entry_equity, equity, config))
            open_episode = None
        return fill

    for i, index in enumerate(data.index):
        row = data.loc[index]
        gap_return = 0.0
        if i > 0:
            previous_index = data.index[i - 1]
            tqqq_gap = _asset_open(data, "TQQQ", index) / _asset_close(data, "TQQQ", previous_index) - 1.0
            voo_gap = _asset_open(data, "VOO", index) / _asset_close(data, "VOO", previous_index) - 1.0
            overnight_weight = config.tqqq_weight if actual_asset == "TQQQ" else 0.0
            gap_return = overnight_weight * tqqq_gap + (1.0 - overnight_weight) * voo_gap
            equity = _add_return(equity, gap_return)

        open_fill: dict[str, object] | None = None
        if pending is not None and pending["fill_index"] == i and scenario.fill_type == "open":
            open_fill = execute_switch(i, pd.Timestamp(pending["signal_date"]), pending["target_asset"], str(pending["reason"]))
            pending = None

        tqqq_intraday = _asset_close(data, "TQQQ", index) / _asset_open(data, "TQQQ", index) - 1.0
        voo_intraday = _asset_close(data, "VOO", index) / _asset_open(data, "VOO", index) - 1.0
        tqqq_weight = config.tqqq_weight if actual_asset == "TQQQ" else 0.0
        intraday_return = tqqq_weight * tqqq_intraday + (1.0 - tqqq_weight) * voo_intraday
        equity = _add_return(equity, intraday_return)

        close_fill: dict[str, object] | None = None
        if pending is not None and pending["fill_index"] == i and scenario.fill_type == "close":
            close_fill = execute_switch(i, pd.Timestamp(pending["signal_date"]), pending["target_asset"], str(pending["reason"]))
            pending = None

        event = ""
        distance = row["distance_to_sma"]
        trailing_stop_level = np.nan
        if pd.notna(distance):
            if target_long:
                if config.exit_mode == "ath_trailing_after_activation":
                    if bool(row["is_new_ath"]) and not ath_reached:
                        ath_reached = True
                        peak_tqqq = float(row["tqqq_close"])
                        event = "New S&P 500 ATH, trailing stop active"
                    elif pd.notna(peak_tqqq):
                        peak_tqqq = max(float(peak_tqqq), float(row["tqqq_close"]))
                else:
                    peak_tqqq = max(float(peak_tqqq), float(row["tqqq_close"])) if pd.notna(peak_tqqq) else float(row["tqqq_close"])
                if bool(row["is_new_ath"]) and not ath_reached:
                    ath_reached = True
                    event = "New S&P 500 ATH, trailing stop active"
                should_exit = False
                if config.exit_mode == "sell_at_ath":
                    should_exit = bool(row["is_new_ath"])
                    if should_exit:
                        event = "Sold on new S&P 500 ATH"
                elif config.exit_mode == "immediate_trailing_close":
                    should_exit = bool(row["tqqq_close"] <= float(peak_tqqq) * (1.0 - config.trail_pct))
                    if should_exit:
                        event = "TQQQ close trailing stop from entry"
                elif config.exit_mode == "ath_trailing_close":
                    should_exit = ath_reached and bool(row["tqqq_close"] <= float(peak_tqqq) * (1.0 - config.trail_pct))
                    if should_exit:
                        event = "TQQQ close trailing stop after ATH"
                elif config.exit_mode == "ath_trailing_after_activation":
                    should_exit = ath_reached and bool(row["tqqq_close"] <= float(peak_tqqq) * (1.0 - config.trail_pct))
                    if should_exit:
                        event = "TQQQ close trailing stop after ATH activation"
                elif config.exit_mode == "trend_failure":
                    should_exit = bool(row["signal_close"] < row["signal_sma"])
                    if should_exit:
                        event = "S&P 500 closed below SMA"
                else:
                    raise ValueError(f"Unknown exit mode: {config.exit_mode}")
                if should_exit:
                    target_long = False
                    awaiting_reset = config.reset_mode != "cooldown"
                    buy_armed = config.reset_mode == "cooldown" and config.cooldown_sessions == 0
                    cooldown_remaining = config.cooldown_sessions if config.reset_mode == "cooldown" else 0
                    ath_reached = False
                    peak_tqqq = np.nan
            if not target_long and cooldown_remaining > 0:
                cooldown_remaining -= 1
                if cooldown_remaining == 0:
                    buy_armed = True
                    event = event or "Cooldown complete"
            reset_threshold = 0.0 if config.reset_mode == "trend_recross" else config.lower_band
            if (not target_long) and awaiting_reset and float(distance) < reset_threshold:
                awaiting_reset = False
                buy_armed = True
                event = event or (
                    "Trend recross reset reached"
                    if config.reset_mode == "trend_recross"
                    else "Reset level reached"
                )
            elif (not target_long) and buy_armed and float(distance) > config.upper_band:
                target_long = True
                buy_armed = False
                cooldown_remaining = 0
                ath_reached = False
                peak_tqqq = float(row["tqqq_close"])
                event = event or "Buy level reached"

        target_asset: Asset = "TQQQ" if target_long else "VOO"
        if target_long and ath_reached and pd.notna(peak_tqqq):
            trailing_stop_level = float(peak_tqqq) * (1.0 - config.trail_pct)
        if pending is not None and pending["target_asset"] != target_asset:
            pending = None
        if pending is None and actual_asset != target_asset and i + scenario.delay_sessions < len(data):
            pending = {
                "signal_date": index,
                "fill_index": i + scenario.delay_sessions,
                "target_asset": target_asset,
                "reason": event or ("Buy signal" if target_asset == "TQQQ" else "Exit signal"),
            }

        rows.append(
            {
                "signal_date": index,
                "signal_event": event,
                "event": event,
                "target_asset": target_asset,
                "active_asset": actual_asset,
                "position": 1.0 if actual_asset == "TQQQ" else 0.0,
                "signal": 1.0 if target_long else 0.0,
                "phase": "Holding TQQQ with trailing stop active" if target_long and ath_reached else "Holding TQQQ" if target_long else "Cooling down after exit" if cooldown_remaining > 0 else "Waiting for reset below lower band" if awaiting_reset else "Armed for next buy signal" if buy_armed else "Defensive allocation",
                "tqqq_weight": tqqq_weight,
                "pending_target": pending["target_asset"] if pending is not None else None,
                "gap_return": gap_return,
                "intraday_return": intraday_return,
                "strategy_equity": equity,
                "is_new_ath": bool(row["is_new_ath"]) if pd.notna(row["is_new_ath"]) else False,
                "spx_sma": row["signal_sma"],
                "spx_close": row["signal_close"],
                "distance_to_sma": distance,
                "tqqq_trailing_stop_level": trailing_stop_level,
                "tqqq_close": row["tqqq_close"],
                "voo_close": row["voo_close"],
                "voo_buy_hold_return": np.nan,
                "fill_event": "open" if open_fill else "close" if close_fill else "",
            }
        )

    result_frame = pd.DataFrame(rows).set_index("signal_date")
    result_frame["voo_return"] = data["voo_close"].pct_change().fillna(data["voo_close"] / data["voo_open"] - 1.0)
    result_frame["tqqq_return"] = data["tqqq_close"].pct_change().fillna(data["tqqq_close"] / data["tqqq_open"] - 1.0)
    result_frame["strategy_return"] = result_frame["strategy_equity"].pct_change().fillna(result_frame["strategy_equity"].iloc[0] / config.initial_capital - 1.0)
    result_frame["voo_equity"] = config.initial_capital * (1.0 + result_frame["voo_return"]).cumprod()
    result_frame["voo_buy_hold_equity"] = result_frame["voo_equity"]
    result_frame["voo_buy_hold_return"] = result_frame["voo_return"]
    result_frame["strategy_peak"] = result_frame["strategy_equity"].cummax()
    result_frame["strategy_drawdown"] = result_frame["strategy_equity"] / result_frame["strategy_peak"] - 1.0
    result_frame["voo_peak"] = result_frame["voo_equity"].cummax()
    result_frame["voo_drawdown"] = result_frame["voo_equity"] / result_frame["voo_peak"] - 1.0
    result_frame["turnover"] = result_frame["tqqq_weight"].diff().abs().fillna(result_frame["tqqq_weight"].abs())

    if open_episode is not None:
        episodes.append(_episode_metrics(data, open_episode, None, entry_equity, equity, config))

    metadata = {
        "data_start": data.index[0].date().isoformat(),
        "data_end": data.index[-1].date().isoformat(),
        "sessions": len(data),
        "execution_label": scenario.label,
        "daily_intraday_proxy": not scenario.modeled_intraday,
    }
    return SimulationResult(
        result_frame,
        pd.DataFrame(fills),
        pd.DataFrame(episodes),
        config,
        metadata,
    )


def score_episodes(episodes: pd.DataFrame, closed_only: bool = False) -> dict[str, float | int]:
    if episodes.empty:
        return {
            "Episodes": 0,
            "Closed episodes": 0,
            "Median excess %": 0.0,
            "Mean excess %": 0.0,
            "Beat VOO %": 0.0,
            "Worst excess %": 0.0,
            "Compounded relative wealth %": 0.0,
        }
    working = episodes.loc[episodes["Status"] == "Closed"].copy() if closed_only else episodes.copy()
    closed = episodes.loc[episodes["Status"] == "Closed"]
    if working.empty:
        return {
            "Episodes": int(len(episodes)),
            "Closed episodes": int(len(closed)),
            "Median excess %": 0.0,
            "Mean excess %": 0.0,
            "Beat VOO %": 0.0,
            "Worst excess %": 0.0,
            "Compounded relative wealth %": 0.0,
        }
    relative = (1.0 + working["Strategy net return %"] / 100.0) / (1.0 + working["VOO hold return %"] / 100.0)
    return {
        "Episodes": int(len(episodes)),
        "Closed episodes": int(len(closed)),
        "Median excess %": float(working["Excess vs VOO %"].median()),
        "Mean excess %": float(working["Excess vs VOO %"].mean()),
        "Beat VOO %": float((working["Excess vs VOO %"] > 0).mean() * 100),
        "Worst excess %": float(working["Excess vs VOO %"].min()),
        "Compounded relative wealth %": float((relative.prod() - 1.0) * 100),
    }


def run_execution_matrix(data: pd.DataFrame, base: ResearchConfig | None = None) -> pd.DataFrame:
    base = base or ResearchConfig()
    rows: list[dict[str, object]] = []
    for scenario in EXECUTION_SCENARIOS.values():
        for cost_bps in (0.0, 5.0, 10.0, 25.0):
            config = replace(base, execution=scenario.key, cost_bps_per_leg=cost_bps)
            result = simulate_strategy(data, config)
            row = {
                "Scenario": scenario.label,
                "Execution key": scenario.key,
                "Cost bps per leg": cost_bps,
            }
            row.update(score_window(result))
            row.update({f"Episode {key}": value for key, value in score_episodes(result.episodes).items()})
            rows.append(row)
    return pd.DataFrame(rows)


def generate_walk_forward_folds(index: pd.DatetimeIndex, initial_years: int = 5, test_years: int = 1) -> list[dict[str, pd.Timestamp]]:
    first_test = index[0] + pd.DateOffset(years=initial_years)
    folds: list[dict[str, pd.Timestamp]] = []
    while first_test < index[-1]:
        test_end = min(first_test + pd.DateOffset(years=test_years) - pd.Timedelta(days=1), index[-1])
        train_end_idx = index.searchsorted(first_test - pd.Timedelta(days=1), side="right") - 1
        test_start_idx = index.searchsorted(first_test, side="left")
        if train_end_idx >= 0 and test_start_idx < len(index):
            folds.append(
                {
                    "train_start": index[0],
                    "train_end": index[train_end_idx],
                    "test_start": index[test_start_idx],
                    "test_end": test_end,
                }
            )
        first_test = first_test + pd.DateOffset(years=test_years)
    return folds


def run_walk_forward(
    data: pd.DataFrame,
    candidates: list[ResearchConfig],
    initial_years: int = 5,
    test_years: int = 1,
) -> pd.DataFrame:
    folds = generate_walk_forward_folds(data.index, initial_years, test_years)
    rows: list[dict[str, object]] = []
    for fold_number, fold in enumerate(folds, start=1):
        train_scores: list[tuple[ResearchConfig, dict[str, float | int]]] = []
        for candidate in candidates:
            train_result = simulate_strategy(data.loc[: fold["train_end"]], candidate)
            train_scores.append(
                (
                    candidate,
                    score_window(train_result, fold["train_start"], fold["train_end"]),
                )
            )
        train_scores.sort(
            key=lambda item: (
                float(item[1]["Excess vs VOO %"]),
                float(item[1]["Max drawdown %"]),
            ),
            reverse=True,
        )
        selected_config, train_score = train_scores[0]
        test_result = simulate_strategy(data.loc[: fold["test_end"]], selected_config)
        test_score = score_window(test_result, fold["test_start"], fold["test_end"])
        rows.append(
            {
                "Fold": fold_number,
                "Train start": fold["train_start"].date(),
                "Train end": fold["train_end"].date(),
                "Test start": fold["test_start"].date(),
                "Test end": fold["test_end"].date(),
                "Selected SMA": selected_config.sma_window,
                "Selected upper %": selected_config.upper_band * 100,
                "Selected lower %": selected_config.lower_band * 100,
                "Selected exit": selected_config.exit_mode,
                "Train excess %": train_score["Excess vs VOO %"],
                "Test excess %": test_score["Excess vs VOO %"],
                "Test return %": test_score["Return %"],
                "Test VOO return %": test_score["VOO return %"],
                "Test annualized %": test_score["Annualized %"],
                "Test Sharpe": test_score["Sharpe"],
                "Test max drawdown %": test_score["Max drawdown %"],
                "Test TQQQ time %": test_score["TQQQ time %"],
                "Test turnover": test_score["Turnover"],
                "Test sessions": test_score["Sessions"],
            }
        )
    return pd.DataFrame(rows)


def summarize_return_concentration(frame: pd.DataFrame) -> dict[str, float]:
    returns = frame["strategy_return"].astype(float)
    if returns.empty:
        return {"Largest daily contribution %": 0.0, "Top 5 daily contribution %": 0.0}
    positive = returns.sort_values(ascending=False)
    total = float((1.0 + returns).prod() - 1.0)
    if total == 0:
        return {"Largest daily contribution %": 0.0, "Top 5 daily contribution %": 0.0}
    return {
        "Largest daily contribution %": float(positive.iloc[0] / total * 100),
        "Top 5 daily contribution %": float(positive.head(5).sum() / total * 100),
    }


def bootstrap_episode_relative_wealth(
    episodes: pd.DataFrame,
    repetitions: int = 2000,
    seed: int = 7,
) -> dict[str, float | int | str]:
    closed = episodes.loc[episodes["Status"] == "Closed"].copy()
    if closed.empty:
        return {"method": "episode bootstrap", "episodes": 0, "repetitions": 0, "p05 %": 0.0, "median %": 0.0, "p95 %": 0.0}
    relative = ((1.0 + closed["Strategy net return %"] / 100.0) / (1.0 + closed["VOO hold return %"] / 100.0)).to_numpy(float)
    rng = np.random.default_rng(seed)
    draws = rng.choice(relative, size=(repetitions, len(relative)), replace=True)
    wealth = draws.prod(axis=1) - 1.0
    return {
        "method": "episode bootstrap with replacement",
        "episodes": int(len(relative)),
        "repetitions": int(repetitions),
        "p05 %": float(np.quantile(wealth, 0.05) * 100),
        "median %": float(np.quantile(wealth, 0.50) * 100),
        "p95 %": float(np.quantile(wealth, 0.95) * 100),
    }


def bootstrap_block_relative_wealth(
    frame: pd.DataFrame,
    block_sessions: int = 21,
    repetitions: int = 1000,
    seed: int = 7,
) -> dict[str, float | int | str]:
    relative_returns = ((1.0 + frame["strategy_return"]) / (1.0 + frame["voo_return"]) - 1.0).to_numpy(float)
    if len(relative_returns) < block_sessions:
        return {"method": "synchronized block bootstrap", "sessions": int(len(relative_returns)), "repetitions": 0, "p05 %": 0.0, "median %": 0.0, "p95 %": 0.0, "block sessions": block_sessions}
    rng = np.random.default_rng(seed)
    starts = np.arange(0, len(relative_returns) - block_sessions + 1)
    blocks_needed = int(np.ceil(len(relative_returns) / block_sessions))
    results = []
    for _ in range(repetitions):
        selected = rng.choice(starts, size=blocks_needed, replace=True)
        sample = np.concatenate([relative_returns[start : start + block_sessions] for start in selected])[: len(relative_returns)]
        results.append(float(np.prod(1.0 + sample) - 1.0))
    return {
        "method": "synchronized block bootstrap",
        "sessions": int(len(relative_returns)),
        "repetitions": int(repetitions),
        "block sessions": int(block_sessions),
        "p05 %": float(np.quantile(results, 0.05) * 100),
        "median %": float(np.quantile(results, 0.50) * 100),
        "p95 %": float(np.quantile(results, 0.95) * 100),
    }


def build_data_manifest(
    data: pd.DataFrame,
    source: str = "yfinance",
    provider_version: str | None = None,
    code_revision: str | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    serialized = data.to_csv(index=True, date_format="%Y-%m-%d").encode("utf-8")
    return {
        "run_id": run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "provider_version": provider_version,
        "code_revision": code_revision,
        "timezone": "America/New_York market sessions represented by normalized dates",
        "start": data.index[0].date().isoformat() if not data.empty else None,
        "end": data.index[-1].date().isoformat() if not data.empty else None,
        "rows": int(len(data)),
        "columns": list(data.columns),
        "missing_by_column": {column: int(data[column].isna().sum()) for column in data.columns},
        "sha256_csv": hashlib.sha256(serialized).hexdigest(),
        "adjustment_note": "Prices are auto-adjusted by yfinance; fund distributions and splits are embedded in adjusted prices.",
    }


def write_data_manifest(manifest: dict[str, object], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
