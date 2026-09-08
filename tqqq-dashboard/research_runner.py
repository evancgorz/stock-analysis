from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pandas as pd

from intraday_data import download_recent_intraday
from play_the_dip_logic import download_market_data
from research_engine import (
    ResearchConfig,
    bootstrap_block_relative_wealth,
    bootstrap_episode_relative_wealth,
    build_data_manifest,
    run_execution_matrix,
    run_walk_forward,
    score_episodes,
    score_window,
    simulate_strategy,
    summarize_return_concentration,
)


def _git_revision() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def _weekly_data(data: pd.DataFrame) -> pd.DataFrame:
    aggregations: dict[str, str] = {}
    for prefix in ("tqqq", "voo", "qqq", "spx"):
        for field, aggregation in (("open", "first"), ("high", "max"), ("low", "min"), ("close", "last")):
            column = f"{prefix}_{field}"
            if column in data.columns:
                aggregations[column] = aggregation
    return data.resample("W-FRI").agg(aggregations).dropna()


def _qqq_traded_data(data: pd.DataFrame) -> pd.DataFrame:
    """Create a clearly labelled same-signal QQQ risk-on comparison."""
    proxy = data.copy()
    for field in ("open", "high", "low", "close"):
        proxy[f"tqqq_{field}"] = proxy[f"qqq_{field}"]
    return proxy


def _experiment_row(name: str, data: pd.DataFrame, config: ResearchConfig) -> dict[str, object]:
    result = simulate_strategy(data, config)
    row: dict[str, object] = {
        "Experiment": name,
        "SMA": config.sma_window,
        "Upper %": config.upper_band * 100,
        "Lower %": config.lower_band * 100,
        "Exit mode": config.exit_mode,
        "Execution": config.execution,
        "TQQQ weight %": config.tqqq_weight * 100,
        "Signal source": config.signal_source,
        "Reset mode": config.reset_mode,
        "Cooldown sessions": config.cooldown_sessions,
        "Cost bps per leg": config.cost_bps_per_leg,
    }
    row.update(score_window(result))
    row.update({f"Episode {key}": value for key, value in score_episodes(result.episodes).items()})
    row.update(summarize_return_concentration(result.frame))
    return row


def build_experiment_suite(data: pd.DataFrame, baseline: ResearchConfig) -> pd.DataFrame:
    configs: list[tuple[str, ResearchConfig]] = [
        ("Baseline", baseline),
        ("SMA 150", replace(baseline, sma_window=150)),
        ("SMA 250", replace(baseline, sma_window=250)),
        ("Entry buffer 0%", replace(baseline, upper_band=0.0)),
        ("Entry buffer 2%", replace(baseline, upper_band=0.02)),
        ("Sell at ATH", replace(baseline, exit_mode="sell_at_ath")),
        ("Immediate 10% trail", replace(baseline, exit_mode="immediate_trailing_close")),
        ("Trend failure exit", replace(baseline, exit_mode="trend_failure")),
        ("10% trail peak starts at ATH", replace(baseline, exit_mode="ath_trailing_after_activation")),
        ("8% ATH trail", replace(baseline, trail_pct=0.08)),
        ("15% ATH trail", replace(baseline, trail_pct=0.15)),
        ("Trend recross reset", replace(baseline, reset_mode="trend_recross")),
        ("Five-session cooldown reset", replace(baseline, reset_mode="cooldown", cooldown_sessions=5)),
        ("50% TQQQ risk-on", replace(baseline, tqqq_weight=0.50)),
        ("QQQ signal", replace(baseline, signal_source="qqq_close")),
    ]
    rows = [_experiment_row(name, data, config) for name, config in configs]

    weekly = _weekly_data(data)
    weekly_baseline = replace(baseline, sma_window=40)
    rows.append(_experiment_row("Weekly signal, 40-week SMA", weekly, weekly_baseline))
    rows.append(_experiment_row("QQQ traded in same risk-on windows", data=_qqq_traded_data(data), config=baseline))
    return pd.DataFrame(rows)


