---
name: layered-regime-momentum
description: Multi-timeframe layered trading system built incrementally — Layer 1 (1h+30m HMA20-slope regime read, 5 states), Layer 2 (1h+15m dynamic bias scoring on ROC/RSI/ADX/Volume, stricter threshold for early vs confirmed regimes), and Layer 3 (regime-locked directional entry via 15m break-of-structure) are implemented; Layer 4 (risk management with split TP1/TP2) is planned. Standalone sibling to tf30m-hma-ema-momentum, not a replacement.
---

# Layered Regime Momentum

A 4-layer trading system being built one layer at a time. Each layer only
passes signal to the next once it agrees internally — the system is
deliberately conservative: it would rather sit out than trade against an
unclear regime.

```
Layer 1  Regime agreement       1h + 30m HMA20 slope -> 5 states (NEUTRAL/EARLY_*/BULL/SELL)
Layer 2  Context bias           1h + 15m dynamic scoring, confirms Layer 1
Layer 3  Directional entry      regime-locked (uptrend -> long only), break of structure
Layer 4  Risk management        5% margin/trade, 2 positions max, 1:1.2 R:R, split TP
```

This is a **standalone skill**, independent of `tf30m-hma-ema-momentum` (no
shared code, no shared deployment) so the two strategies can be run and
compared side by side.

## Status

| Layer | Status | File |
|---|---|---|
| 1. Regime agreement | ✅ Implemented, tested | `scripts/layer1_regime.py` |
| 2. Context bias / dynamic scoring | ✅ Implemented, tested | `scripts/layer2_bias.py` |
| 3. Directional entry | ✅ Implemented, tested | `scripts/layer3_entry.py` |
| 4. Risk management | ⏳ Not started | — |

---

## Layer 1 — 5-State Regime Read (1h + 30m)

**Rule**: compute HMA(20) on each timeframe's own closes. A timeframe's
regime is the *slope* of its HMA20 — rising = `UP`, falling = `DOWN`,
unchanged or still warming up = `NEUTRAL`. 30m is the **leading** timeframe
(it turns first); 1h is the **confirming** one. Combining both gives 5
mutually-exclusive, exhaustive states:

```
regime_30m   regime_1h          layer1_regime
UP           UP                 BULL         full agreement
UP           DOWN or NEUTRAL    EARLY_BULL   30m leads, 1h not yet confirming
DOWN         DOWN               SELL         full agreement
DOWN         UP or NEUTRAL      EARLY_SELL   30m leads, 1h not yet confirming
NEUTRAL      anything           NEUTRAL      30m itself undecided -- nothing to lead
```

`EARLY_BULL`/`EARLY_SELL` fire whenever 30m has a direction and 1h hasn't
matched it yet — whether 1h is merely undecided or **actively opposite**
(outright conflict counts as "early," not neutral; this was a deliberate
call, not an oversight — see the classification table test). Two derived
booleans make this easy to consume downstream:

- `layer1_directional` — `True` for any non-`NEUTRAL` state (there is *some*
  lean, even if not yet confirmed)
- `layer1_confirmed` — `True` only for full agreement (`BULL`/`SELL`)

A caller that only wants the strict old "both timeframes agree" signal uses
`layer1_confirmed`; one that wants to react to an emerging move immediately
(with presumably tighter risk) can act on `layer1_directional` instead and
size differently for `EARLY_*` vs. confirmed states in Layer 3/4.

### No-lookahead alignment

The 1h regime only updates once per hour; between updates it must be held
constant on the 30m grid using **only 1h bars that have already closed**.
`timestamp` throughout this module is a bar's *open* time (the ccxt/Binance
convention), so a bar is only actually closed at `open_time + interval` —
comparing raw open-time timestamps directly would leak a still-forming 1h
bar into the join one bar early. `align_htf_to_ltf()` converts both sides to
*close* time before the as-of join specifically to avoid that off-by-one; see
the regression test in `tests/test_layer1_regime.py` at the repo root, which
was written after this exact bug was caught during development (a first
version compared open-time timestamps directly and looked one bar ahead).

### Usage

```bash
uv pip install pandas numpy

# Synthetic demo
python scripts/layer1_regime.py --demo

# Your own data: two CSVs (open,high,low,close,volume,timestamp-ms), one per timeframe
python scripts/layer1_regime.py --csv-1h btc_1h.csv --csv-30m btc_30m.csv
```

Programmatic use:

