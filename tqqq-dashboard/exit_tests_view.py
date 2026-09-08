from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from play_the_dip_logic import (
    DEFENSIVE_ASSET,
    download_market_data,
    format_pct,
)
from research_engine import ResearchConfig, score_window, simulate_strategy
from state_store import load_page_state, save_page_state


PAGE_KEY = "exit_tests"
TODAY = pd.Timestamp.today().normalize()
DEFAULT_START_DATE = (TODAY - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
DEFAULT_END_DATE = TODAY.strftime("%Y-%m-%d")
SMA_WINDOW = 200
UPPER_BAND = 0.01
LOWER_BAND = -0.01
PAGE_DEFAULTS = {
    "defensive_asset": "VOO",
}

EXIT_RULES: dict[str, str] = {
    "sell_at_ath": "Sell at SPX ATH",
    "tqqq_trailing_10_immediate": "TQQQ 10% trailing stop from entry",
    "tqqq_trailing_10_after_ath": "SPX ATH then TQQQ 10% trailing stop",
}


@st.cache_data(show_spinner=False)
def run_exit_rule_analysis(start_date: str, end_date: str, defensive_asset: str) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    data = download_market_data(pd.Timestamp(start_date), pd.Timestamp(end_date))

    summary_rows: list[dict[str, str | float | int]] = []
    equity_frame = pd.DataFrame()
    trade_logs: dict[str, pd.DataFrame] = {}

    exit_modes = {
        "sell_at_ath": "sell_at_ath",
        "tqqq_trailing_10_immediate": "immediate_trailing_close",
        "tqqq_trailing_10_after_ath": "ath_trailing_close",
    }

    for rule_key, rule_name in EXIT_RULES.items():
        result = simulate_strategy(
            data,
            ResearchConfig(
                exit_mode=exit_modes[rule_key],
                cost_bps_per_leg=5.0,
            ),
        )
        frame = result.frame
        trades = result.episodes.copy()
        trade_logs[rule_name] = trades
        score = score_window(result)
        closed = trades.loc[trades["Status"] == "Closed"]
        win_rate = (closed["Strategy net return %"] > 0).mean() if not closed.empty else 0.0
        avg_trade = closed["Strategy net return %"].mean() / 100 if not closed.empty else 0.0

        summary_rows.append(
            {
                "Exit approach": rule_name,
                "Total return": format_pct(score["Return %"] / 100),
                "Vs VOO": format_pct(score["Excess vs VOO %"] / 100),
                "Annualized return": format_pct(score["Annualized %"] / 100),
                "Sharpe": round(score["Sharpe"], 2),
                "Max drawdown": format_pct(score["Max drawdown %"] / 100),
                "Win rate": format_pct(win_rate),
                "Average trade": format_pct(avg_trade),
                "Trade count": int(len(closed)),
                "Time invested": format_pct(score["TQQQ time %"] / 100),
            }
        )

        equity_frame[rule_name] = frame["strategy_equity"]

    if not equity_frame.empty:
        benchmark = simulate_strategy(
            data,
            ResearchConfig(exit_mode="immediate_trailing_close", cost_bps_per_leg=5.0),
        )
        equity_frame["VOO Buy & Hold"] = benchmark.frame["voo_equity"]

    summary = pd.DataFrame(summary_rows)
    return summary, equity_frame, trade_logs


def build_equity_figure(equity_frame: pd.DataFrame, selected_rules: list[str]) -> go.Figure:
    color_map = {
        "Sell at SPX ATH": "#d99100",
        "TQQQ 10% trailing stop from entry": "#1f3b57",
        "SPX ATH then TQQQ 10% trailing stop": "#b14f29",
        "VOO Buy & Hold": "#4d4d4d",
    }
    figure = go.Figure()
    for rule_name in selected_rules:
        if rule_name not in equity_frame.columns:
            continue
        figure.add_trace(
            go.Scatter(
                x=equity_frame.index,
                y=equity_frame[rule_name],
                mode="lines",
                name=rule_name,
                line={"width": 2.5, "color": color_map.get(rule_name, "#1f3b57")},
            )
        )
    if "VOO Buy & Hold" in equity_frame.columns:
        figure.add_trace(
            go.Scatter(
                x=equity_frame.index,
                y=equity_frame["VOO Buy & Hold"],
                mode="lines",
                name="VOO Buy & Hold",
                line={"width": 2, "dash": "dot", "color": color_map["VOO Buy & Hold"]},
            )
        )
    figure.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        height=440,
        template="plotly_white",
        legend={"orientation": "h", "y": 1.08, "x": 0},
        yaxis_title="Equity",
    )
    return figure


def render() -> None:
    saved_inputs = load_page_state(PAGE_KEY, PAGE_DEFAULTS)

    st.title("Exit Tests")
    st.caption(
        "This page keeps the entry setup fixed at a 200-day SMA with a +1% buy band and -1% reset band, then compares three exit approaches against continuous VOO ownership."
    )

    with st.sidebar:
        st.header("Test Inputs")
        start_date = st.date_input("Start date", value=pd.Timestamp(DEFAULT_START_DATE))
        end_date = st.date_input("End date", value=pd.Timestamp(DEFAULT_END_DATE))
        defensive_asset = DEFENSIVE_ASSET
        st.caption("Off-regime allocation: VOO")
        if st.button("Refresh data"):
            st.cache_data.clear()

    save_page_state(
        PAGE_KEY,
        {
            "defensive_asset": defensive_asset,
        },
        last_page=PAGE_KEY,
    )

    if start_date >= end_date:
        st.error("End date must be after start date.")
        return

    try:
        summary, equity_frame, trade_logs = run_exit_rule_analysis(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
            defensive_asset,
        )
    except Exception as exc:
        st.error(f"Could not run the exit tests: {exc}")
        return

    if summary.empty:
        st.warning("No valid results were produced for the selected period.")
        return

    top_return = summary.iloc[summary["Total return"].str.rstrip("%").astype(float).idxmax()]
    top_sharpe = summary.iloc[summary["Sharpe"].astype(float).idxmax()]
    top_win_rate = summary.iloc[summary["Win rate"].str.rstrip("%").astype(float).idxmax()]

    metrics = st.columns(3)
    metrics[0].metric("Best total return", f"{top_return['Exit approach']} ({top_return['Total return']})")
    metrics[1].metric("Best Sharpe", f"{top_sharpe['Exit approach']} ({top_sharpe['Sharpe']:.2f})")
    metrics[2].metric("Best win rate", f"{top_win_rate['Exit approach']} ({top_win_rate['Win rate']})")

    st.subheader("Exit approach summary")
    st.dataframe(summary, use_container_width=True, hide_index=True)

    st.subheader("Trade logs")
    for rule_name in EXIT_RULES.values():
        st.markdown(f"**{rule_name}**")
        trades = trade_logs.get(rule_name, pd.DataFrame())
        if trades.empty:
            st.info("No trades were generated for this exit approach in the selected period.")
        else:
            st.dataframe(trades, use_container_width=True, hide_index=True)

    with st.expander("Equity comparison chart"):
        plotted_rule_names = list(EXIT_RULES.values())
        st.plotly_chart(build_equity_figure(equity_frame, plotted_rule_names), use_container_width=True)

    st.info(
        "Assumptions for this test page: entries still use the same one-day-delayed execution as the main strategy page. For the trailing-stop variants, the TQQQ stop is inactive until the S&P 500 first makes a new ATH during the trade."
    )
