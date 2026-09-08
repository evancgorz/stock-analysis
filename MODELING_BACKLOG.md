# TQQQ / VOO modeling and decision backlog

Status: proposed research protocol; no strategy has passed validation under this protocol.
Scope: dedicated strategy accounts. VOO is the resting allocation; TQQQ is the tactical allocation. The wider portfolio is outside scope. Preserve the existing full-account rotation as the baseline; test smaller tactical allocations only as explicitly labeled research alternatives.

## Objective and decision standard

Determine whether switching from VOO to TQQQ adds worthwhile returns during the actual risk-on holding intervals, and which simple rules make that decision repeatable under manual execution. Favor understandable rules, stable results, and tolerance of execution delays over the highest historical return. Interest in TQQQ does not establish a numerical acceptable loss limit.

Every proposed rule must have a hypothesis, a comparison with the baseline changing one feature at a time, results after costs and delays, uncertainty estimates, and an adopt / reject / inconclusive decision. Maintain an experiment register including unsuccessful trials. Freeze candidate definitions before evaluating them. No automatic production parameter changes based on a leaderboard.

## P0 — Repair the evidence foundation

- [ ] M01: Audit and reconcile existing results before drawing conclusions.
  - In `robustness_view.evaluate_combination`, slicing the frame does not rebase equity: ending equity divided by initial capital includes warm-up gains. Recompute evaluation-period wealth from evaluation-period returns with a clearly defined starting timestamp, including the first return consistently.
  - Reconstruct SMA, historical highs, reset state, holdings, and trailing peaks from all prior available history. A short SMA warm-up is insufficient to reconstruct a stateful trading strategy. Score only the evaluation window.
  - The existing 70/30 procedure is a single historical holdout, not repeated walk-forward validation. Previously inspected dates are no longer a pristine holdout.
  - Current first-row strategy returns include intraday performance while VOO benchmark starts at zero. Align both investments to the same starting instant and capital.
  - Fix duplicate entries and carried-in positions in trade extraction; separate closed trades from open mark-to-market observations. Never invent an entry price at a fold boundary.
  - Reconcile documentation with code: current code tracks the TQQQ peak from the buy signal, while the specification says after ATH activation. Establish actual-fill-based peaks and compare both post-entry and post-activation alternatives explicitly.
  - Verify current-day incomplete bars cannot generate confirmed signals. Historical window highs must not be called all-time highs without sufficient prior index history.
  - Acceptance: hand-calculated fixtures reconcile holdings, dividends, costs, equity, fills, and matched VOO returns; prefix-invariance tests show future observations cannot change earlier decisions. Reissue the previous return/drawdown claims as corrected or withdrawn with a reconciliation table.

- [ ] M02: Freeze a reproducible baseline and dataset.
  - Record SMA 200, +1% buy band, -1% reset band, total-return S&P signal, ATH-activated 10% close-based trailing exit, VOO resting allocation, and next-session open execution as the initial research baseline.
  - Specify strict versus inclusive comparisons, initial armed state, buy-above-level versus fresh crossing, same-day event precedence, ATH on entry day, reset after exit, missing sessions, and pending orders. An inactive pre-ATH stop means no such exit protection; report that exposure explicitly.
  - Store immutable OHLC/dividend/split snapshots, provider, retrieval time, exchange timezone/calendar, coverage, gaps, adjustment conventions, hashes, code revision, config, seeds, and run identifier.
  - Obtain index history before ETF inception for indicators. Primary investable history starts at verified common fund availability (currently September 2010 in the feed); explain coverage lost to unavailable instruments.
  - Use raw tradable prices with corporate-action accounting or a demonstrably consistent adjusted OHLC model. Reconcile split/dividend dates. Fund expenses embedded in historical fund returns must not be deducted twice.
  - Acceptance: an offline rerun reproduces results and all candidates share identical evaluation dates and benchmark conventions.

## P1 — Model how execution actually happens