```python
from layer1_regime import layer1_regime
result = layer1_regime(df_1h, df_30m)  # one row per 30m bar
# columns: timestamp, regime_30m, regime_1h,
#          layer1_regime (NEUTRAL/EARLY_BULL/BULL/EARLY_SELL/SELL),
#          layer1_directional, layer1_confirmed
latest = result.iloc[-1]
if latest.layer1_confirmed:
    print(f"Confirmed regime: {latest.layer1_regime}")   # BULL or SELL
elif latest.layer1_directional:
    print(f"Early regime: {latest.layer1_regime}")        # EARLY_BULL or EARLY_SELL
```

Real-data sanity check (BTC, 6 months, 1h native + 30m resampled from
complete 15m Binance data): `BULL` 32.3%, `SELL` 34.5%, `EARLY_BULL` 16.2%,
`EARLY_SELL` 16.6%, `NEUTRAL` 0.3% — 99.7% of bars carry *some* directional
lean, 66.8% are fully confirmed. Plausible and not degenerate: no single
state dominates, and the near-zero `NEUTRAL` share matches expectations,
since `NEUTRAL` only fires when the leading (30m) timeframe itself hasn't
picked a side yet — a narrow condition once past HMA warmup.

---

## Layer 2 — Context Bias (1h + 15m dynamic scoring)

