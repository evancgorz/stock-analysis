from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from play_the_dip_logic import (
    INITIAL_CAPITAL,
    build_play_the_dip_frame,
    download_market_data,
    extract_trades,
    sharpe_ratio,
)
from state_store import load_page_state, save_page_state


PAGE_KEY = "play_the_dip_grid_search"
TODAY = pd.Timestamp.today().normalize()
DEFAULT_START_DATE = (TODAY - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
DEFAULT_END_DATE = TODAY.strftime("%Y-%m-%d")
PAGE_DEFAULTS = {
    "sma_start": 100,
    "sma_end": 300,
    "sma_step": 20,
    "threshold_start_pct": 0.5,
    "threshold_end_pct": 3.0,
    "threshold_step_pct": 0.5,
    "defensive_asset": "Cash",
}


def build_heatmap(results: pd.DataFrame, value_column: str, title: str) -> go.Figure:
    pivot = results.pivot(index="threshold_pct", columns="sma_window", values=value_column).sort_index(ascending=False)
    figure = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale="RdYlGn",
            colorbar={"title": title},
            hovertemplate="SMA %{x}<br>Threshold %{y}%<br>Value %{z:.2f}<extra></extra>",
        )
    )
    figure.update_layout(
        title=title,
        margin={"l": 12, "r": 12, "t": 44, "b": 12},
        height=420,
        template="plotly_white",
        xaxis_title="SMA window",
        yaxis_title="Matched +/- threshold (%)",
    )
    return figure


@st.cache_data(show_spinner=False)
def run_grid_search(
    start_date: str,
    end_date: str,
    sma_values: tuple[int, ...],
    threshold_values: tuple[float, ...],
    defensive_asset: str,
) -> pd.DataFrame:
    market_data = download_market_data(pd.Timestamp(start_date), pd.Timestamp(end_date))
    rows = []

    for sma_window in sma_values:
        for threshold_pct in threshold_values:
            threshold = threshold_pct / 100
            frame = build_play_the_dip_frame(
                market_data,
                int(sma_window),
                threshold,
                -threshold,
                defensive_asset,
            )
            if frame.empty:
                continue

            trades = extract_trades(frame)
            strategy_return = frame["strategy_equity"].iloc[-1] / INITIAL_CAPITAL - 1.0
            spx_return = frame["spx_buy_hold_equity"].iloc[-1] / INITIAL_CAPITAL - 1.0
            win_rate = (trades["Return %"] > 0).mean() if not trades.empty else 0.0

            rows.append(
                {
                    "sma_window": int(sma_window),
                    "threshold_pct": float(threshold_pct),
                    "win_rate_pct": win_rate * 100,
                    "strategy_return_pct": strategy_return * 100,
                    "spx_return_pct": spx_return * 100,
                    "strategy_vs_spx_pct": (strategy_return - spx_return) * 100,
                    "sharpe_ratio": sharpe_ratio(frame["strategy_return"]),
                    "trade_count": len(trades),
                }
            )

    return pd.DataFrame(rows)


