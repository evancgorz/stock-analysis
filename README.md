# Stock Analysis

This repo contains a Streamlit stock-analysis app focused on a `Play the Dip` TQQQ strategy and its parameter research tools.

## What It Includes

- `Home`: the main `Play the Dip` dashboard with live `yfinance` data
- `Grid Search`: a research page for sweeping SMA windows and matched `+/-` thresholds
- persistent UI settings for strategy parameters and page state

## Strategy Summary

The current strategy:

- uses the S&P 500 total-return index (`^SP500TR`) as the regime signal
- calculates a rolling SMA window
- enters TQQQ when the S&P 500 rises above the upper threshold relative to its SMA
- activates a TQQQ close-based trailing exit after a fresh S&P 500 all-time high
- waits for the S&P 500 to drop below the lower threshold before re-arming the next buy
- rotates off-regime exposure into `VOO` (the strategy never uses cash)

The research baseline is evaluated against continuous VOO during the same risk-on intervals and includes next-session execution, paired episode ledgers, cost/delay matrices, walk-forward folds, bounded alternatives, and an explicit paper-validation gate.

The latest fixed-rule risk/return comparison is published in [`research_reports/strategy_comparison/strategy_comparison.md`](C:\Github\stock-analysis\research_reports\strategy_comparison\strategy_comparison.md).

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
