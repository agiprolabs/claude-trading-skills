---
name: prediction-market-live-ops
description: Use when building, backtesting, operating, or scaling automated trading on prediction markets (Kalshi or similar) — evidence-gated methodology, live-execution safety rails, and falsification protocols distilled from a real live-money campaign
---

# Prediction-Market Trading Doctrine

Hard-won operational knowledge from a live Kalshi campaign (Aug–Sep 2026:
crypto/commodity maker ladders, regime tilts, tennis dust vacuum — all
falsified honestly, infrastructure open-sourced). Reference implementation: https://github.com/agiprolabs/kalshi-stack.
Complements `prediction-market-strategy` (edge selection/sizing) — this skill
covers the OPERATIONAL side: validating, executing, and killing strategies
against a live venue without losing more than the lesson costs.

## The prime directive

Every strategy decision is evidence-gated: backtest → paper → live micro-probe
→ ratchet. Each stage has a PRE-DECLARED kill condition with correctly
calibrated probability math, written down BEFORE the data arrives. When a
threshold turns out miscalibrated, correct it openly and re-declare — never
silently move a goalpost in either direction.

## Backtest hygiene (each rule was violated once, expensively)

- **Print-replay EV of passive-fill strategies is an UPPER BOUND, never an
  estimate.** The prints a resting order actually captures are an
  adversely-selected sample of the tape (sweeps deep enough to reach your
  queue skew toward true collapses). A tennis dust book that measured +125%/$
  on prints went 0-for-78 live (P<2%). Only fill-conditioned live outcomes
  validate a maker strategy.
- **Time-series joins use the last bar ending ≤ the decision instant.**
  A candle containing the instant is look-ahead and will fabricate
  covariates that vanish out-of-sample.
- **Taker backtests need print-confirmed executability**, not quoted-ask
  edges — stale quotes create phantom fills.
- **Any bucketed-PnL review includes a top-N-share column.** Lottery-payoff
  books concentrate EV; a "pattern" that is two elephant rounds is noise.
  Same rule when a holdout "wins": check concentration before believing it.
- **Early settlements are selection-biased toward losers** (collapses end
  fast; comebacks are long matches/rounds). Never read a verdict off the
  fast-settling prefix.
- **Static tilts that flip sign between tape halves are regime bets, not
  edges.** A conditioning scheme must beat baseline on BOTH halves and on
  each individual day; pre-register the rules, no per-day fitting.
- Mirror/complement markets are the SAME bet — deduplicate before computing
  independence-based probabilities.

## Live execution rules (the incident ledger)

- **Smoke-test every live order path with a real 1-lot round trip** (place,
  verify resting, cancel, verify gone) before any strategy trades through
  it. Paper cannot exercise venue routing parameters. Cost: $0.01.
- **Cancels must be truthful**: distinguish cancelled / already-gone
  (filled!) / failed. A 404 is not a cancel — it means wrong routing shard
  or a fill-race. Swallowed cancel failures + re-anchor loops = runaway
  position stacking (cost us $84 in one evening).
- **Route the exchange shard (`exchange_index`) consistently on EVERY call**
  — placement, reads, cancels, collateral. Collateral must be pre-positioned
  on the shard before orders.
- **Measure rate limits empirically with dust orders** (burst ladder +
  sustained test). Advertised budgets can be 10× off effective per-order
  cost. Pace bursts to the measured rate with retry-requeue on 429.
- **post_only for any maker strategy** — an "aggressive maker" price on a
  market trading inside your band silently becomes a taker fill of a
  different (unvalidated) trade. Tag and cohort maker vs taker fills
  separately in all realized-EV accounting.
- **Rails, always**: halt-file checked before every order batch (cancel-all
  on appearance), independent scheduler-driven drawdown breaker with
  deposit-jump detection, per-order and per-market size caps with anomaly
  ledger events, equity floor stand-down. The breaker baseline is set at
  session start per the operator's stated loss tolerance.
- **Queue priority is the product** in penny/maker books. Synchronized-open
  venues: NTP + fire at boundary+0 with a retry probe (measure the venue's
  open-transition latency). Event-driven venues: push-based discovery
  (lifecycle WebSocket channels) beats polling; a fresh market's book is
  empty, so first-to-rest owns the level for its lifetime.
- **Restart daemons at activity boundaries**; mid-round restarts orphan
  in-memory state (untracked orders, missed settlements).
- **Geofencing is real**: order-origin IP matters, categories differ
  (sports/elections vs financials), and enforcement can change overnight.
  Datacenter location is part of your compliance posture.

## Scaling doctrine

- **House-money ratchet**: double size only when realized profit at the
  current step covers the next step's incremental risk AND round-count and
  EV-continuity gates pass. Drop back a step on trailing degradation.
- **Measure the capacity curve** (EV/$ by per-print cap) before believing
  any scale projection; then the binding constraint is capture rate ×
  measured pool, and capture rate is only measurable live.
- **Fill quality is the untested link at every new size** — the paper/live
  EV-per-$ ratio at each step gates the next.

## Experiment operations

- Cohort every fill (maker/taker, band, source) at write time — post-hoc
  attribution is what lets a bug contaminate a verdict.
- Ship one variable at a time; changing size and placement logic in the same
  window destroys attribution.
- Run A/B variants in paper against a frozen baseline (small-footprint
  variant, shared rounds, EV/premium-$ as the scale-free judge).
- Log everything to append-only ledgers; reconcile realized PnL to the
  venue's own fills/settlements, never to internal marks.
- Post results (wins AND falsifications) to the operator's channel; write a
  decision record with evidence and reversal conditions for every ship,
  retire, and kill.