- [ ] M03: Build one event-driven simulator shared by all research pages.
  - Distinguish signal time, confirmation/data-availability time, notification time, user action time, order submission, and fill time. A confirmed closing signal cannot receive an earlier fill.
  - At a rotation, retain the old asset's performance until its sale; charge each sell and buy leg separately and record any brief operational gap. No strategic cash allocation is introduced.
  - Track pending orders, missed/partial fills, cancellations, stale alerts, fractional versus whole shares, residual cash, and signals that reverse before a delayed order executes. Specify revalidation using only information available then.
  - Acceptance: ledger reconciles exactly with equity and the paired benchmark under nonzero entry and exit gaps, costs, splits, delayed fills, and missing data.

- [ ] M04: Run the execution scenario matrix for every serious candidate.

  | Scenario | Confirmation and execution | Purpose |
  | --- | --- | --- |
  | Reference | Completed session close; following session official open | Reproducible baseline; assumes an order can reach the opening auction |
  | Practical morning | Same confirmation; next session 09:35 and 10:00 America/New_York | Manual reaction after opening |
  | Late morning | Same confirmation; next session 11:00 | Conservative morning delay |
  | Missed morning | Next session close | Operational stress |
  | Missed session | Second following session open | Exceptional delay stress |
  | Mixed behavior | Most fills next morning, occasional late/missed fills; fixed seeded scenarios | Sensitivity to imperfect adherence |

  - Apply delays independently to buys and sells and jointly. Report the incremental damage from exit delay, especially near a trailing exit.
  - Use the exchange calendar for weekends, holidays, early closes, and daylight-saving transitions. Next morning means next trading session.
  - Actual intraday bars/quotes are required to estimate morning fills. Use the first available bar after submission with a stated spread/slippage convention; never infer 10:00 prices from daily OHLC. Where intraday history is unavailable, report daily-open/close bounds and a separate shorter-period intraday study.
  - Explore 0, 5, 10, and 25 basis points per traded leg as scenario assumptions, not measured execution costs. Calibrate later using actual account fills. Include commissions separately and disclose auction/market-order versus limit-order assumptions; limits may not fill.
  - Acceptance: candidate-by-delay tables show paired VOO advantage, drawdown, worst trade, lost edge, and break-even cost. A strategy dependent on an immediate ideal fill does not qualify for the manual workflow.

- [ ] M05: Separate exit signals from broker stop orders.
  - Baseline: a close below the active trailing threshold creates a next-session exit. A 10% threshold is not a guaranteed 10% loss cap.
  - Compare standing intraday stop-market execution as a separate variant. A gap below the stop fills at the available market price with slippage; a stop-limit can remain unfilled.
  - With daily bars, do not assume favorable ordering of high/low or same-bar peak update and stop touch. Use intraday evidence or conservative path bounds.
  - Acceptance: attribute losses to pre-activation exposure, threshold movement, close confirmation, overnight gaps, and reaction delay separately.

## P2 — Make risk-on VOO comparison the primary report

- [ ] M06: Build the paired opportunity ledger.
  - For each actual TQQQ entry fill through actual exit fill, compare equal starting dollars in TQQQ versus retaining VOO for exactly the same timestamps, including distributions and relevant transaction costs.
  - Report entry/exit signals and fills, duration, TQQQ net return, VOO total return, percentage-point difference, relative wealth `(1 + TQQQ return) / (1 + VOO return) - 1`, incremental dollars, adverse/favorable excursion, and drawdown for each path.
  - VOO retention has no hypothetical sale/rebuy costs. Charge the strategy both rotation legs. Attribute VOO-sale and TQQQ-purchase costs to entry and the reverse costs to exit.
  - Open episodes appear separately with a common mark timestamp; report closed-only win/expectancy statistics. Boundary-spanning trades retain true origin and show separate window performance.
  - Aggregate median/mean excess, fraction beating VOO, worst excess, paired downside, holding duration, compounded relative wealth across nonoverlapping episodes, and the contribution of the best one/two episodes. Do not add percentage-point returns as if they compounded.
  - Acceptance: a reader can answer whether each decision to leave VOO paid off, how much extra downside it incurred, and whether the benefit survives a late fill.

