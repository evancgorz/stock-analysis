# Satellite strategy comparison

Data: 2010-09-09 through 2026-09-08 (4,023 common sessions including QLD)
Execution: completed daily signal, next-session open; 5 bps per traded weight-leg equivalent; no intraday stop assumption

## Conclusion

This fixed comparison produced 6 alternatives with at least the current CAGR and a less severe maximum drawdown. That is encouraging, but it is not proof of a durable edge: the policies were tested on the same historical sample, and the volatility rules still need a genuinely untouched validation period and real fill data.

The most credible improvement to investigate next is volatility-aware sizing or a TQQQ/QLD ladder. These reduce exposure when prior TQQQ volatility is high, which is economically plausible and supported by volatility-management research, but the historical results must still survive a frozen walk-forward test and real execution.

## Policy comparison

| Policy | CAGR % | Max drawdown % | Sharpe | Sortino | Excess vs VOO % | Risk-on time % | Average TQQQ weight % | Turnover |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Current strategy: 100% TQQQ risk-on | 22.57 | -75.48 | 0.68 | 0.75 | 1649.04 | 33.21 | 33.21 | 36.00 |
| TQQQ volatility target 60% | 25.26 | -62.65 | 0.81 | 0.92 | 2714.70 | 33.21 | 28.29 | 64.81 |
| TQQQ volatility target 50% | 25.19 | -56.98 | 0.84 | 0.96 | 2680.10 | 33.21 | 26.04 | 70.95 |
| TQQQ volatility target 40% | 24.54 | -50.73 | 0.87 | 1.00 | 2394.67 | 33.21 | 22.61 | 74.35 |
| TQQQ volatility target 30% | 23.06 | -44.45 | 0.89 | 1.04 | 1818.05 | 33.21 | 18.02 | 68.34 |
| TQQQ half-size when prior volatility exceeds 60% | 24.82 | -52.97 | 0.83 | 0.94 | 2513.99 | 33.21 | 25.22 | 60.00 |
| 50% TQQQ / 50% VOO risk-on | 20.15 | -52.97 | 0.76 | 0.87 | 948.51 | 33.21 | 16.60 | 18.00 |
| QLD instead of TQQQ, same signal and timing | 21.11 | -57.36 | 0.77 | 0.88 | 1202.26 | 33.21 | 0.00 | 36.00 |
| 50% TQQQ / 50% QLD risk-on | 22.14 | -67.29 | 0.72 | 0.80 | 1508.67 | 33.21 | 16.60 | 36.00 |
| TQQQ in calm conditions, QLD in high volatility | 24.87 | -57.36 | 0.82 | 0.93 | 2537.75 | 33.21 | 17.23 | 98.00 |

## Walk-forward consistency

| Policy key | count | positive_fold_pct | mean_excess | worst_excess |
| --- | --- | --- | --- | --- |
| current_tqqq | 11 | 54.55 | 12.78 | -44.87 |
| leverage_ladder | 11 | 63.64 | 12.66 | -26.78 |
| qld_same_signal | 11 | 54.55 | 8.88 | -26.78 |
| tqqq_half | 11 | 54.55 | 7.00 | -23.60 |
| tqqq_high_vol_half | 11 | 63.64 | 11.96 | -23.60 |
| tqqq_qld_mix | 11 | 54.55 | 11.03 | -36.17 |
| tqqq_target_30 | 11 | 63.64 | 9.95 | -15.98 |
| tqqq_target_40 | 11 | 63.64 | 12.77 | -21.28 |
| tqqq_target_50 | 11 | 63.64 | 14.46 | -26.34 |
| tqqq_target_60 | 11 | 63.64 | 15.35 | -31.24 |

Fold-by-fold comparison against current strategy: tqqq_target_60: better than current in 4/11 folds; mean difference 2.58 percentage points; tqqq_target_50: better than current in 4/11 folds; mean difference 1.69 percentage points; tqqq_high_vol_half: better than current in 4/11 folds; mean difference -0.82 percentage points; leverage_ladder: better than current in 4/11 folds; mean difference -0.12 percentage points.

## Pareto result

Policies that matched or exceeded the current strategy's CAGR while having a less severe maximum drawdown: 6.
| Policy | CAGR % | Max drawdown % | Sharpe |
| --- | --- | --- | --- |
| TQQQ volatility target 60% | 25.26 | -62.65 | 0.81 |
| TQQQ volatility target 50% | 25.19 | -56.98 | 0.84 |
| TQQQ volatility target 40% | 24.54 | -50.73 | 0.87 |
| TQQQ volatility target 30% | 23.06 | -44.45 | 0.89 |
| TQQQ half-size when prior volatility exceeds 60% | 24.82 | -52.97 | 0.83 |
| TQQQ in calm conditions, QLD in high volatility | 24.87 | -57.36 | 0.82 |

## Interpretation

- QLD and QQQ reduce leverage risk, but they should be expected to give up some upside in the strongest trends.
- Volatility targeting can reduce drawdown and improve Sharpe, but it can also cut exposure before a sharp rebound. It is a risk-control candidate, not a guaranteed return enhancer.
- The ladder is attractive operationally because it uses a small number of discrete states rather than continuously changing weights.
- The test holds the signal and timing constant. It does not yet prove that a separately optimized signal would be better.

## Research context

TQQQ and QLD are daily-target leveraged ETFs; their multi-day results can differ materially from a simple 3x or 2x multiple because of daily reset and compounding.[1][2] Research on volatility-managed portfolios provides a rationale for reducing exposure when volatility rises, while later work cautions that out-of-sample implementation can be unstable.[3][4] Time-series momentum research supports testing trend persistence, but its original evidence is broader futures markets rather than a guarantee for this ETF rule.[5]

## Decision

Keep the current strategy as the reference. Promote no alternative yet. Advance only the volatility-target and TQQQ/QLD-ladder candidates to a second-stage test with preregistered parameters, separate development/validation dates, actual fill records, and a stated drawdown limit.

## Sources

1. [ProShares TQQQ](https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq) — daily 3x Nasdaq-100 objective and multi-day divergence warning.
2. [ProShares QLD](https://www.proshares.com/our-etfs/leveraged-and-inverse/qld) — daily 2x Nasdaq-100 objective and compounding warning.
3. [Moreira and Muir, Volatility Managed Portfolios, NBER](https://www.nber.org/papers/w22208) — rationale for reducing risk when volatility is high.
4. [Cederburg et al., On the performance of volatility-managed portfolios](https://www.sciencedirect.com/science/article/pii/S0304405X2030132X) — out-of-sample and implementation caution.
5. [Moskowitz, Ooi, and Pedersen, Time Series Momentum](https://fairmodel.econ.yale.edu/ec439/mosk.pdf) — original trend-persistence evidence across liquid futures.