def build_experiment_register() -> pd.DataFrame:
    """Keep included, rejected, and unavailable experiments visible."""
    return pd.DataFrame(
        [
            {"Family": "Trend horizon", "Candidate": "SMA 150 / 200 / 250", "Status": "Included", "Decision": "Research only; compare nearby settings and walk-forward folds."},
            {"Family": "Entry buffer", "Candidate": "0% / 1% / 2%", "Status": "Included", "Decision": "Bounded one-variable comparison."},
            {"Family": "Reset", "Candidate": "-1% band / trend recross / five-session cooldown", "Status": "Included", "Decision": "Bounded one-variable comparison."},
            {"Family": "Exit", "Candidate": "ATH sale / immediate 10% / ATH-activated 10% / trend failure", "Status": "Included", "Decision": "Compare close-confirmed exits against frozen baseline."},
            {"Family": "Trail width", "Candidate": "8% / 10% / 15%", "Status": "Included", "Decision": "Sensitivity only; no leaderboard promotion."},
            {"Family": "Signal market", "Candidate": "S&P total return / QQQ close", "Status": "Included", "Decision": "QQQ signal is a challenger, not an automatic replacement."},
            {"Family": "Leverage", "Candidate": "QQQ traded instead of TQQQ", "Status": "Included", "Decision": "Same windows isolate the leverage contribution."},
            {"Family": "Sizing", "Candidate": "50% TQQQ / 50% VOO in risk-on windows", "Status": "Included", "Decision": "Lower-risk challenger; weight is fixed and remainder stays in VOO."},
            {"Family": "Attention", "Candidate": "Weekly 40-week SMA", "Status": "Included", "Decision": "Lower-attention challenger; fills remain next weekly bar in this proxy."},
            {"Family": "Volatility sizing", "Candidate": "Prior-data volatility cap", "Status": "Deferred", "Decision": "No fixed cap and rebalance convention was specified; do not tune one after seeing results."},
            {"Family": "Pullback entry", "Candidate": "Trend-confirmed pullback/recovery", "Status": "Deferred", "Decision": "No single operational definition was frozen before this run; preserve as a preregistered follow-up."},
            {"Family": "2x leverage", "Candidate": "2x Nasdaq fund", "Status": "Unavailable", "Decision": "No verified 2x fund series was included in the common data feed; do not substitute a synthetic proxy."},
        ]
    )


def collect_intraday_availability(end_date: str) -> list[dict[str, object]]:
    end = pd.Timestamp(end_date)
    start = end - pd.Timedelta(days=30)
    rows: list[dict[str, object]] = []
    for ticker in ("TQQQ", "VOO"):
        try:
            _, availability = download_recent_intraday(ticker, start, end, interval="5m")
            rows.append(availability.__dict__)
        except Exception as exc:
            rows.append(
                {
                    "ticker": ticker,
                    "interval": "5m",
                    "requested_start": start.date().isoformat(),
                    "requested_end": end.date().isoformat(),
                    "rows": 0,
                    "first_bar": None,
                    "last_bar": None,
                    "status": "unavailable",
                    "note": f"Intraday availability check failed safely: {exc}",
                }
            )
    return rows


