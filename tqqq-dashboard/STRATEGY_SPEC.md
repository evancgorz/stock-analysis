# TQQQ / VOO Strategy Specification

Version: 1.0  
Account scope: the dedicated strategy account only

## Portfolio rule

The account is always invested in exactly one asset:

- `VOO` when the TQQQ regime is inactive, resetting, or exited.
- `TQQQ` when the buy regime is active.

The strategy never allocates to cash.

## Signal rule

The signal series is the S&P 500 total-return index (`^SP500TR`). The strategy calculates its rolling simple moving average and distance from that average.

- Enter TQQQ when the S&P 500 closes more than the upper band above its SMA.
- After an exit, remain in VOO until the S&P 500 closes below the lower reset band.
- The default parameters are a 200-day SMA, a +1% buy band, and a -1% reset band.
- Comparisons are strict (`>` for the buy/ATH tests and `<` for the reset test); equal values do not trigger an event.

## Exit rule

While holding TQQQ:

- A fresh S&P 500 all-time high activates the TQQQ trailing stop.
- The frozen baseline keeps the highest observed TQQQ close from entry, but only activates the stop after an S&P 500 ATH. The research suite separately tests resetting the peak when ATH activation occurs.
- A stop exit rotates the account to VOO and prevents re-entry until the reset rule is met.

## Execution model

Signals are generated after the market close. The resulting position is executed at the next trading day's open.

- The position held before the open receives that day's overnight gap.
- The new position receives that day's open-to-close return.
- The research baseline charges configurable transaction costs per sell/buy leg (the published run uses 5 bps per leg) and can stress 0/5/10/25 bps plus explicit slippage. Taxes remain account-specific and are not modeled. A close-confirmed trailing exit is not a guaranteed broker stop; the standing intraday stop-market variant is withheld until recorded intraday data is available.

Reset alternatives (trend recross and a fixed five-session cooldown) are research challengers only. They are not production parameters unless separately promoted through the same evidence gates.

## Research standard

Results should be judged against continuous VOO ownership using out-of-sample periods, parameter-stability analysis, full available TQQQ history, and realistic implementation assumptions.
