---
name: layered-regime-momentum
description: Multi-timeframe layered trading system built incrementally — Layer 1 (1h+30m HMA20-slope regime read, 5 states: NEUTRAL/EARLY_BULL/BULL/EARLY_SELL/SELL) is implemented; Layer 2 (context bias scoring), Layer 3 (regime-locked entry), and Layer 4 (risk management with split TP1/TP2) are planned. Standalone sibling to tf30m-hma-ema-momentum, not a replacement.
---

# Layered Regime Momentum

A 4-layer trading system being built one layer at a time. Each layer only
passes signal to the next once it agrees internally — the system is
deliberately conservative: it would rather sit out than trade against an
unclear regime.

```
Layer 1  Regime agreement       1h + 30m HMA20 slope -> 5 states (NEUTRAL/EARLY_*/BULL/SELL)
Layer 2  Context bias           1h + 15m dynamic scoring, confirms Layer 1
Layer 3  Directional entry      regime-locked (uptrend -> long only), structure/cross
Layer 4  Risk management        5% margin/trade, 2 positions max, 1:1.2 R:R, split TP
```

This is a **standalone skill**, independent of `tf30m-hma-ema-momentum` (no
shared code, no shared deployment) so the two strategies can be run and
compared side by side.

## Status

| Layer | Status | File |
|---|---|---|
| 1. Regime agreement | ✅ Implemented, tested | `scripts/layer1_regime.py` |
| 2. Context bias / dynamic scoring | ⏳ Not started | — |
| 3. Directional entry | ⏳ Not started | — |
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

## Layers 2–4 (planned)

Not yet implemented — will be built and documented here once each is
designed and tested, one at a time, per the project's own build order:

- **Layer 2 — Context bias**: takes Layer 1's regime and computes a dynamic
  score from 1h + 15m to confirm (or veto) it before Layer 3 acts.
- **Layer 3 — Directional entry**: trades *only* in the Layer 1/2 direction
  (an uptrend permits long entries only, never short); entry trigger via
  market structure and/or a fast/slow cross indicator.
- **Layer 4 — Risk management**: 5% of balance margin per position, max 2
  concurrent positions, no second position on a symbol already holding one,
  R:R 1:1.2 with stops at ATR(14)×1.5 (1R), split exit — 50% of size at TP1
  (0.5R), remaining 50% at TP2 (1.2R).

---

## Files

### Scripts
- `scripts/layer1_regime.py` — HMA20 indicator, per-timeframe regime
  classification, no-lookahead cross-timeframe alignment, the 5-state
  `classify_layer1` combination logic, and a CLI with `--demo` and
  `--csv-1h`/`--csv-30m`.

### Tests
- `tests/test_layer1_regime.py` (repo root) — warmup-neutral behavior, the
  no-lookahead alignment regression test, a full 3×3 table test of
  `classify_layer1` covering all nine (regime_30m, regime_1h) combinations,
  and an end-to-end confirmed-agreement check.

*This skill provides analytical tools and information only. It does not
constitute financial advice or trading recommendations.*
