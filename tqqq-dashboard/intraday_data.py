from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class IntradayAvailability:
    ticker: str
    interval: str
    requested_start: str
    requested_end: str
    rows: int
    first_bar: str | None
    last_bar: str | None
    status: str
    note: str


def download_recent_intraday(
    ticker: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    interval: str = "5m",
) -> tuple[pd.DataFrame, IntradayAvailability]:
    requested_days = (end.normalize() - start.normalize()).days
    if requested_days > 60:
        return pd.DataFrame(), IntradayAvailability(
            ticker,
            interval,
            start.date().isoformat(),
            end.date().isoformat(),
            0,
            None,
            None,
            "unavailable",
            "Yahoo Finance does not provide a reliable multi-year intraday history through this interface; use a recorded intraday feed for historical validation.",
        )
    raw = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        interval=interval,
        auto_adjust=True,
        prepost=False,
        progress=False,
    )
    if raw.empty:
        return pd.DataFrame(), IntradayAvailability(
            ticker,
            interval,
            start.date().isoformat(),
            end.date().isoformat(),
            0,
            None,
            None,
            "unavailable",
            "No intraday observations were returned.",
        )
    frame = raw.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame.index = pd.to_datetime(frame.index)
    frame = frame.dropna(how="all")
    availability = IntradayAvailability(
        ticker,
        interval,
        start.date().isoformat(),
        end.date().isoformat(),
        len(frame),
        frame.index[0].isoformat() if not frame.empty else None,
        frame.index[-1].isoformat() if not frame.empty else None,
        "available" if not frame.empty else "unavailable",
        "Use the first bar after submission and record the actual market timezone and order type when calibrating fills.",
    )
    return frame, availability


def fill_window(frame: pd.DataFrame, submission_time: pd.Timestamp) -> pd.DataFrame:
    """Return bars after an order submission; caller chooses the fill rule."""
    if frame.empty:
        return frame
    timestamp = submission_time
    if timestamp.tzinfo is None and frame.index.tz is not None:
        timestamp = timestamp.tz_localize(frame.index.tz)
    return frame.loc[frame.index >= timestamp]
