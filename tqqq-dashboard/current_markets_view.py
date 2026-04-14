from __future__ import annotations

import pandas as pd
import streamlit as st
import yfinance as yf


TICKERS = ["TQQQ", "SPY", "QQQ"]


@st.cache_data(show_spinner=False, ttl=3600)
def load_daily_reference_data() -> pd.DataFrame:
    raw = yf.download(
        TICKERS,
        period="2y",
        interval="1d",
        auto_adjust=True,
        progress=False,
    )

    if raw.empty:
        raise ValueError("No data returned from yfinance.")

    closes = raw["Close"].copy()
    closes.index = pd.to_datetime(closes.index)
    closes = closes.dropna(how="all")

    rows: list[dict[str, float | str]] = []
    for ticker in TICKERS:
        series = closes[ticker].dropna()
        if len(series) < 200:
            continue

        trailing_year = series.tail(252)
        sma_200 = float(series.rolling(200).mean().iloc[-1])

        rows.append(
            {
                "Ticker": ticker,
                "52-week high": float(trailing_year.max()),
                "52-week low": float(trailing_year.min()),
                "200-day SMA": sma_200,
                "Prev close": float(series.iloc[-2]) if len(series) > 1 else float(series.iloc[-1]),
            }
        )

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, ttl=5)
def load_live_prices() -> pd.DataFrame:
    intraday = yf.download(
        TICKERS,
        period="5d",
        interval="1m",
        auto_adjust=True,
        progress=False,
        prepost=True,
    )

    if intraday.empty:
        raise ValueError("No intraday data returned from yfinance.")

    closes = intraday["Close"].copy()
    closes.index = pd.to_datetime(closes.index)
    closes = closes.dropna(how="all")

    rows: list[dict[str, float | str]] = []
    for ticker in TICKERS:
        series = closes[ticker].dropna()
        if series.empty:
            continue
        rows.append(
            {
                "Ticker": ticker,
                "Price": float(series.iloc[-1]),
            }
        )

    return pd.DataFrame(rows)


def load_current_market_snapshot() -> pd.DataFrame:
    reference = load_daily_reference_data()
    live = load_live_prices()
    snapshot = reference.merge(live, on="Ticker", how="left")
    snapshot["Price"] = snapshot["Price"].fillna(snapshot["Prev close"])
    snapshot["Day change %"] = snapshot["Price"] / snapshot["Prev close"] - 1.0
    return snapshot[["Ticker", "Price", "Day change %", "52-week high", "52-week low", "200-day SMA"]]


def format_price(value: float) -> str:
    return f"{value:,.2f}"


def format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def color_day_change(value: float) -> str:
    if value > 0:
        return "color: #0d7a5f; font-weight: 700;"
    if value < 0:
        return "color: #a12e2b; font-weight: 700;"
    return "color: #6b7280; font-weight: 700;"


@st.fragment(run_every="1s")
def render_live_snapshot() -> None:
    st.caption(
        "Auto-refreshing while open. Quick snapshot for TQQQ, SPY, and QQQ with price, daily move, 52-week range, and 200-day SMA."
    )

    try:
        snapshot = load_current_market_snapshot()
    except Exception as exc:
        st.error(f"Could not load market snapshot: {exc}")
        return

    if snapshot.empty:
        st.warning("No market snapshot data is available right now.")
        return

    cards = st.columns(len(snapshot))
    for idx, (_, row) in enumerate(snapshot.iterrows()):
        with cards[idx]:
            cards[idx].metric(
                row["Ticker"],
                format_price(float(row["Price"])),
                format_pct(float(row["Day change %"])),
            )
            st.caption(
                f"52W: {format_price(float(row['52-week low']))} to {format_price(float(row['52-week high']))}"
            )
            st.caption(f"200D SMA: {format_price(float(row['200-day SMA']))}")

    display = snapshot.copy()
    styled = (
        display.style
        .format(
            {
                "Price": "{:,.2f}",
                "Day change %": lambda v: f"{v * 100:.2f}%",
                "52-week high": "{:,.2f}",
                "52-week low": "{:,.2f}",
                "200-day SMA": "{:,.2f}",
            }
        )
        .map(color_day_change, subset=["Day change %"])
    )

    st.subheader("Market Snapshot")
    st.dataframe(styled, use_container_width=True, hide_index=True)


def render() -> None:
    st.title("Current Markets")

    if st.sidebar.button("Refresh market snapshot"):
        st.cache_data.clear()

    render_live_snapshot()
