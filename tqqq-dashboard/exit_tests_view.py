from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from play_the_dip_logic import (
    INITIAL_CAPITAL,
    annualized_return,
    download_market_data,
    extract_trades,
    format_pct,
    sharpe_ratio,
)
from state_store import load_page_state, save_page_state


PAGE_KEY = "exit_tests"
TODAY = pd.Timestamp.today().normalize()
DEFAULT_START_DATE = (TODAY - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
DEFAULT_END_DATE = TODAY.strftime("%Y-%m-%d")
SMA_WINDOW = 200
UPPER_BAND = 0.01
LOWER_BAND = -0.01
PAGE_DEFAULTS = {
    "defensive_asset": "Cash",
}

EXIT_RULES: dict[str, str] = {
    "tqqq_trailing_10_immediate": "TQQQ 10% trailing stop from entry",
    "tqqq_trailing_10_after_ath": "SPX ATH then TQQQ 10% trailing stop",
}


def _rule_triggered(
    rule_key: str,
    row: pd.Series,
    trade_state: dict[str, float | int],
) -> tuple[bool, str]:
    if rule_key == "tqqq_trailing_10_immediate":
        stop_level = float(trade_state["peak_tqqq"]) * 0.90
        return bool(row["tqqq_close"] <= stop_level), "TQQQ fell 10% from its post-entry high"
    if rule_key == "tqqq_trailing_10_after_ath":
        if not bool(trade_state["ath_reached"]):
            return False, ""
        stop_level = float(trade_state["peak_tqqq"]) * 0.90
        return bool(row["tqqq_close"] <= stop_level), "TQQQ fell 10% after the S&P 500 reached a new ATH"
    raise ValueError(f"Unsupported exit rule: {rule_key}")


def build_exit_test_frame(data: pd.DataFrame, defensive_asset: str, rule_key: str) -> pd.DataFrame:
    frame = data.copy()
    frame["spx_sma"] = frame["spx_close"].rolling(SMA_WINDOW).mean()
    frame["spx_20_sma"] = frame["spx_close"].rolling(20).mean()
    frame["spx_50_sma"] = frame["spx_close"].rolling(50).mean()
    frame["distance_to_sma"] = frame["spx_close"] / frame["spx_sma"] - 1.0
    frame["prior_ath"] = frame["spx_close"].cummax().shift(1)
    frame["is_new_ath"] = frame["spx_close"] > frame["prior_ath"].fillna(-np.inf)

    ready = frame.dropna(subset=["spx_sma"]).copy()

    signals: list[float] = []
    phases: list[str] = []
    events: list[str] = []
    exit_rule_names: list[str] = []

    target_long = False
    awaiting_reset = False
    buy_armed = True
    trade_state: dict[str, float | int] = {
        "peak_tqqq": np.nan,
        "peak_spx": np.nan,
        "days_in_trade": 0,
        "ath_reached": False,
    }

    for _, row in ready.iterrows():
        event = ""
        distance = float(row["distance_to_sma"])

        if target_long:
            trade_state["peak_tqqq"] = max(float(trade_state["peak_tqqq"]), float(row["tqqq_close"]))
            trade_state["peak_spx"] = max(float(trade_state["peak_spx"]), float(row["spx_close"]))
            trade_state["days_in_trade"] = int(trade_state["days_in_trade"]) + 1
            if bool(row["is_new_ath"]):
                trade_state["ath_reached"] = True
            exit_now, exit_reason = _rule_triggered(rule_key, row, trade_state)
            if exit_now:
                target_long = False
                awaiting_reset = True
                buy_armed = False
                event = exit_reason
                trade_state = {
                    "peak_tqqq": np.nan,
                    "peak_spx": np.nan,
                    "days_in_trade": 0,
                    "ath_reached": False,
                }
        elif awaiting_reset and distance < LOWER_BAND:
            awaiting_reset = False
            buy_armed = True
            event = "Reset level reached"
        elif (not target_long) and buy_armed and distance > UPPER_BAND:
            target_long = True
            buy_armed = False
            trade_state = {
                "peak_tqqq": float(row["tqqq_close"]),
                "peak_spx": float(row["spx_close"]),
                "days_in_trade": 0,
                "ath_reached": False,
            }
            event = "Buy level reached"

        if target_long:
            phase = "Holding TQQQ"
        elif awaiting_reset:
            phase = "Waiting for reset below lower band"
        elif buy_armed:
            phase = "Armed for next buy signal"
        else:
            phase = "Defensive allocation"

        signals.append(1.0 if target_long else 0.0)
        phases.append(phase)
        events.append(event)
        exit_rule_names.append(EXIT_RULES[rule_key])

    ready["signal"] = signals
    ready["phase"] = phases
    ready["event"] = events
    ready["exit_rule"] = exit_rule_names
    ready["position"] = ready["signal"].shift(1).fillna(0.0)
    ready["tqqq_return"] = ready["tqqq_close"].pct_change().fillna(0.0)
    ready["voo_return"] = ready["voo_close"].pct_change().fillna(0.0)
    ready["spx_return"] = ready["spx_close"].pct_change().fillna(0.0)
    ready["defensive_return"] = 0.0 if defensive_asset == "Cash" else ready["voo_return"]
    ready["active_asset"] = np.where(ready["position"] == 1.0, "TQQQ", defensive_asset)
    ready["strategy_return"] = ready["position"] * ready["tqqq_return"]
    ready["strategy_return"] += (1.0 - ready["position"]) * ready["defensive_return"]
    ready["strategy_equity"] = INITIAL_CAPITAL * (1 + ready["strategy_return"]).cumprod()
    ready["spx_buy_hold_equity"] = INITIAL_CAPITAL * (1 + ready["spx_return"]).cumprod()
    ready["strategy_peak"] = ready["strategy_equity"].cummax()
    ready["strategy_drawdown"] = ready["strategy_equity"] / ready["strategy_peak"] - 1.0
    return ready


@st.cache_data(show_spinner=False)
def run_exit_rule_analysis(start_date: str, end_date: str, defensive_asset: str) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    data = download_market_data(pd.Timestamp(start_date), pd.Timestamp(end_date))

    summary_rows: list[dict[str, str | float | int]] = []
    equity_frame = pd.DataFrame()
    trade_logs: dict[str, pd.DataFrame] = {}

    for rule_key, rule_name in EXIT_RULES.items():
        frame = build_exit_test_frame(data, defensive_asset, rule_key)
        if frame.empty:
            continue

        trades = extract_trades(frame)
        trade_logs[rule_name] = trades
        total_return = frame["strategy_equity"].iloc[-1] / INITIAL_CAPITAL - 1.0
        spx_return = frame["spx_buy_hold_equity"].iloc[-1] / INITIAL_CAPITAL - 1.0
        win_rate = (trades["Return %"] > 0).mean() if not trades.empty else 0.0
        avg_trade = trades["Return %"].mean() / 100 if not trades.empty else 0.0

        summary_rows.append(
            {
                "Exit approach": rule_name,
                "Total return": format_pct(total_return),
                "Vs S&P 500": format_pct(total_return - spx_return),
                "Annualized return": format_pct(annualized_return(frame["strategy_equity"])),
                "Sharpe": round(sharpe_ratio(frame["strategy_return"]), 2),
                "Max drawdown": format_pct(frame["strategy_drawdown"].min()),
                "Win rate": format_pct(win_rate),
                "Average trade": format_pct(avg_trade),
                "Trade count": int(len(trades)),
                "Time invested": format_pct(frame["position"].mean()),
            }
        )

        equity_frame[rule_name] = frame["strategy_equity"]

    if not equity_frame.empty:
        benchmark = build_exit_test_frame(data, defensive_asset, "tqqq_trailing_10_immediate")
        equity_frame["S&P 500 Buy & Hold"] = benchmark["spx_buy_hold_equity"]

    summary = pd.DataFrame(summary_rows)
    return summary, equity_frame, trade_logs


def build_equity_figure(equity_frame: pd.DataFrame, selected_rules: list[str]) -> go.Figure:
    color_map = {
        "TQQQ 10% trailing stop from entry": "#1f3b57",
        "SPX ATH then TQQQ 10% trailing stop": "#b14f29",
        "S&P 500 Buy & Hold": "#4d4d4d",
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
    if "S&P 500 Buy & Hold" in equity_frame.columns:
        figure.add_trace(
            go.Scatter(
                x=equity_frame.index,
                y=equity_frame["S&P 500 Buy & Hold"],
                mode="lines",
                name="S&P 500 Buy & Hold",
                line={"width": 2, "dash": "dot", "color": color_map["S&P 500 Buy & Hold"]},
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
        "This page keeps the entry setup fixed at a 200-day SMA with a +1% buy band and -1% reset band, then compares two exit approaches: a 10% TQQQ trailing stop from entry versus a 10% TQQQ trailing stop that only activates after the S&P 500 reaches a fresh all-time high."
    )

    with st.sidebar:
        st.header("Test Inputs")
        start_date = st.date_input("Start date", value=pd.Timestamp(DEFAULT_START_DATE))
        end_date = st.date_input("End date", value=pd.Timestamp(DEFAULT_END_DATE))
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
