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
from low_trade_comparison import LowTradeSpec, simulate_entry_locked_policy
from operating_policy import OPERATING_POLICIES, build_action_plan
from state_store import load_page_state, save_page_state


PAGE_KEY = "play_the_dip"
TODAY = pd.Timestamp.today().normalize()
DEFAULT_END_DATE = TODAY.strftime("%Y-%m-%d")
OPERATIONAL_START_DATE = "2010-02-11"
PAGE_DEFAULTS = {
    "sma_window": 200,
    "upper_band_pct": 1.0,
    "lower_band_pct": -1.0,
    "defensive_asset": "VOO",
    "operating_policy": "baseline",
    "account_value": 100_000.0,
    "current_tqqq_pct": 0.0,
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


def render() -> None:
    saved_inputs = load_page_state(PAGE_KEY, PAGE_DEFAULTS)

    st.title("Strategy Cockpit")
    st.caption(
        "One confirmed action, one target allocation, and one next condition. Signals use completed daily data and trades occur only when the state changes."
    )

    with st.sidebar:
        st.header("Operating setup")
        policy_keys = [policy.key for policy in OPERATING_POLICIES]
        policy_labels = [policy.label for policy in OPERATING_POLICIES]
        saved_policy = str(saved_inputs.get("operating_policy", "baseline"))
        selected_index = policy_keys.index(saved_policy) if saved_policy in policy_keys else 0
        selected_policy_label = st.selectbox(
            "Policy",
            options=policy_labels,
            index=selected_index,
            help="The frozen baseline remains the default. Challengers are clearly labeled and do not alter the baseline specification.",
        )
        policy = next(item for item in OPERATING_POLICIES if item.label == selected_policy_label)
        operating_policy_key = policy.key
        st.caption(f"{policy.research_status}. {policy.description}")

        account_value = st.number_input(
            "Strategy account value ($)",
            min_value=0.0,
            value=float(saved_inputs.get("account_value", 100_000.0)),
            step=1_000.0,
            help="Used only to estimate the allocation change; it is saved locally with the app state.",
        )
        current_tqqq_pct = st.number_input(
            "Current TQQQ allocation (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(saved_inputs.get("current_tqqq_pct", 0.0)),
            step=1.0,
            help="Update this after a fill so the order estimate reconciles the model target with your account.",
        )
        defensive_asset = DEFENSIVE_ASSET
        st.caption("The remainder of the account is held in VOO; cash is never the model target.")
        if st.button("Refresh data"):
            st.cache_data.clear()

        with st.expander("Data controls"):
            end_date = st.date_input("Data end date", value=pd.Timestamp(DEFAULT_END_DATE))
            st.caption("The operating state is always rebuilt from TQQQ inception. A historical end date becomes stale and cannot issue a confirmed trade.")

        sma_window = int(PAGE_DEFAULTS["sma_window"])
        upper_band_pct = float(PAGE_DEFAULTS["upper_band_pct"])
        lower_band_pct = float(PAGE_DEFAULTS["lower_band_pct"])
        st.caption("Frozen operating parameters: 200-day SMA, +1% entry band, -1% reset band, next-open execution.")

    save_page_state(
        PAGE_KEY,
        {
            "sma_window": int(sma_window),
            "upper_band_pct": float(upper_band_pct),
            "lower_band_pct": float(lower_band_pct),
            "defensive_asset": defensive_asset,
            "operating_policy": operating_policy_key,
            "account_value": float(account_value),
            "current_tqqq_pct": float(current_tqqq_pct),
        },
        last_page=PAGE_KEY,
    )

    if pd.Timestamp(OPERATIONAL_START_DATE) >= pd.Timestamp(end_date):
        st.error("Data end date must be after the strategy inception date.")
        return

    upper_band = float(upper_band_pct) / 100
    lower_band = float(lower_band_pct) / 100

    try:
        raw_data = download_market_data(pd.Timestamp(OPERATIONAL_START_DATE), pd.Timestamp(end_date))
        result = simulate_strategy(
            raw_data,
            ResearchConfig(
                sma_window=int(sma_window),
                upper_band=upper_band,
                lower_band=lower_band,
                exit_mode=policy.exit_mode,
                cost_bps_per_leg=5.0,
            ),
        )
        strategy_frame = result.frame
        if policy.key == "entry_locked_60":
            sized = simulate_entry_locked_policy(
                raw_data,
                result.frame,
                LowTradeSpec(
                    "entry_locked_60",
                    policy.label,
                    "entry_target",
                    target_vol=float(policy.target_volatility),
                ),
            )
            strategy_frame = result.frame.copy()
            for column in ("strategy_return", "strategy_equity", "tqqq_weight", "voo_weight", "turnover"):
                strategy_frame[column] = sized[column]
            strategy_frame["strategy_peak"] = strategy_frame["strategy_equity"].cummax()
            strategy_frame["strategy_drawdown"] = strategy_frame["strategy_equity"] / strategy_frame["strategy_peak"] - 1.0
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
    action_plan = build_action_plan(
        raw_data,
        result,
        policy,
        freshness,
        float(account_value),
        float(current_tqqq_pct),
        upper_band,
        lower_band,
    )
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
    strategy_annualized_return = annualized_return(strategy_frame["strategy_equity"])
    voo_annualized_return = annualized_return(strategy_frame["voo_buy_hold_equity"])
    strategy_sharpe = sharpe_ratio(strategy_frame["strategy_return"])
    voo_buy_hold_sharpe = sharpe_ratio(strategy_frame["voo_buy_hold_return"])

    st.subheader("Today’s instruction")
    action_kind = str(action_plan["action_kind"])
    action_message = f"{action_plan['action']} — {action_plan['order_text']}"
    if action_kind == "stale":
        st.error(action_message)
    elif action_kind in {"enter", "exit"}:
        st.warning(action_message)
    else:
        st.success(action_message)

    state_metrics = st.columns(4)
    state_metrics[0].metric("Action", str(action_plan["action"]))
    state_metrics[1].metric(
        "Target allocation",
        f"{float(action_plan['target_tqqq_weight']) * 100:.0f}% TQQQ",
        help=f"The remaining {float(action_plan['target_voo_weight']) * 100:.0f}% is VOO.",
    )
    state_metrics[2].metric("When", str(action_plan["timing"]))
    state_metrics[3].metric("Signal session", str(action_plan["signal_session"]))

    allocation_metrics = st.columns(3)
    allocation_metrics[0].metric("Target TQQQ", format_usd(float(action_plan["target_tqqq_dollars"])))
    allocation_metrics[1].metric("Target VOO", format_usd(float(action_plan["target_voo_dollars"])))
    allocation_metrics[2].metric("Model holding", str(action_plan["active_asset"]))

    st.markdown(f"**Why:** {action_plan['signal_event']}. Current phase: {action_plan['phase']}.")
    st.markdown(f"**What would change this:** {action_plan['next_condition']}")
    if action_plan["realized_volatility"] is not None:
        st.caption(
            f"Sizing volatility: {float(action_plan['realized_volatility']) * 100:.1f}% annualized. "
            f"{action_plan['sizing_basis']} The weight stays locked until exit."
        )

    with st.expander("Execution checklist", expanded=action_kind in {"enter", "exit"}):
        st.markdown(
            f"""
1. Confirm the latest completed session is **{action_plan['signal_session']}** and data status is fresh.
2. Use the selected policy: **{policy.label}**.
3. If an allocation change is required, execute at the **next market open**; do not anticipate an unconfirmed close.
4. Target **{float(action_plan['target_tqqq_weight']) * 100:.1f}% TQQQ / {float(action_plan['target_voo_weight']) * 100:.1f}% VOO**.
5. Record the actual fill, then update “Current TQQQ allocation” in the sidebar.
            """
        )

    if freshness["status"] == "fresh" and st.button("Record this instruction"):
        record_recommendation(
            {
                "strategy_version": STRATEGY_VERSION,
                "session": strategy_frame.index[-1].date().isoformat(),
                "policy_key": policy.key,
                "policy_label": policy.label,
                "action": action_plan["action"],
                "note": action_plan["order_text"],
                "signal_distance_to_sma": float(latest["distance_to_sma"]),
                "target_asset": str(latest["target_asset"]),
                "active_asset": str(latest["active_asset"]),
                "signal_event": str(latest["event"] or ""),
                "target_tqqq_weight": float(action_plan["target_tqqq_weight"]),
                "account_value": float(account_value),
            }
        )
        st.success("Instruction recorded.")

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
    st.plotly_chart(build_signal_check_figure(strategy_frame, upper_band, lower_band), width="stretch")

    with st.expander("More charts and performance"):
        st.subheader("Performance details")
        st.caption(f"Full-history simulation for: {policy.label}")
        summary = pd.DataFrame(
            {
                "Metric": [
                    "Total return",
                    "Annualized return",
                    "Sharpe ratio",
                    "Final equity",
                    "Max drawdown",
                    "Time invested",
                ],
                policy.label: [
                    format_pct(total_return),
                    format_pct(strategy_annualized_return),
                    f"{strategy_sharpe:.2f}",
                    format_usd(strategy_frame["strategy_equity"].iloc[-1]),
                    format_pct(max_drawdown),
                    format_pct(time_in_market),
                ],
                "VOO Buy & Hold": [
                    format_pct(voo_buy_hold_return),
                    format_pct(voo_annualized_return),
                    f"{voo_buy_hold_sharpe:.2f}",
                    format_usd(strategy_frame["voo_buy_hold_equity"].iloc[-1]),
                    "",
                    "",
                ],
            }
        )
        st.dataframe(summary, width="stretch", hide_index=True)

        st.subheader("S&P 500 Price and Trigger Levels")
        st.plotly_chart(build_price_regime_figure(strategy_frame, upper_band, lower_band), width="stretch")

        st.subheader("S&P 500 Distance from 200-day SMA")
        st.plotly_chart(build_percent_regime_figure(strategy_frame, upper_band, lower_band), width="stretch")

        st.subheader("Equity curve")
        st.plotly_chart(build_equity_figure(strategy_frame), width="stretch")

        st.subheader("Drawdown")
        st.plotly_chart(build_drawdown_figure(strategy_frame), width="stretch")

    with st.expander("Trade log"):
        if trades.empty:
            st.info("No TQQQ episodes were generated for the selected period.")
        elif policy.key == "entry_locked_60":
            st.caption("These are the entry and exit dates from the signal engine. Return columns are omitted because this policy uses entry-locked partial sizing.")
            date_columns = [
                column
                for column in (
                    "Status",
                    "Entry signal date",
                    "Entry fill date",
                    "Exit signal date",
                    "Exit fill date",
                    "Exit reason",
                )
                if column in trades.columns
            ]
            st.dataframe(trades[date_columns], width="stretch", hide_index=True)
        else:
            st.dataframe(trades, width="stretch", hide_index=True)

    with st.expander("Decision journal"):
        journal = load_journal()
        if journal.empty:
            st.info("No recommendations or fills have been recorded yet.")
        else:
            st.dataframe(journal, width="stretch", hide_index=True)
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
                "tqqq_weight",
                "strategy_equity",
                "voo_buy_hold_equity",
            ]
        ].copy()
        display_frame["distance_to_sma"] = (display_frame["distance_to_sma"] * 100).round(2)
        st.dataframe(display_frame, width="stretch")
