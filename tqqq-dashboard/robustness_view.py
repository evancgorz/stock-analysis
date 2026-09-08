from __future__ import annotations

import pandas as pd
import streamlit as st

from play_the_dip_logic import download_market_data
from research_engine import (
    ResearchConfig,
    run_execution_matrix,
    run_walk_forward,
    score_episodes,
    score_window,
    simulate_strategy,
)
from research_runner import build_experiment_suite


TODAY = pd.Timestamp.today().normalize()
DEFAULT_START_DATE = pd.Timestamp("2010-02-11")
DEFAULT_END_DATE = TODAY


@st.cache_data(show_spinner=False)
def load_research_data(start_date: str, end_date: str) -> pd.DataFrame:
    return download_market_data(pd.Timestamp(start_date), pd.Timestamp(end_date))


@st.cache_data(show_spinner=False)
def run_research_suite(start_date: str, end_date: str, cost_bps: float):
    data = load_research_data(start_date, end_date)
    baseline = ResearchConfig(cost_bps_per_leg=cost_bps)
    result = simulate_strategy(data, baseline)
    execution = run_execution_matrix(data, baseline)
    experiments = build_experiment_suite(data, baseline)
    candidates = [
        ResearchConfig(sma_window=sma, upper_band=upper, lower_band=-0.01, cost_bps_per_leg=cost_bps)
        for sma in (150, 200, 250)
        for upper in (0.0, 0.01, 0.02)
    ]
    folds = run_walk_forward(data, candidates, initial_years=5, test_years=1)
    return data, baseline, result, execution, experiments, folds


def render() -> None:
    st.title("Research and Robustness")
    st.caption(
        "The research pages use one event-driven simulator. Results compare the dedicated VOO/TQQQ account with continuous VOO over identical dates and show execution sensitivity before any promotion decision."
    )

    with st.sidebar:
        start_date = st.date_input("Research start", value=DEFAULT_START_DATE)
        end_date = st.date_input("Research end", value=DEFAULT_END_DATE)
        cost_bps = st.number_input("Cost per traded leg (bps)", min_value=0.0, max_value=100.0, value=5.0, step=1.0)

    if start_date >= end_date:
        st.error("Research end must be after research start.")
        return

    try:
        data, baseline, result, execution, experiments, folds = run_research_suite(
            start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), float(cost_bps)
        )
    except Exception as exc:
        st.error(f"Could not run the research suite: {exc}")
        return

    score = score_window(result)
    episode_score = score_episodes(result.episodes)
    metrics = st.columns(5)
    metrics[0].metric("Baseline vs VOO", f"{score['Excess vs VOO %']:.2f}%")
    metrics[1].metric("Max drawdown", f"{score['Max drawdown %']:.2f}%")
    metrics[2].metric("Sharpe", f"{score['Sharpe']:.2f}")
    metrics[3].metric("TQQQ time", f"{score['TQQQ time %']:.1f}%")
    metrics[4].metric("Episodes beating VOO", f"{episode_score['Beat VOO %']:.1f}%")
    st.info(
        f"Common data coverage: {data.index[0].date()} to {data.index[-1].date()} ({len(data):,} sessions). The daily matrix is a delay and cost sensitivity study; it does not reconstruct 09:35, 10:00, or 11:00 prices from daily bars."
    )

    st.subheader("Baseline paired risk-on ledger")
    st.dataframe(result.episodes, use_container_width=True, hide_index=True)

    st.subheader("Execution and cost sensitivity")
    st.dataframe(execution, use_container_width=True, hide_index=True)

    st.subheader("Bounded experiments")
    st.dataframe(experiments, use_container_width=True, hide_index=True)

    st.subheader("Expanding walk-forward folds")
    if folds.empty:
        st.warning("No walk-forward folds were available for the selected dates.")
    else:
        st.dataframe(folds, use_container_width=True, hide_index=True)
        st.caption(
            f"Selected candidates beat VOO in {(folds['Test excess %'] > 0).mean():.0%} of one-year test folds. This is historical evidence with sparse episodes, not a guarantee."
        )

    with st.expander("Fills and event ledger"):
        st.dataframe(result.fills, use_container_width=True, hide_index=True)
        st.dataframe(result.frame.tail(500), use_container_width=True)
