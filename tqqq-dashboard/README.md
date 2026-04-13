# TQQQ Strategy Dashboard

This Streamlit app focuses on the `Play the Dip` strategy and the analysis tools around it.

## Pages

- `Home`: main strategy dashboard
- `Grid Search`: sweep SMA windows and matched thresholds to compare win rate, Sharpe ratio, and strategy vs S&P 500 return

## Strategy

The current `Play the Dip` model:

- uses `^GSPC` as the signal series
- calculates a rolling SMA
- buys TQQQ when the S&P 500 rises above the upper threshold relative to the SMA
- sells when the S&P 500 prints a fresh all-time high
- only re-arms after the S&P 500 drops below the lower threshold
- holds either `Cash` or `VOO` while off-regime

To avoid lookahead bias, the app applies the signal from one trading day to the next trading day's TQQQ return.

## Main Files

- `app.py`: Streamlit entry point with explicit `Home` and `Grid Search` navigation
- `home_view.py`: main strategy dashboard
- `grid_search_view.py`: parameter grid search workspace
- `play_the_dip_logic.py`: shared data download and backtest logic
- `state_store.py`: lightweight saved UI state

## Run It

```powershell
cd "C:\Users\GORCZYNE\OneDrive - Zoetis\Documents\New project\tqqq-dashboard"
pip install -r requirements.txt
streamlit run app.py
```

Or:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\GORCZYNE\OneDrive - Zoetis\Documents\New project\tqqq-dashboard\run_dashboard.ps1"
```
