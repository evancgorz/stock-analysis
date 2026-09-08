from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from play_the_dip_logic import (
    DEFENSIVE_ASSET,
    INITIAL_CAPITAL,
    STRATEGY_VERSION,
    annualized_return,
    download_market_data,
    format_pct,
    format_usd,
    sharpe_ratio,
)
from research_engine import ResearchConfig, simulate_strategy
from decision_journal import assess_data_freshness, load_journal, record_fill, record_recommendation
from state_store import load_page_state, save_page_state


PAGE_KEY = "play_the_dip"
TODAY = pd.Timestamp.today().normalize()
DEFAULT_START_DATE = (TODAY - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
DEFAULT_END_DATE = TODAY.strftime("%Y-%m-%d")
PAGE_DEFAULTS = {
    "sma_window": 200,
    "upper_band_pct": 1.0,
    "lower_band_pct": -1.0,
    "defensive_asset": "VOO",
}


def build_equity_figure(frame: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["strategy_equity"],
            mode="lines",
            name="Strategy",
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


def current_recommendation(frame: pd.DataFrame) -> tuple[str, str]:
    latest = frame.iloc[-1]
    current_position = bool(latest["position"] == 1.0)
    next_position = bool(latest["signal"] == 1.0)

    if current_position and not next_position:
        return "Exit TQQQ → VOO", "Signal changed after the latest close; rotate at the next open."
    if not current_position and next_position:
        return "Enter TQQQ next open", "The latest close qualified the buy rule; enter at the next open."
    if current_position:
        return "Hold TQQQ", "The TQQQ position remains valid under the current rules."
    return "Hold VOO", "No active TQQQ signal; remain invested in VOO."


def render() -> None:
    saved_inputs = load_page_state(PAGE_KEY, PAGE_DEFAULTS)

    st.title("Home")
    st.caption(
        f"Strategy v{STRATEGY_VERSION}: buy TQQQ after the S&P 500 closes more than 1% above its 200-day SMA, stay invested in VOO until that buy signal appears, activate a 10% TQQQ trailing stop after the S&P 500 makes a fresh all-time high, and only re-arm after the S&P 500 drops more than 1% below its 200-day SMA."
    )
    st.info(
        "Research assumptions: signals are generated after the close and executed at the next open; daily trailing exits are modeled from closing prices; the current research run charges 5 bps per traded leg and keeps broker stop orders separate."
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
        defensive_asset = DEFENSIVE_ASSET
        st.caption("Off-regime allocation: VOO")
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
        result = simulate_strategy(
            raw_data,
            ResearchConfig(
                sma_window=int(sma_window),
                upper_band=upper_band,
                lower_band=lower_band,
                cost_bps_per_leg=5.0,
            ),
        )
        strategy_frame = result.frame
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return

    if strategy_frame.empty:
        st.warning("Not enough data is available to calculate the selected SMA window.")
        return

    freshness = assess_data_freshness(strategy_frame.index)
    if freshness["status"] == "stale":
        st.error(freshness["message"])
    else:
        st.caption(f"Data status: {freshness['message']} Latest completed session: {freshness['latest_session']}.")

    trades = result.episodes
    latest = strategy_frame.iloc[-1]
    recommendation, recommendation_note = current_recommendation(strategy_frame)
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
    closed_trades = trades.loc[trades["Status"] == "Closed"] if not trades.empty else trades
    win_rate = (closed_trades["Strategy net return %"] > 0).mean() if not closed_trades.empty else 0.0
    strategy_annualized_return = annualized_return(strategy_frame["strategy_equity"])
    voo_annualized_return = annualized_return(strategy_frame["voo_buy_hold_equity"])
    strategy_sharpe = sharpe_ratio(strategy_frame["strategy_return"])
    voo_buy_hold_sharpe = sharpe_ratio(strategy_frame["voo_buy_hold_return"])

    st.subheader("Latest state")
    state_metrics = st.columns(3)
    state_metrics[0].metric("Recommendation", recommendation)
    state_metrics[1].metric("Phase", str(latest["phase"]))
    state_metrics[2].metric("Latest event", str(latest["event"] or "None"))
    st.caption(recommendation_note)
    if freshness["status"] == "fresh" and st.button("Record recommendation"):
        record_recommendation(
            {
                "strategy_version": STRATEGY_VERSION,
                "session": strategy_frame.index[-1].date().isoformat(),
                "action": recommendation,
                "note": recommendation_note,
                "signal_distance_to_sma": float(latest["distance_to_sma"]),
                "target_asset": str(latest["target_asset"]),
                "active_asset": str(latest["active_asset"]),
                "signal_event": str(latest["event"] or ""),
            }
        )
        st.success("Recommendation recorded.")

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
                "Strategy": [
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
            st.info("No TQQQ episodes were generated for the selected period.")
        else:
            st.dataframe(trades, use_container_width=True, hide_index=True)

    with st.expander("Decision journal"):
        journal = load_journal()
        if journal.empty:
            st.info("No recommendations or fills have been recorded yet.")
        else:
            st.dataframe(journal, use_container_width=True, hide_index=True)
        with st.form("fill_journal_form"):
            st.caption("Record an actual fill separately from the model recommendation.")
            fill_date = st.date_input("Fill date", value=pd.Timestamp.today())
            fill_asset = st.selectbox("Filled asset", options=["VOO", "TQQQ"])
            fill_price = st.number_input("Fill price", min_value=0.0, value=0.0, step=0.01)
            fill_notes = st.text_input("Notes")
            submitted = st.form_submit_button("Record fill")
            if submitted and fill_price > 0:
                record_fill({"fill_date": fill_date.isoformat(), "asset": fill_asset, "price": fill_price, "notes": fill_notes})
                st.success("Fill recorded.")

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