- [ ] M07: Add account-level and regime diagnostics as secondary evidence.
  - Full VOO/TQQQ account versus continuous VOO: CAGR, drawdown, recovery duration, volatility, turnover, time in TQQQ, and return after costs. Both accounts remain invested outside tactical intervals.
  - Report rolling 1/3/5-year comparisons, calendar periods, worst starts, and named stress episodes within actual coverage. Keep historical episode labels descriptive rather than selecting rules from their outcomes.
  - Attribute excess to exposure, entry timing, exit timing, costs, and delay; include QQQ during matched periods to assess whether extra leverage added value.
  - If using Sharpe/Sortino/Calmar, disclose annualization, risk-free/minimum acceptable return conventions, and undefined cases. Pair them with drawdown and sample size.
  - Acceptance: primary risk-on findings and secondary account findings are consistent and explain any divergence.

## P3 — Small, hypothesis-driven experiments

- [ ] M08: Establish which baseline decisions earn their complexity.

  | Decision | Coarse alternatives | Evidence sought |
  | --- | --- | --- |
  | Trend horizon | SMA 150 / 200 / 250 | Broad stability, rather than a single optimum |
  | Entry buffer | 0 / 1 / 2%; optional two completed closes | Noise reduction versus delayed entry |
  | Reset | Existing -1% reset; trend recross; fixed short cooldown | Avoid churn without missing durable trends |
  | Exit protection | ATH sale; immediate 10% trail; ATH-activated 10% trail; trend failure | Whether waiting for ATH creates avoidable losses |
  | Trail width | 8 / 10 / 15% near a shortlisted exit | Sensitivity and tolerable implementation delay |
  | Signal market | S&P price / total return; QQQ trend | Whether the signal matches the traded exposure |

  - Begin with one change at a time; combine only a small number with clear independent rationale. Do not run the full Cartesian product.
  - Reconstruct the historically worst losses to identify which proposed exit would actually have been available at that time.
  - Acceptance: each rule gets a short decision memo with mechanisms, paired comparisons, nearby settings, delay sensitivity, costs, and limitations.

- [ ] M09: Bounded exploration of related strategies.
  - QQQ or a 2x Nasdaq fund in the same risk-on windows: test how much benefit depends on 3x exposure, using real fund coverage and clearly labeled alternatives.
  - 50% TQQQ / 50% VOO during risk-on, all VOO otherwise: measure whether lower exposure preserves useful edge. State whether weights drift or rebalance and charge rebalancing costs.
  - Weekly confirmed trend signals: test whether lower attention requirements and fewer false signals compensate for slower exits.
  - Prior-data volatility filter or capped volatility-based TQQQ sizing, remainder VOO: test risk reduction with a fixed simple rule and no future volatility input.
  - Trend-confirmed pullback entry: one predetermined pullback/recovery rule to test opportunity cost versus chasing an extended move.
  - Limit the first exploration round to these five families. Register every trial and stop expanding when findings cannot be distinguished with the available number of independent episodes.
  - Acceptance: retain at most two understandable challengers for validation; inconclusive candidates stay research-only.

## P4 — Validate robustness and uncertainty

- [ ] M10: Replace the single split with chronological validation.
  - First evaluate the unchanged baseline across full history and multiple predetermined windows without optimizing it.
  - Use expanding training windows (initial five years) and subsequent one-year tests, with a two-year test sensitivity because trades are sparse. Select only on earlier data and stitch disjoint test returns once.
  - For candidates fixed before evaluation, reconstruct continuous historical state. For an adaptive policy, separately specify fold transitions, actual inherited holdings, and costs when parameters change; never substitute an imaginary candidate holding at the boundary.
  - Use common warm-up and evaluation dates for comparisons; exclude incomplete current sessions. Prevent train/test label leakage from trades crossing the boundary.
  - Mark all already explored historical data as retrospective. Reserve future paper observations for genuinely prospective validation; record each time a holdout is inspected.
  - Acceptance: report every fold, including failures and folds with no trades, plus aggregate stitched results and total independent episodes.

