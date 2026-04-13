# Stock Analysis

This repo contains a Streamlit stock-analysis app focused on a `Play the Dip` TQQQ strategy and its parameter research tools.

## What It Includes

- `Home`: the main `Play the Dip` dashboard with live `yfinance` data
- `Grid Search`: a research page for sweeping SMA windows and matched `+/-` thresholds
- persistent UI settings for strategy parameters and page state

## Strategy Summary

The current strategy:

- uses the S&P 500 (`^GSPC`) as the regime signal
- calculates a rolling SMA window
- enters TQQQ when the S&P 500 rises above the upper threshold relative to its SMA
- exits on a fresh S&P 500 all-time high
- waits for the S&P 500 to drop below the lower threshold before re-arming the next buy
- optionally rotates off-regime exposure into `Cash` or `VOO`

## Project Layout

- [`tqqq-dashboard/app.py`](C:\Users\GORCZYNE\OneDrive - Zoetis\Documents\New project\tqqq-dashboard\app.py): app entry point and explicit two-page navigation
- [`tqqq-dashboard/home_view.py`](C:\Users\GORCZYNE\OneDrive - Zoetis\Documents\New project\tqqq-dashboard\home_view.py): main strategy dashboard
- [`tqqq-dashboard/grid_search_view.py`](C:\Users\GORCZYNE\OneDrive - Zoetis\Documents\New project\tqqq-dashboard\grid_search_view.py): parameter grid search
- [`tqqq-dashboard/play_the_dip_logic.py`](C:\Users\GORCZYNE\OneDrive - Zoetis\Documents\New project\tqqq-dashboard\play_the_dip_logic.py): shared backtest logic

## Run Locally

```powershell
cd "C:\Users\GORCZYNE\OneDrive - Zoetis\Documents\New project\tqqq-dashboard"
pip install -r requirements.txt
streamlit run app.py
```

Or use the included launcher:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\GORCZYNE\OneDrive - Zoetis\Documents\New project\tqqq-dashboard\run_dashboard.ps1"
```
