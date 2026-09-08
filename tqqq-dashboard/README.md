# TQQQ Strategy Dashboard

This Streamlit app focuses on a rules-based TQQQ strategy and the supporting analysis tools around it.

## Pages

- `Home`: main strategy dashboard
- `Current Markets`: live snapshot for TQQQ, SPY, and QQQ
- `Grid Search`: sweep SMA windows and matched thresholds to compare win rate, Sharpe ratio, and strategy vs VOO return

## Strategy

The current strategy model:

- uses the S&P 500 total return index via `^SP500TR` as the signal series
- calculates a rolling SMA
- buys TQQQ when the S&P 500 rises above the upper threshold relative to the SMA
- activates a TQQQ close-based trailing exit after the S&P 500 prints a fresh all-time high
- only re-arms after the S&P 500 drops below the lower threshold
- holds `VOO` while off-regime; the strategy never uses cash

Signals are generated after the close and executed at the next trading day's open. The backtest accounts separately for the prior position's overnight gap and the new position's open-to-close return.

The strategy account is always invested in exactly one asset: `VOO` or `TQQQ`.

## Main Files

- `app.py`: Streamlit entry point with explicit app navigation
- `home_view.py`: main strategy dashboard
- `current_markets_view.py`: live market snapshot page
- `grid_search_view.py`: parameter grid search workspace
- `robustness_view.py`: train/test walk-forward robustness checks
- `research_engine.py`: shared event-driven simulator, fills, paired VOO episodes, and diagnostics
- `research_runner.py`: reproducible report generator and experiment register
- `PAPER_VALIDATION.md`: prospective operational validation protocol
- `STRATEGY_SPEC.md`: canonical account, signal, exit, and execution rules
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