**Rule**: reuses the same 4 confirmation indicators as `tf30m-hma-ema-momentum`
(ROC9, RSI14, ADX14, Volume vs SMA20), computed on **1h and 15m**, but scores
each one *continuously* (0-100, "how strongly does this support Layer 1's
direction") instead of counting binary pass/fail conditions:

| Indicator | Directional? | Score method |
|---|---|---|
| ROC9 | Yes | Rolling percentile rank (100 bars) of ROC9 for BULL, of `-ROC9` for SELL |
| RSI14 | Yes | RSI14 directly for BULL, `100 - RSI14` for SELL (already a natural 0-100 gauge) |
| ADX14 | No | Rolling percentile rank of ADX14 — trend *strength* has no direction of its own, so the same score applies to BULL or SELL |
| Volume | No | Rolling percentile rank of `volume / volume_sma20` — same reasoning as ADX |

A timeframe's score is the mean of its 4 components. Layer 2's combined score
is `0.5 × score_1h + 0.5 × score_15m` (equal weight by default — adjustable
via `weight_1h`).

**Percentile rank, not a fixed threshold**: momentum/trend-strength have no
fixed scale across assets or volatility regimes, so each is ranked against
its *own trailing 100-bar history* rather than compared to a hardcoded
number — literally the "dynamic" in dynamic scoring. One consequence worth
knowing: a smoothly, constantly compounding trend (the *same* % move every
bar) produces a *flat* ROC/ADX, which then ranks near the 50th percentile
against its own recent history — not near 100 — because percentile rank
measures "more extreme than recently," not "absolute level." It's
*acceleration/deceleration* that pushes a score toward the extremes, not
sustained-but-steady movement. (Caught by an initial version of the test
suite using a constant-rate trend that failed to score highly — fixed by
testing with a genuinely accelerating trend instead, which is also the more
realistic case for real market data.)

**Threshold depends on how confirmed Layer 1 already is:**

```
layer1_regime      Layer 2 pass condition
BULL / SELL         layer2_score >= 55  (CONFIRMED_THRESHOLD)
EARLY_BULL/SELL     layer2_score >= 70  (EARLY_THRESHOLD, stricter)
NEUTRAL             never passes -- no direction to score bias against
```

An early (unconfirmed) regime needs materially stronger bias evidence before
Layer 3 is allowed to act on it than an already-fully-agreeing one.

### Usage

```bash
python scripts/layer2_bias.py --demo
python scripts/layer2_bias.py --csv-1h btc_1h.csv --csv-30m btc_30m.csv --csv-15m btc_15m.csv
```

```python
from layer2_bias import layer2_bias
result = layer2_bias(df_1h, df_30m, df_15m)  # one row per 15m bar
# columns: timestamp, layer1_regime, bias_1h, bias_15m,
#          layer2_score, layer2_threshold, layer2_pass, layer2_direction
latest = result.iloc[-1]
if latest.layer2_pass:
    print(f"Layer 2 confirms {latest.layer2_direction} (score {latest.layer2_score:.1f})")
```

Real-data sanity check (BTC, 6 months): `EARLY_BULL` passes 0.9% of the time,
`EARLY_SELL` 1.1% (both near the strict 70 threshold, as intended), `BULL`
53.2%, `SELL` 59.6% (roughly half, at the looser 55 threshold) — the
threshold split by Layer 1 state is doing real work, not just decorative.

---

## Layer 3 — Directional Entry (structure break, 15m)

**Rule**: Layer 1 + Layer 2 together already say "trade this direction now,
or not at all" — Layer 3 never has to make its own direction call, only find
*where* to enter within whatever direction `layer2_pass` currently permits,
using **market structure** on the 15m grid (the same grid Layer 2 outputs on,
so no further cross-timeframe alignment is needed):

- **Swing detection**: a bar is a confirmed swing high once `swing_lookback`
  bars (default 3) have closed *after* it with none of them, nor the
  `swing_lookback` bars before it, showing a higher high. Swing lows mirror
  this. Confirmation is always `swing_lookback` bars late by construction —
  there's no way to know a bar was a local peak until enough subsequent price
  action has ruled out a higher one (same close-time discipline as Layer 1's
  alignment: nothing is used before it could actually be known).
- **Break of structure (BOS)**: a fresh close above the last *confirmed*
  swing high fires a long trigger; a fresh close below the last confirmed
  swing low fires a short trigger. Each break is a **one-shot signal** — once
  consumed, that level won't refire on later bars that also close above it;
  a new swing point has to form first.
- **Regime lock**: `LONG` only fires when `layer2_direction == "BULL"` **and**
  `layer2_pass` **and** a fresh `bos_up` land on the same bar; `SHORT`
  mirrors this for `SELL`/`bos_down`. Going long during a permitted downtrend
  (or short during a permitted uptrend) is **structurally impossible**, not
  just discouraged — there is no code path that produces it (verified by
  test and by scanning the full real-BTC-data run below for exactly zero
  such cases).

### Usage

```bash
python scripts/layer3_entry.py --demo
python scripts/layer3_entry.py --csv-1h btc_1h.csv --csv-30m btc_30m.csv --csv-15m btc_15m.csv
```

```python
from layer3_entry import layer3_entry
result = layer3_entry(df_1h, df_30m, df_15m)  # one row per 15m bar
# columns: everything from layer2_bias, plus last_swing_high, last_swing_low,
#          bos_up, bos_down, layer3_entry ('LONG'/'SHORT'/None)
latest = result.iloc[-1]
if latest.layer3_entry:
    print(f"{latest.layer3_entry} entry signal at {latest.timestamp}")
```

Real-data check (BTC, 6 months, 15m): 186 LONG + 221 SHORT signals over
17,376 bars (roughly 2 signals/day) — a scan of every signal confirms zero
cross-contamination (no LONG while `layer2_direction == "SELL"` or vice
versa), matching the "structurally impossible" design goal exactly.

---

## Layer 4 (planned)

- **Risk management**: 5% of balance margin per position, max 2 concurrent
  positions, no second position on a symbol already holding one, R:R 1:1.2
  with stops at ATR(14)×1.5 (1R), split exit — 50% of size at TP1 (0.5R),
  remaining 50% at TP2 (1.2R).

---

## Files

### Scripts
- `scripts/layer1_regime.py` — HMA20 indicator, per-timeframe regime
  classification, no-lookahead cross-timeframe alignment, the 5-state
  `classify_layer1` combination logic, and a CLI with `--demo` and
  `--csv-1h`/`--csv-30m`.
- `scripts/layer2_bias.py` — ROC9/RSI14/ADX14/Volume indicators, rolling
  percentile-rank normalization, directional (BULL/SELL-aware) scoring per
  timeframe, combined 1h+15m dynamic score, and the Layer-1-state-dependent
  pass threshold. Imports `layer1_regime.py` (sibling script) for the Layer 1
  read and its no-lookahead alignment helper. CLI with `--demo` and
  `--csv-1h`/`--csv-30m`/`--csv-15m`.
- `scripts/layer3_entry.py` — fractal swing-high/low detection, one-shot
  break-of-structure triggers, and the regime lock that makes LONG
  structurally impossible during a permitted downtrend (and vice versa).
  Imports `layer2_bias.py` (sibling script). CLI with `--demo` and
  `--csv-1h`/`--csv-30m`/`--csv-15m`.

### Tests
- `tests/test_layer1_regime.py` (repo root) — warmup-neutral behavior, the
  no-lookahead alignment regression test, a full 3×3 table test of
  `classify_layer1` covering all nine (regime_30m, regime_1h) combinations,
  and an end-to-end confirmed-agreement check.
- `tests/test_layer2_bias.py` (repo root) — percentile-rank sanity checks,
  the BULL/SELL mirroring test for directional scoring, the
  confirmed-vs-early threshold split, a NEUTRAL-never-passes check, and an
  end-to-end accelerating-uptrend check.
- `tests/test_layer3_entry.py` (repo root) — swing-confirmation timing
  (a swing high must not appear before enough future bars exist to confirm
  it), the one-shot break-of-structure property, the regime lock (LONG only
  with BULL direction + layer2_pass, and vice versa), and a check that a
  break with the wrong bias strength produces no entry.

*This skill provides analytical tools and information only. It does not
constitute financial advice or trading recommendations.*