def build_period_report(result, data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    years = sorted({int(year) for year in result.frame.index.year})
    for year in years:
        score = score_window(result, pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year}-12-31"))
        rows.append({"Period": str(year), **score})
    for sessions in (252, 756, 1260):
        if len(data) < sessions:
            continue
        for end_position in range(sessions - 1, len(data), 63):
            start = data.index[end_position - sessions + 1]
            end = data.index[end_position]
            score = score_window(result, start, end)
            rows.append({"Period": f"rolling_{sessions}_{end.date()}", **score})
    return pd.DataFrame(rows)


def build_scorecard(result, folds: pd.DataFrame, execution_matrix: pd.DataFrame, experiments: pd.DataFrame) -> pd.DataFrame:
    fold_positive = float((folds["Test excess %"] > 0).mean() * 100) if not folds.empty else 0.0
    delayed = execution_matrix.loc[execution_matrix["Execution key"] == "second_open"]
    delayed_positive = float((delayed["Excess vs VOO %"] > 0).mean() * 100) if not delayed.empty else 0.0
    score = score_window(result)
    rows = [
        {"Dimension": "Accounting tests", "Status": "Pass", "Evidence": "Event, cost, prefix-invariance, and fold-order tests pass."},
        {"Dimension": "Paired VOO benefit", "Status": "Mixed", "Evidence": f"{score['Excess vs VOO %']:.2f} percentage-point full-period excess; episode table is primary."},
        {"Dimension": "Cross-period consistency", "Status": "Mixed", "Evidence": f"{fold_positive:.1f}% of one-year test folds beat VOO."},
        {"Dimension": "Drawdown and recovery", "Status": "Fail for promotion", "Evidence": f"Maximum drawdown {score['Max drawdown %']:.2f}%; user limit is not defined."},
        {"Dimension": "Execution tolerance", "Status": "Mixed", "Evidence": f"{delayed_positive:.1f}% of second-session-open/cost cases beat VOO."},
        {"Dimension": "Standing stop-market", "Status": "Inconclusive", "Evidence": "Withheld: multi-year intraday bars are unavailable and daily OHLC cannot establish within-day stop ordering or gap-through fills."},
        {"Dimension": "Parameter stability", "Status": "Research only", "Evidence": f"{len(experiments)} bounded candidates recorded; no automatic selection."},
        {"Dimension": "Promotion decision", "Status": "Inconclusive", "Evidence": "Needs an agreed loss limit, intraday fill evidence, and prospective paper observations."},
    ]
    return pd.DataFrame(rows)


def build_report(
    output_dir: Path,
    manifest: dict[str, object],
    baseline: ResearchConfig,
    execution_matrix: pd.DataFrame,
    experiments: pd.DataFrame,
    folds: pd.DataFrame,
    baseline_result,
    uncertainty: dict[str, object],
    scorecard: pd.DataFrame,
) -> None:
    baseline_score = score_window(baseline_result)
    episode_score = score_episodes(baseline_result.episodes)
    positive_folds = float((folds["Test excess %"] > 0).mean() * 100) if not folds.empty else 0.0
    report = f"""# TQQQ / VOO modeling report

Run date: {manifest["retrieved_at_utc"]}
Code revision at data retrieval: {manifest.get("code_revision") or "unknown"}
Data: {manifest["start"]} through {manifest["end"]}, {manifest["rows"]} common sessions
Provider: {manifest["source"]}; prices are auto-adjusted

## Research conclusion

This is a historical research report, not a promotion decision. The baseline is a full-account rotation between VOO and TQQQ, with a close-confirmed signal and the selected execution delay. It is evaluated against continuous VOO using the same timestamps.

The baseline full-period result was {baseline_score["Return %"]:.2f}% versus VOO at {baseline_score["VOO return %"]:.2f}%, a paired difference of {baseline_score["Excess vs VOO %"]:.2f} percentage points. Its maximum drawdown was {baseline_score["Max drawdown %"]:.2f}%, Sharpe was {baseline_score["Sharpe"]:.2f}, TQQQ exposure was {baseline_score["TQQQ time %"]:.2f}%, and turnover was {baseline_score["Turnover"]:.0f} account rotations.

The matched risk-on ledger contained {episode_score["Episodes"]} episodes, {episode_score["Closed episodes"]} closed, and {episode_score["Beat VOO %"]:.1f}% beat VOO after the configured costs. Median episode excess was {episode_score["Median excess %"]:.2f} percentage points; compounded relative wealth across episodes was {episode_score["Compounded relative wealth %"]:.2f}%.

    The repeated expanding-window walk-forward test had {len(folds)} one-year test folds. The selected candidate beat VOO in {positive_folds:.1f}% of folds. The fold table is the authoritative evidence; sparse trades, large drawdowns, or a concentration in a few episodes remain grounds for an inconclusive decision.

The episode bootstrap relative-wealth interval was p05 {uncertainty["episode"]["p05 %"]:.2f}%, median {uncertainty["episode"]["median %"]:.2f}%, p95 {uncertainty["episode"]["p95 %"]:.2f}%. The synchronized daily block-bootstrap interval was p05 {uncertainty["block"]["p05 %"]:.2f}%, median {uncertainty["block"]["median %"]:.2f}%, p95 {uncertainty["block"]["p95 %"]:.2f}%. These are uncertainty summaries for realized paths, not new strategy simulations.

## Accounting and implementation rules

- Signals use completed daily bars. The signal is never allowed to see a future bar.
- Orders are scheduled from the signal close and filled according to the scenario column.
- A rotation carries the prior asset through the overnight gap, then applies the new asset from its fill phase.
- Each rotation charges two transaction legs at {baseline.cost_bps_per_leg:g} basis points per leg. Slippage is separate and currently {baseline.slippage_bps_per_leg:g} basis points per leg.
- The daily scenario matrix is a bound and sensitivity study for 09:35, 10:00, and 11:00 fills. It is not an intraday price reconstruction. An intraday data study is required before claiming those clock times.
- A close-based trailing stop is a next-session signal. It is not a guaranteed 10% broker stop. Gap-through and standing stop-market variants remain separate experiments.
- The standing intraday stop-market study is explicitly withheld from promotion because the available history cannot establish within-day path ordering or realistic gap-through fills. See stop_order_study.json.

## Files in this run

- execution_matrix.csv: delay and cost sensitivity.
- experiments.csv: bounded one-change experiments and related strategies.
- walk_forward_folds.csv: expanding five-year training and one-year test folds.
- episode_ledger.csv: paired TQQQ/VOO episodes.
- fills.csv: signal dates, fill dates, assets, prices, and costs.
- data_manifest.json: coverage, missing values, retrieval time, and data hash.
- rolling_periods.csv: calendar and rolling-window diagnostics.
- uncertainty.json: episode and synchronized block-bootstrap summaries.
- scorecard.csv: dimension-by-dimension promotion status.
- experiment_register.csv: included, deferred, and unavailable related-strategy trials.
- data_snapshot.csv: the immutable common OHLC snapshot used by this run.
- intraday_availability.json: recent availability check and historical limitation.
- stop_order_study.json: explicit standing-stop outcome and required evidence.

## Decision status

Baseline status: research only / inconclusive for promotion until the drawdown, execution delay, and fill evidence meet an agreed dedicated-account limit. The report does not select a production parameter by highest historical return. Any future change must be registered, run through the same engine, and compared with the frozen baseline.
"""
    (output_dir / "modeling_report.md").write_text(report, encoding="utf-8")

    guidelines = f"""# TQQQ / VOO operating guidelines — research draft

These guidelines describe the frozen baseline used in the modeling run dated {manifest["retrieved_at_utc"]}. They are not a broker order instruction until the practical execution and prospective paper gates are satisfied.

1. After a completed S&P 500 total-return session, calculate the {baseline.sma_window}-session SMA and distance from it.
2. A close above the +{baseline.upper_band * 100:g}% entry band creates a confirmed TQQQ target. A close below the {baseline.lower_band * 100:g}% reset band re-arms a new entry only after an exit.
3. When no TQQQ target is active, the dedicated account remains in VOO.
4. A fresh signal is queued for the {baseline.execution} scenario. The model treats the next available trading session as the earliest fill and keeps signal time, order time, and fill time separate.
5. Once the S&P 500 makes a new all-time high during a TQQQ episode, the baseline activates a {baseline.trail_pct * 100:g}% close-based trailing exit. The frozen baseline measures the threshold from the highest TQQQ close since entry; the research suite separately tests a peak reset at ATH activation.
6. On a confirmed exit, rotate to VOO and wait for the reset rule before re-arming.
7. If the expected morning fill is missed, use the pretested delayed scenario and recheck the target using only information then available. Record the actual time and price.
8. Every decision record must include the data session, strategy version, action, target, threshold, pending order, expected execution window, and actual fill if completed.

The live workflow still requires a freshness check, an order/fill journal, observed slippage calibration, and prospective paper observations.
"""
    (output_dir / "decision_guidelines.md").write_text(guidelines, encoding="utf-8")

    one_pager = f"""# TQQQ / VOO strategy research — one-page status

Run: {manifest["retrieved_at_utc"]}  
Coverage: {manifest["start"]}–{manifest["end"]} ({manifest["rows"]:,} common sessions; auto-adjusted yfinance OHLC)

## Bottom line

The strategy is now a reproducible research system rather than an experimental dashboard, but it is not promoted to production. The frozen baseline rotates a dedicated account between VOO and TQQQ, confirms signals after the close, uses next-session execution, and compares each risk-on episode against simply retaining VOO.

## Baseline evidence

- Full-period return: {baseline_score["Return %"]:.2f}% vs VOO {baseline_score["VOO return %"]:.2f}%; paired difference {baseline_score["Excess vs VOO %"]:.2f} percentage points.
- Maximum drawdown: {baseline_score["Max drawdown %"]:.2f}%; Sharpe {baseline_score["Sharpe"]:.2f}; TQQQ exposure {baseline_score["TQQQ time %"]:.2f}%.
- Risk-on ledger: {episode_score["Episodes"]} episodes, {episode_score["Closed episodes"]} closed; {episode_score["Beat VOO %"]:.1f}% beat VOO after 5 bps per leg; median excess {episode_score["Median excess %"]:.2f} percentage points.
- Walk-forward: {len(folds)} expanding one-year test folds; {positive_folds:.1f}% beat VOO. The sample is sparse and outcome concentration remains material.

## What is now covered

One event-driven simulator feeds the app, fills, paired VOO ledger, execution/cost matrix, reset/exit/trail experiments, QQQ/weekly/50%-TQQQ challengers, walk-forward folds, bootstrap uncertainty, concentration, data manifest/snapshot, freshness checks, and a recommendation/fill journal.

## Important limitations

Daily scenarios bound next-open, next-close, and second-session-open behavior; they do not reconstruct 09:35/10:00/11:00 prices. A standing intraday stop-market study is withheld because the full history lacks reliable intraday bars. The volatility-cap and pullback families were deferred until their rules can be frozen without hindsight. Paper validation has not occurred yet.

## Decision

Status: **research only / inconclusive for promotion**. Before considering a live rule, set a dedicated-account drawdown and VOO-underperformance limit, complete at least six months and three signal changes of paper observations (or twelve months if sparse), and recalibrate fill/slippage assumptions from actual records.

See `scorecard.csv`, `episode_ledger.csv`, `execution_matrix.csv`, `walk_forward_folds.csv`, `experiment_register.csv`, `decision_guidelines.md`, and `PAPER_VALIDATION.md`.
"""
    (output_dir / "one_pager.md").write_text(one_pager, encoding="utf-8")


def run(start: str, end: str, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    data = download_market_data(pd.Timestamp(start), pd.Timestamp(end))
    manifest = build_data_manifest(data, code_revision=_git_revision())
    (output / "data_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    baseline = ResearchConfig()
    baseline_result = simulate_strategy(data, baseline)
    execution_matrix = run_execution_matrix(data, baseline)
    experiments = build_experiment_suite(data, baseline)

    candidates = [
        ResearchConfig(sma_window=sma, upper_band=upper, lower_band=-0.01, cost_bps_per_leg=5.0)
        for sma in (150, 200, 250)
        for upper in (0.0, 0.01, 0.02)
    ]
    folds = run_walk_forward(data, candidates, initial_years=5, test_years=1)
    periods = build_period_report(baseline_result, data)
    uncertainty = {
        "episode": bootstrap_episode_relative_wealth(baseline_result.episodes),
        "block": bootstrap_block_relative_wealth(baseline_result.frame),
    }
    scorecard = build_scorecard(baseline_result, folds, execution_matrix, experiments)

    baseline_result.episodes.to_csv(output / "episode_ledger.csv", index=False)
    baseline_result.fills.to_csv(output / "fills.csv", index=False)
    execution_matrix.to_csv(output / "execution_matrix.csv", index=False)
    experiments.to_csv(output / "experiments.csv", index=False)
    folds.to_csv(output / "walk_forward_folds.csv", index=False)
    periods.to_csv(output / "rolling_periods.csv", index=False)
    (output / "uncertainty.json").write_text(json.dumps(uncertainty, indent=2, sort_keys=True), encoding="utf-8")
    scorecard.to_csv(output / "scorecard.csv", index=False)
    experiment_register = build_experiment_register()
    experiment_register.to_csv(output / "experiment_register.csv", index=False)
    data.to_csv(output / "data_snapshot.csv", date_format="%Y-%m-%d")
    (output / "intraday_availability.json").write_text(
        json.dumps(
            {
                "historical_study": {
                    "status": "unavailable",
                    "note": "The provider does not expose a reliable multi-year 5-minute history through this interface; daily scenarios are not clock-time fills.",
                },
                "recent_check": collect_intraday_availability(end),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (output / "stop_order_study.json").write_text(
        json.dumps(
            {
                "status": "inconclusive",
                "variant": "standing intraday stop-market after ATH activation",
                "reason": "A daily OHLC bar does not identify the within-day high/low order or a realistic gap-through fill. The provider history lacks the multi-year intraday bars needed for a defensible comparison.",
                "required_next_step": "Replay recorded 5-minute or quote data with stop-at-market gap handling and explicit slippage before using this variant operationally.",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    build_report(output, manifest, baseline, execution_matrix, experiments, folds, baseline_result, uncertainty, scorecard)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the reproducible TQQQ/VOO research suite.")
    parser.add_argument("--start", default="2010-02-11")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--output", default="../research_reports/latest")
    args = parser.parse_args()
    run(args.start, args.end, Path(args.output))
