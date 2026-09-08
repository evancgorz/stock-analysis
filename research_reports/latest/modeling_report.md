# TQQQ / VOO modeling report

Run date: 2026-09-08T17:31:54.170872+00:00
Code revision at data retrieval: 0302859a589e85738ca742970079f77f75eeb24f
Data: 2010-09-09 through 2026-09-08, 4023 common sessions
Provider: yfinance; prices are auto-adjusted

## Research conclusion

This is a historical research report, not a promotion decision. The baseline is a full-account rotation between VOO and TQQQ, with a close-confirmed signal and the selected execution delay. It is evaluated against continuous VOO using the same timestamps.

The baseline full-period result was 2462.84% versus VOO at 813.81%, a paired difference of 1649.04 percentage points. Its maximum drawdown was -75.48%, Sharpe was 0.68, TQQQ exposure was 33.21%, and turnover was 18 account rotations.

The matched risk-on ledger contained 9 episodes, 9 closed, and 66.7% beat VOO after the configured costs. Median episode excess was 9.09 percentage points; compounded relative wealth across episodes was 183.00%.

    The repeated expanding-window walk-forward test had 11 one-year test folds. The selected candidate beat VOO in 72.7% of folds. The fold table is the authoritative evidence; sparse trades, large drawdowns, or a concentration in a few episodes remain grounds for an inconclusive decision.

The episode bootstrap relative-wealth interval was p05 -10.12%, median 184.47%, p95 730.02%. The synchronized daily block-bootstrap interval was p05 -69.40%, median 183.88%, p95 1796.21%. These are uncertainty summaries for realized paths, not new strategy simulations.

## Accounting and implementation rules

- Signals use completed daily bars. The signal is never allowed to see a future bar.
- Orders are scheduled from the signal close and filled according to the scenario column.
- A rotation carries the prior asset through the overnight gap, then applies the new asset from its fill phase.
- Each rotation charges two transaction legs at 5 basis points per leg. Slippage is separate and currently 0 basis points per leg.
- The daily scenario matrix is a bound and sensitivity study for 09:35, 10:00, and 11:00 fills. It is not an intraday price reconstruction. An intraday data study is required before claiming those clock times.
- A close-based trailing stop is a next-session signal. It is not a guaranteed 10% broker stop. Gap-through and standing stop-market variants remain separate experiments.
- The standing intraday stop-market study is explicitly withheld from promotion because the available history cannot establish within-day path ordering or realistic gap-through fills. See stop_order_study.json.

## Files in this run

- execution_matrix.csv: delay and cost sensitivity.
- experiments.csv: bounded one-change experiments and related strategies.
- walk_forward_folds.csv: expanding five-year training and one-year test folds.
- episode_ledger.csv: paired TQQQ/VOO episodes.
- fills.csv: signal dates, fill dates, assets, prices, and costs.
- data_manifest.json: coverage, missing values, retrieval time, and data hash.
- rolling_periods.csv: calendar and rolling-window diagnostics.
- uncertainty.json: episode and synchronized block-bootstrap summaries.
- scorecard.csv: dimension-by-dimension promotion status.
- experiment_register.csv: included, deferred, and unavailable related-strategy trials.
- data_snapshot.csv: the immutable common OHLC snapshot used by this run.
- intraday_availability.json: recent availability check and historical limitation.
- stop_order_study.json: explicit standing-stop outcome and required evidence.

## Decision status

Baseline status: research only / inconclusive for promotion until the drawdown, execution delay, and fill evidence meet an agreed dedicated-account limit. The report does not select a production parameter by highest historical return. Any future change must be registered, run through the same engine, and compared with the frozen baseline.
