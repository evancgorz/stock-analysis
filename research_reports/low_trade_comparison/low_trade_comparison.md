# Low-trading satellite strategy comparison

Data: 2010-09-09 through 2026-09-08 (4,023 common sessions including QLD)
Execution: same completed daily signal and next-session open; 5 bps per traded weight-leg equivalent

## Conclusion

Entry-locked policies materially reduce operational activity because the volatility decision is made once at the TQQQ entry and held until the existing exit signal. They are the right family to pursue for an investor who does not want daily management.

The current strategy has 18 rebalance days. The entry-locked volatility candidates also use the same entry/exit events, so they do not add continuous daily rebalancing. Their historical risk/return results are shown below; none should be promoted without a clean validation period.

## Comparison

| Policy | Rebalance days | Rotation-equivalent turnover | CAGR % | Max drawdown % | Sharpe | Excess vs VOO % |
| --- | --- | --- | --- | --- | --- | --- |
| Current strategy: 100% TQQQ risk-on | 18 | 18.00 | 22.57 | -75.48 | 0.68 | 1649.04 |
| Entry-locked TQQQ target 60% | 18 | 14.65 | 22.16 | -63.15 | 0.73 | 1515.22 |
| Entry-locked TQQQ target 50% | 18 | 12.47 | 21.53 | -57.36 | 0.75 | 1323.52 |
| Entry-locked TQQQ target 40% | 18 | 9.98 | 20.56 | -51.28 | 0.77 | 1053.99 |
| Entry-locked TQQQ target 30% | 18 | 7.48 | 19.41 | -45.17 | 0.80 | 773.48 |
| Entry-locked half-size above 60% volatility | 18 | 11.00 | 21.22 | -52.97 | 0.75 | 1234.42 |
| Entry-locked TQQQ/QLD volatility ladder | 18 | 18.00 | 22.09 | -57.36 | 0.76 | 1495.06 |
| Entry-locked 50% TQQQ / 50% VOO | 18 | 9.00 | 20.15 | -52.97 | 0.76 | 948.51 |

## Walk-forward consistency

| Policy key | count | positive_fold_pct | mean_excess | worst_excess |
| --- | --- | --- | --- | --- |
| current_tqqq | 11 | 54.55 | 12.78 | -44.87 |
| entry_half | 11 | 45.45 | 7.00 | -23.60 |
| entry_high_vol_half | 11 | 45.45 | 7.00 | -23.60 |
| entry_leverage_ladder | 11 | 45.45 | 8.88 | -26.78 |
| entry_target_30 | 11 | 54.55 | 5.00 | -16.61 |
| entry_target_40 | 11 | 54.55 | 6.60 | -22.04 |
| entry_target_50 | 11 | 45.45 | 8.14 | -27.35 |
| entry_target_60 | 11 | 45.45 | 9.64 | -32.50 |

## Low-attention exit-rule experiment

The entry-locked sizing tests keep the current exit rule fixed. Because exit timing is the other major source of operator burden, this separate experiment changes only the exit rule while leaving the entry signal, next-open execution, and cost model fixed.

| Policy | Rebalance days | Fills | CAGR % | Max drawdown % | Sharpe | Excess vs VOO % |
| --- | --- | --- | --- | --- | --- | --- |
| Current ATH-activated 10% trailing exit | 18 | 18 | 22.57 | -75.48 | 0.68 | 1649.04 |
| Trend-failure exit: SPX closes below its SMA | 49 | 49 | 28.40 | -59.36 | 0.81 | 4481.05 |
| Immediate 10% TQQQ close trail | 46 | 46 | 20.37 | -48.63 | 0.86 | 1004.70 |

| Policy key | count | positive_fold_pct | mean_excess | worst_excess |
| --- | --- | --- | --- | --- |
| exit_current | 11 | 54.55 | 12.78 | -44.87 |
| exit_immediate_trail | 11 | 36.36 | 5.69 | -22.75 |
| exit_trend_failure | 11 | 54.55 | 15.76 | -36.56 |

The trend-failure exit produced 49 rebalance days over the full sample (about 3.1 per year), versus 18 for the current rule. It improved historical CAGR from 22.57% to 28.40% and reduced maximum drawdown from -75.48% to -59.36%, but it is more reactive and must pass the same frozen validation process.

The immediate trailing exit reduced maximum drawdown to -48.63% but also reduced CAGR to 20.37% and required 46 rebalance days. It is a risk-control option, not the lead return candidate.

## Practical recommendation

Use a two-track shortlist. For the fewest decisions, advance entry-locked 60% sizing as the primary risk-reduction challenger and entry-locked 50% sizing as the more conservative challenger; both preserve the current 18 event days and make no daily adjustments. Separately, advance trend-failure exit as the return/risk challenger if roughly three rotation days per year is acceptable. Do not choose it from the full-sample result alone.

Avoid continuous daily volatility targeting for this use case. It had attractive historical statistics, but it requires hundreds of rebalance days and violates the operational constraint.

## Caveats

The backtest holds the signal and exit logic constant. Volatility is trailing 20-session realized TQQQ volatility, shifted so only information available before entry is used. A weight change is modeled as a buy/sell exposure adjustment and includes transaction costs, but actual order count, spreads, taxes, and partial-fill behavior still need paper records.