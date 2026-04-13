from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from play_the_dip_logic import (
    INITIAL_CAPITAL,
    annualized_return,
    build_play_the_dip_frame,
    download_market_data,
    extract_trades,
    format_pct,
    format_usd,
    sharpe_ratio,
)
from state_store import load_page_state, save_page_state


PAGE_KEY = "play_the_dip"
TODAY = pd.Timestamp.today().normalize()
DEFAULT_START_DATE = (TODAY - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
DEFAULT_END_DATE = TODAY.strftime("%Y-%m-%d")
PAGE_DEFAULTS = {
    "sma_window": 200,
    "upper_band_pct": 1.0,
    "lower_band_pct": -1.0,
    "defensive_asset": "Cash",
}


def build_equity_figure(frame: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["strategy_equity"],
            mode="lines",
            name="Play the Dip",
            line={"color": "#b14f29", "width": 3},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["voo_buy_hold_equity"],
            mode="lines",
            name="VOO Buy & Hold",
            line={"color": "#3c5d7c", "width": 2, "dash": "dot"},
        )
    )
    figure.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        legend={"orientation": "h", "y": 1.08, "x": 0},
        height=420,
        template="plotly_white",
    )
    return figure


def build_signal_check_figure(
    frame: pd.DataFrame,
    upper_band: float,
    lower_band: float,
    lookback_bars: int = 126,
) -> go.Figure:
    window = frame.tail(lookback_bars).copy()
    upper_trigger = window["spx_sma"] * (1 + upper_band)
    lower_trigger = window["spx_sma"] * (1 + lower_band)

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=window.index,
            y=window["spx_close"],
            mode="lines",
            name="S&P 500",
            line={"color": "#1f3b57", "width": 2.6},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=window.index,
            y=window["spx_sma"],
            mode="lines",
            name="SMA",
            line={"color": "#7c6a58", "width": 1.8},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=window.index,
            y=upper_trigger,
            mode="lines",
            name="Buy level",
            line={"color": "#0d7a5f", "width": 2},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=window.index,
            y=lower_trigger,
            mode="lines",
            name="Reset level",
            line={"color": "#a12e2b", "width": 2},
        )
    )
    ath_points = window[window["is_new_ath"]]
    figure.add_trace(
        go.Scatter(
            x=ath_points.index,
            y=ath_points["spx_close"],
            mode="markers",
            name="ATH",
            marker={"color": "#d99100", "size": 7},
        )
    )
    figure.update_layout(
        margin={"l": 12, "r": 12, "t": 20, "b": 12},
        height=320,
        template="plotly_white",
        legend={"orientation": "h", "y": 1.08, "x": 0},
        yaxis_title="S&P 500 price",
    )
    return figure


def build_drawdown_figure(frame: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["strategy_drawdown"] * 100,
            fill="tozeroy",
            mode="lines",
            line={"color": "#a12e2b", "width": 2.5},
            name="Strategy Drawdown",
        )
    )
    figure.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        height=280,
        template="plotly_white",
        yaxis_title="%",
        showlegend=False,
    )
    return figure


def build_price_regime_figure(frame: pd.DataFrame, upper_band: float, lower_band: float) -> go.Figure:
    upper_trigger = frame["spx_sma"] * (1 + upper_band)
    lower_trigger = frame["spx_sma"] * (1 + lower_band)
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["spx_close"],
            mode="lines",
            name="S&P 500 Close",
            line={"color": "#1f3b57", "width": 2.4},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=frame.index,
            y=upper_trigger,
            mode="lines",
            name="Buy trigger level",
            line={"color": "#0d7a5f", "width": 2.2},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["spx_sma"],
            mode="lines",
            name="200-day SMA",
            line={"color": "#7c6a58", "width": 1.8},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=frame.index,
            y=lower_trigger,
            mode="lines",
            name="Reset trigger level",
            line={"color": "#a12e2b", "width": 2.2},
        )
    )
    ath_points = frame[frame["is_new_ath"]]
    figure.add_trace(
        go.Scatter(
            x=ath_points.index,
            y=ath_points["spx_close"],
            mode="markers",
            name="New S&P 500 ATH",
            marker={"color": "#d99100", "size": 7},
            hovertemplate="%{x|%Y-%m-%d}<br>S&P 500 ATH: %{y:.2f}<extra></extra>",
        )
    )
    figure.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        height=320,
        template="plotly_white",
        legend={"orientation": "h", "y": 1.08, "x": 0},
        yaxis_title="S&P 500 price",
    )
    return figure


