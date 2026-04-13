from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


INITIAL_CAPITAL = 100_000.0


@dataclass
class Trade:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    return_pct: float
    exit_reason: str
    status: str


@st.cache_data(show_spinner=False, ttl=3600)
def download_market_data(start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    raw = yf.download(
        ["TQQQ", "VOO", "^GSPC"],
        start=start_date.strftime("%Y-%m-%d"),
        end=(end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )

    if raw.empty:
        raise ValueError("No data returned from yfinance.")

    closes = raw["Close"].rename(
        columns={"TQQQ": "tqqq_close", "VOO": "voo_close", "^GSPC": "spx_close"}
    )
    data = closes.dropna().copy()
    data.index = pd.to_datetime(data.index)
    return data.sort_index()


def format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def format_usd(value: float) -> str:
    return f"${value:,.0f}"


def annualized_return(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    total_return = equity.iloc[-1] / equity.iloc[0]
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1 / 365.25)
    return total_return ** (1 / years) - 1


def sharpe_ratio(returns: pd.Series) -> float:
    volatility = returns.std()
    if volatility == 0 or np.isnan(volatility):
        return 0.0
    return (returns.mean() / volatility) * np.sqrt(252)


def build_play_the_dip_frame(
    data: pd.DataFrame,
    sma_window: int,
    upper_band: float,
    lower_band: float,
    defensive_asset: str,
) -> pd.DataFrame:
    frame = data.copy()
    frame["spx_sma"] = frame["spx_close"].rolling(sma_window).mean()
    frame["distance_to_sma"] = frame["spx_close"] / frame["spx_sma"] - 1.0
    frame["prior_ath"] = frame["spx_close"].cummax().shift(1)
    frame["is_new_ath"] = frame["spx_close"] > frame["prior_ath"].fillna(-np.inf)

    ready = frame.dropna(subset=["spx_sma"]).copy()

    signals = []
    phases = []
    events = []

    target_long = False
    awaiting_reset = False
    buy_armed = True

    for _, row in ready.iterrows():
        event = ""
        distance = row["distance_to_sma"]

        if target_long and row["is_new_ath"]:
            target_long = False
            awaiting_reset = True
            buy_armed = False
            event = "New S&P 500 ATH"
        elif awaiting_reset and distance < lower_band:
            awaiting_reset = False
            buy_armed = True
            event = "Reset level reached"
        elif (not target_long) and buy_armed and distance > upper_band:
            target_long = True
            buy_armed = False
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

    ready["signal"] = signals
    ready["phase"] = phases
    ready["event"] = events
    ready["position"] = ready["signal"].shift(1).fillna(0.0)
    ready["tqqq_return"] = ready["tqqq_close"].pct_change().fillna(0.0)
    ready["voo_return"] = ready["voo_close"].pct_change().fillna(0.0)
    ready["spx_return"] = ready["spx_close"].pct_change().fillna(0.0)
    ready["defensive_return"] = 0.0 if defensive_asset == "Cash" else ready["voo_return"]
    ready["active_asset"] = np.where(ready["position"] == 1.0, "TQQQ", defensive_asset)
    ready["strategy_return"] = ready["position"] * ready["tqqq_return"]
    ready["strategy_return"] += (1.0 - ready["position"]) * ready["defensive_return"]
    ready["buy_hold_return"] = ready["tqqq_return"]
    ready["voo_buy_hold_return"] = ready["voo_return"]
    ready["spx_buy_hold_return"] = ready["spx_return"]
    ready["strategy_equity"] = INITIAL_CAPITAL * (1 + ready["strategy_return"]).cumprod()
    ready["buy_hold_equity"] = INITIAL_CAPITAL * (1 + ready["buy_hold_return"]).cumprod()
    ready["voo_buy_hold_equity"] = INITIAL_CAPITAL * (1 + ready["voo_buy_hold_return"]).cumprod()
    ready["spx_buy_hold_equity"] = INITIAL_CAPITAL * (1 + ready["spx_buy_hold_return"]).cumprod()
    ready["strategy_peak"] = ready["strategy_equity"].cummax()
    ready["strategy_drawdown"] = ready["strategy_equity"] / ready["strategy_peak"] - 1.0

    return ready


def extract_trades(frame: pd.DataFrame) -> pd.DataFrame:
    position_changes = frame["position"].diff().fillna(frame["position"])
    entries = frame.index[position_changes == 1.0]
    exits = frame.index[position_changes == -1.0]

    if frame["position"].iloc[0] == 1.0:
        entries = pd.Index([frame.index[0]]).append(entries)
    if len(exits) < len(entries):
        exits = exits.append(pd.Index([frame.index[-1]]))

    trades = []
    for entry_date, exit_date in zip(entries, exits):
        entry_price = float(frame.loc[entry_date, "tqqq_close"])
        exit_price = float(frame.loc[exit_date, "tqqq_close"])
        has_real_exit = position_changes.loc[exit_date] == -1.0
        exit_event = frame.loc[exit_date, "event"]
        if has_real_exit:
            exit_reason = str(exit_event or "Exit signal")
            status = "Closed"
        else:
            exit_reason = "Open trade as of selected end date"
            status = "Open"
        trades.append(
            Trade(
                entry_date=entry_date,
                exit_date=exit_date,
                entry_price=entry_price,
                exit_price=exit_price,
                return_pct=exit_price / entry_price - 1.0,
                exit_reason=exit_reason,
                status=status,
            )
        )

    return pd.DataFrame(
        [
            {
                "Status": trade.status,
                "Entry date": trade.entry_date.date(),
                "Exit date": trade.exit_date.date(),
                "Entry price": round(trade.entry_price, 2),
                "Exit price": round(trade.exit_price, 2),
                "Return %": round(trade.return_pct * 100, 2),
                "Exit reason": trade.exit_reason,
            }
            for trade in trades
        ]
    )