def render() -> None:
    saved_inputs = load_page_state(PAGE_KEY, PAGE_DEFAULTS)

    st.title("Grid Search")
    st.caption(
        "Sweep matched +/- thresholds and SMA windows to find stronger parameter combinations for the strategy."
    )

    with st.sidebar:
        st.header("Grid Inputs")
        start_date = st.date_input("Start date", value=pd.Timestamp(DEFAULT_START_DATE))
        end_date = st.date_input("End date", value=pd.Timestamp(DEFAULT_END_DATE))
        sma_start = st.number_input("SMA start", min_value=50, max_value=400, value=int(saved_inputs["sma_start"]), step=5)
        sma_end = st.number_input("SMA end", min_value=50, max_value=400, value=int(saved_inputs["sma_end"]), step=5)
        sma_step = st.number_input("SMA step", min_value=1, max_value=100, value=int(saved_inputs["sma_step"]), step=1)
        threshold_start_pct = st.number_input(
            "Threshold start (%)",
            min_value=0.1,
            max_value=10.0,
            value=float(saved_inputs["threshold_start_pct"]),
            step=0.1,
        )
        threshold_end_pct = st.number_input(
            "Threshold end (%)",
            min_value=0.1,
            max_value=10.0,
            value=float(saved_inputs["threshold_end_pct"]),
            step=0.1,
        )
        threshold_step_pct = st.number_input(
            "Threshold step (%)",
            min_value=0.1,
            max_value=5.0,
            value=float(saved_inputs["threshold_step_pct"]),
            step=0.1,
        )
        defensive_asset = st.selectbox(
            "Off-regime allocation",
            options=["Cash", "VOO"],
            index=0 if saved_inputs["defensive_asset"] == "Cash" else 1,
        )
        if st.button("Refresh data"):
            st.cache_data.clear()

    save_page_state(
        PAGE_KEY,
        {
            "sma_start": int(sma_start),
            "sma_end": int(sma_end),
            "sma_step": int(sma_step),
            "threshold_start_pct": float(threshold_start_pct),
            "threshold_end_pct": float(threshold_end_pct),
            "threshold_step_pct": float(threshold_step_pct),
            "defensive_asset": defensive_asset,
        },
        last_page=PAGE_KEY,
    )

    if start_date >= end_date:
        st.error("End date must be after start date.")
        return
    if sma_start >= sma_end:
        st.error("SMA end must be greater than SMA start.")
        return
    if threshold_start_pct >= threshold_end_pct:
        st.error("Threshold end must be greater than threshold start.")
        return

    sma_values = tuple(range(int(sma_start), int(sma_end) + 1, int(sma_step)))
    threshold_values = tuple(
        round(value, 4)
        for value in np.arange(
            float(threshold_start_pct),
            float(threshold_end_pct) + float(threshold_step_pct) / 2,
            float(threshold_step_pct),
        ).tolist()
    )

    try:
        results = run_grid_search(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
            sma_values,
            threshold_values,
            defensive_asset,
        )
    except Exception as exc:
        st.error(f"Could not run the grid search: {exc}")
        return

    if results.empty:
        st.warning("No valid combinations were produced for the selected ranges.")
        return

    best_vs_spx = results.loc[results["strategy_vs_spx_pct"].idxmax()]
    best_win_rate = results.loc[results["win_rate_pct"].idxmax()]
    best_sharpe = results.loc[results["sharpe_ratio"].idxmax()]

    metrics = st.columns(6)
    metrics[0].metric("Best vs S&P 500", f"{best_vs_spx['strategy_vs_spx_pct']:.2f}%")
    metrics[1].metric("Best SMA", str(int(best_vs_spx["sma_window"])))
    metrics[2].metric("Best threshold", f"{best_vs_spx['threshold_pct']:.2f}%")
    metrics[3].metric("Best win rate", f"{best_win_rate['win_rate_pct']:.2f}%")
    metrics[4].metric("Best Sharpe", f"{best_sharpe['sharpe_ratio']:.2f}")
    metrics[5].metric(
        "Sharpe SMA / Threshold",
        f"{int(best_sharpe['sma_window'])} / {best_sharpe['threshold_pct']:.2f}%",
    )

    left, middle, right = st.columns(3)
    with left:
        st.plotly_chart(build_heatmap(results, "strategy_vs_spx_pct", "Strategy vs S&P 500 Return (%)"), use_container_width=True)
    with middle:
        st.plotly_chart(build_heatmap(results, "win_rate_pct", "Win Rate (%)"), use_container_width=True)
    with right:
        st.plotly_chart(build_heatmap(results, "sharpe_ratio", "Sharpe Ratio"), use_container_width=True)

    st.subheader("Top combinations by strategy vs S&P 500")
    top_results = results.sort_values(["strategy_vs_spx_pct", "win_rate_pct"], ascending=[False, False]).head(20).copy()
    st.dataframe(top_results, use_container_width=True, hide_index=True)

    st.subheader("Top combinations by Sharpe ratio")
    top_sharpe = results.sort_values(["sharpe_ratio", "strategy_vs_spx_pct"], ascending=[False, False]).head(20).copy()
    st.dataframe(top_sharpe, use_container_width=True, hide_index=True)