def build_percent_regime_figure(frame: pd.DataFrame, upper_band: float, lower_band: float) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["distance_to_sma"] * 100,
            mode="lines",
            name="% from 200 SMA",
            line={"color": "#3c5d7c", "width": 2.4},
        )
    )
    figure.add_hline(y=upper_band * 100, line_dash="dot", line_color="#0d7a5f")
    figure.add_hline(y=lower_band * 100, line_dash="dot", line_color="#a12e2b")
    figure.update_layout(
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        height=280,
        template="plotly_white",
        legend={"orientation": "h", "y": 1.08, "x": 0},
        yaxis_title="% from SMA",
    )
    return figure


def render() -> None:
    saved_inputs = load_page_state(PAGE_KEY, PAGE_DEFAULTS)

    st.title("Home")
    st.caption(
        "Play the Dip is now the core strategy. Use Grid Search to evaluate how SMA windows and matched thresholds affect win rate, Sharpe, and relative performance."
    )

    with st.sidebar:
        st.header("Inputs")
        start_date = st.date_input("Start date", value=pd.Timestamp(DEFAULT_START_DATE))
        end_date = st.date_input("End date", value=pd.Timestamp(DEFAULT_END_DATE))
        sma_window = st.number_input(
            "SMA window",
            min_value=50,
            max_value=300,
            value=int(saved_inputs["sma_window"]),
            step=5,
        )
        upper_band_pct = st.number_input(
            "Buy threshold above SMA (%)",
            min_value=0.0,
            max_value=10.0,
            value=float(saved_inputs["upper_band_pct"]),
            step=0.1,
        )
        lower_band_pct = st.number_input(
            "Reset threshold below SMA (%)",
            min_value=-10.0,
            max_value=0.0,
            value=float(saved_inputs["lower_band_pct"]),
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
            "sma_window": int(sma_window),
            "upper_band_pct": float(upper_band_pct),
            "lower_band_pct": float(lower_band_pct),
            "defensive_asset": defensive_asset,
        },
        last_page=PAGE_KEY,
    )

    if start_date >= end_date:
        st.error("End date must be after start date.")
        return

    upper_band = float(upper_band_pct) / 100
    lower_band = float(lower_band_pct) / 100

    try:
        raw_data = download_market_data(pd.Timestamp(start_date), pd.Timestamp(end_date))
        strategy_frame = build_play_the_dip_frame(
            raw_data,
            int(sma_window),
            upper_band,
            lower_band,
            defensive_asset,
        )
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return

    if strategy_frame.empty:
        st.warning("Not enough data is available to calculate the selected SMA window.")
        return

    trades = extract_trades(strategy_frame)
    latest = strategy_frame.iloc[-1]
    latest_ath = strategy_frame["spx_close"].cummax().iloc[-1]
    latest_day_change = (
        strategy_frame["spx_close"].pct_change().iloc[-1]
        if len(strategy_frame) > 1
        else 0.0
    )

    total_return = strategy_frame["strategy_equity"].iloc[-1] / INITIAL_CAPITAL - 1.0
    voo_buy_hold_return = strategy_frame["voo_buy_hold_equity"].iloc[-1] / INITIAL_CAPITAL - 1.0
    max_drawdown = strategy_frame["strategy_drawdown"].min()
    time_in_market = strategy_frame["position"].mean()
    win_rate = (trades["Return %"] > 0).mean() if not trades.empty else 0.0
    strategy_annualized_return = annualized_return(strategy_frame["strategy_equity"])
    voo_annualized_return = annualized_return(strategy_frame["voo_buy_hold_equity"])
    strategy_sharpe = sharpe_ratio(strategy_frame["strategy_return"])
    voo_buy_hold_sharpe = sharpe_ratio(strategy_frame["voo_buy_hold_return"])

    st.subheader("Latest state")
    state_metrics = st.columns(2)
    state_metrics[0].metric("Phase", str(latest["phase"]))
    state_metrics[1].metric("Latest event", str(latest["event"] or "None"))

    key_metrics = st.columns(2)
    key_metrics[0].metric("Distance to SMA", format_pct(latest["distance_to_sma"]))
    key_metrics[1].metric("S&P 500 close", f"{latest['spx_close']:,.2f}")

    level_metrics = st.columns(2)
    level_metrics[0].metric("200-day SMA", f"{latest['spx_sma']:,.2f}")
    level_metrics[1].metric("Latest ATH", f"{latest_ath:,.2f}")

    change_metrics = st.columns(2)
    change_metrics[0].metric("Today % change", format_pct(latest_day_change))
    change_metrics[1].metric("Current holding", str(latest["active_asset"]))

    st.subheader("Trading check")
    st.plotly_chart(build_signal_check_figure(strategy_frame, upper_band, lower_band), use_container_width=True)

    with st.expander("More charts and performance"):
        st.subheader("Performance details")
        summary = pd.DataFrame(
            {
                "Metric": [
                    "Total return",
                    "Annualized return",
                    "Sharpe ratio",
                    "Final equity",
                    "Max drawdown",
                    "Time invested",
                    "Win rate",
                ],
                "Play the Dip": [
                    format_pct(total_return),
                    format_pct(strategy_annualized_return),
                    f"{strategy_sharpe:.2f}",
                    format_usd(strategy_frame["strategy_equity"].iloc[-1]),
                    format_pct(max_drawdown),
                    format_pct(time_in_market),
                    format_pct(win_rate),
                ],
                "VOO Buy & Hold": [
                    format_pct(voo_buy_hold_return),
                    format_pct(voo_annualized_return),
                    f"{voo_buy_hold_sharpe:.2f}",
                    format_usd(strategy_frame["voo_buy_hold_equity"].iloc[-1]),
                    "",
                    "",
                    "",
                ],
            }
        )
        st.dataframe(summary, use_container_width=True, hide_index=True)

        st.subheader("S&P 500 Price and Trigger Levels")
        st.plotly_chart(build_price_regime_figure(strategy_frame, upper_band, lower_band), use_container_width=True)

        st.subheader("S&P 500 Distance from 200-day SMA")
        st.plotly_chart(build_percent_regime_figure(strategy_frame, upper_band, lower_band), use_container_width=True)

        st.subheader("Equity curve")
        st.plotly_chart(build_equity_figure(strategy_frame), use_container_width=True)

        st.subheader("Drawdown")
        st.plotly_chart(build_drawdown_figure(strategy_frame), use_container_width=True)

    with st.expander("Trade log"):
        if trades.empty:
            st.info("No completed trades were generated for the selected period.")
        else:
            st.dataframe(trades, use_container_width=True, hide_index=True)

    with st.expander("Backtest data"):
        display_frame = strategy_frame[
            [
                "tqqq_close",
                "voo_close",
                "spx_close",
                "spx_sma",
                "distance_to_sma",
                "is_new_ath",
                "phase",
                "event",
                "signal",
                "position",
                "active_asset",
                "strategy_equity",
                "voo_buy_hold_equity",
            ]
        ].copy()
        display_frame["distance_to_sma"] = (display_frame["distance_to_sma"] * 100).round(2)
        st.dataframe(display_frame, use_container_width=True)