- [ ] M11: Quantify fragility without manufacturing confidence.
  - Use paired episode resampling and paired block resampling of synchronized returns where appropriate; preserve TQQQ/VOO dependence and disclose block-length sensitivity. Resampled realized trades measure outcome uncertainty, not new trigger behavior.
  - Keep full strategy replay on historical paths separate from statistical resampling. Any synthetic pre-inception daily-leverage proxy must model daily reset, financing, expenses, and path effects and be calibrated against overlap; label it stress evidence, never actual TQQQ history.
  - Test removing the largest winner, modest parameter perturbations, delayed alerts, and increased costs. Evaluate nearby settings on development data before final validation.
  - Account for the number of tried alternatives and correlated candidates. Ten related winners are not ten independent confirmations.
  - Acceptance: provide interval estimates with method/sample caveats, concentration analysis, and an explicit insufficient-evidence outcome when trades are too few.

- [ ] M12: Produce an evidence scorecard and promotion decision.
  - Score separately: accounting correctness, paired VOO benefit, cross-period consistency, drawdown/recovery, parameter stability, and practical execution tolerance. Avoid a single opaque confidence percentage.
  - Before promotion, establish acceptable dedicated-account drawdown, maximum underperformance versus VOO, and operational effort with the user using the completed tradeoff report. These limits are not yet known.
  - A candidate must have reconciled accounting, positive net paired evidence across multiple periods, no dominant dependence on one episode, useful performance under next-morning delay, and loss behavior within the agreed limits. Failure or inadequate evidence prevents promotion.
  - Acceptance: baseline and at most two challengers receive adopt / reject / inconclusive decisions with explicit reasons; simpler rules win unresolved ties.

## P5 — Translate evidence into a practical operating guide

- [ ] M13: Design the daily decision and execution workflow.
  - After the exchange close and provider completion check, compute and persist a timestamped confirmed signal. Tentative intraday readings must be visibly distinct.
  - Alert on a required change, include strategy version, as-of session, actual/model position distinction, action, reason, next-session execution window, active threshold, and signal expiry/recheck instruction.
  - Check data freshness and pending orders the following morning; apply the pretested late-fill/reversal policy if the user missed the expected window. Record actual acknowledgment and fill time/price.
  - Keep the research threshold and actual broker-order status distinct. Broker settlement, buying-power, order-type availability, and account-specific tax treatment must be confirmed before account automation.
  - Model taxable and tax-deferred scenarios separately if relevant; tax assumptions remain configurable until account facts are known. Do not assume gains, losses, or sale proceeds can be treated identically across accounts.
  - Acceptance: replay complete example weeks including a Friday signal, holiday, stale feed, delayed buy, and gap-through exit; every displayed action follows the modeled rules.

- [ ] M14: Paper validation and final research package.
  - Persist generated recommendations and human fills separately. Compare observed latency/slippage against tested scenarios and recalibrate assumptions transparently.
  - Use a multi-month operational observation window plus historical replay of rare entry/exit events. A quiet paper period is an operational check, not proof of performance.
  - Deliver reproducible run configs, immutable data manifest, trade/fill and paired-VOO ledgers, fold results, delay/cost matrices, parameter stability plots, rejected-trial register, decision memos, and a concise final guideline sheet.
  - Acceptance: another run reproduces all published tables; the guideline sheet states exactly when to enter, hold, exit, reset, and recheck a delayed signal, with the supporting evidence for each rule.

## Delivery sequence and completion gates

1. M01–M02: corrected baseline and reproducible data. Withdraw unreliable earlier metrics until reconciled.
2. M03–M07: realistic execution and matched risk-on VOO scorecard. This is the first substantive modeling report.
3. M08–M09: bounded experiments and documented rule choices.
4. M10–M12: chronological validation, uncertainty, and concrete candidate tradeoffs.
5. M13–M14: practical guide and paper evidence before any production promotion.

This backlog is complete when all items have evidence-backed outcomes, including explicit rejection or inconclusive findings. Coding a report page or obtaining a high backtest return alone does not complete a modeling milestone. This document authorizes planning; implementation and experiment results must be recorded as separate work products.
