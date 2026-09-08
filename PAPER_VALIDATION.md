# Prospective paper validation

Status: pending observation window. Historical research is complete for the current run, but a paper period cannot be backfilled.

Use the daily signal command after a completed market session:

```powershell
cd tqqq-dashboard
python daily_signal.py
```

For each recommendation, record the signal session, when the notification was seen, order submission time, order type, intended fill window, actual fill time and price, asset sold, asset bought, and any reason for a missed or changed order. The model recommendation and the human fill are separate records.

Minimum observation window: six months and at least three signal changes, or twelve months if fewer than three changes occur. A quiet period is an operational result, not performance confirmation.

Compare observed entry and exit slippage with the tested 0/5/10/25 basis-point scenarios. Keep all observations, including missed signals and rejected orders. Do not alter the frozen baseline during the observation window.

The promotion gate remains inconclusive until the observation window, an agreed dedicated-account drawdown limit, and the historical evidence scorecard are reviewed together.
