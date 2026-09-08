# TQQQ / VOO strategy research — one-page status

Run: 2026-09-08T17:31:54.170872+00:00  
Coverage: 2010-09-09–2026-09-08 (4,023 common sessions; auto-adjusted yfinance OHLC)

## Bottom line

The strategy is now a reproducible research system rather than an experimental dashboard, but it is not promoted to production. The frozen baseline rotates a dedicated account between VOO and TQQQ, confirms signals after the close, uses next-session execution, and compares each risk-on episode against simply retaining VOO.

## Baseline evidence

- Full-period return: 2462.84% vs VOO 813.81%; paired difference 1649.04 percentage points.
- Maximum drawdown: -75.48%; Sharpe 0.68; TQQQ exposure 33.21%.
- Risk-on ledger: 9 episodes, 9 closed; 66.7% beat VOO after 5 bps per leg; median excess 9.09 percentage points.
- Walk-forward: 11 expanding one-year test folds; 72.7% beat VOO. The sample is sparse and outcome concentration remains material.

## What is now covered

One event-driven simulator feeds the app, fills, paired VOO ledger, execution/cost matrix, reset/exit/trail experiments, QQQ/weekly/50%-TQQQ challengers, walk-forward folds, bootstrap uncertainty, concentration, data manifest/snapshot, freshness checks, and a recommendation/fill journal.

## Important limitations

Daily scenarios bound next-open, next-close, and second-session-open behavior; they do not reconstruct 09:35/10:00/11:00 prices. A standing intraday stop-market study is withheld because the full history lacks reliable intraday bars. The volatility-cap and pullback families were deferred until their rules can be frozen without hindsight. Paper validation has not occurred yet.

## Decision

Status: **research only / inconclusive for promotion**. Before considering a live rule, set a dedicated-account drawdown and VOO-underperformance limit, complete at least six months and three signal changes of paper observations (or twelve months if sparse), and recalibrate fill/slippage assumptions from actual records.

See `scorecard.csv`, `episode_ledger.csv`, `execution_matrix.csv`, `walk_forward_folds.csv`, `experiment_register.csv`, `decision_guidelines.md`, and `PAPER_VALIDATION.md`.
