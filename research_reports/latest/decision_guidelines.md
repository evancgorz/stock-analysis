# TQQQ / VOO operating guidelines — research draft

These guidelines describe the frozen baseline used in the modeling run dated 2026-09-08T17:31:54.170872+00:00. They are not a broker order instruction until the practical execution and prospective paper gates are satisfied.

1. After a completed S&P 500 total-return session, calculate the 200-session SMA and distance from it.
2. A close above the +1% entry band creates a confirmed TQQQ target. A close below the -1% reset band re-arms a new entry only after an exit.
3. When no TQQQ target is active, the dedicated account remains in VOO.
4. A fresh signal is queued for the next_open scenario. The model treats the next available trading session as the earliest fill and keeps signal time, order time, and fill time separate.
5. Once the S&P 500 makes a new all-time high during a TQQQ episode, the baseline activates a 10% close-based trailing exit. The frozen baseline measures the threshold from the highest TQQQ close since entry; the research suite separately tests a peak reset at ATH activation.
6. On a confirmed exit, rotate to VOO and wait for the reset rule before re-arming.
7. If the expected morning fill is missed, use the pretested delayed scenario and recheck the target using only information then available. Record the actual time and price.
8. Every decision record must include the data session, strategy version, action, target, threshold, pending order, expected execution window, and actual fill if completed.

The live workflow still requires a freshness check, an order/fill journal, observed slippage calibration, and prospective paper observations.
