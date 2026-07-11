---
name: layered-regime-momentum
description: Multi-timeframe layered trading system built incrementally — Layer 1 (1h+30m regime agreement) is implemented; Layer 2 (context bias scoring), Layer 3 (regime-locked entry), and Layer 4 (risk management with split TP1/TP2) are planned. Standalone sibling to tf30m-hma-ema-momentum, not a replacement.
---

# Layered Regime Momentum

A 4-layer trading system being built one layer at a time. Each layer only
passes signal to the next once it agrees internally — the system is
deliberately conservative: it would rather sit out than trade against an
unclear regime.

```
Layer 1  Regime agreement       1h + 30m HMA20 slope, both must agree
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

## Layer 1 — Regime Agreement (1h + 30m)

**Rule**: compute HMA(20) on each timeframe's own closes. A timeframe's
regime is the *slope* of its HMA20 — rising = `UP`, falling = `DOWN`,
unchanged or still warming up = `NEUTRAL`. Layer 1 passes only when both
timeframes agree on a non-neutral direction:

```
1h == UP   AND 30m == UP    -> PASS, regime = UP
1h == DOWN AND 30m == DOWN  -> PASS, regime = DOWN
anything else                -> NO PASS, regime = NEUTRAL
```

When regimes disagree (one leads, one hasn't caught up yet, which is normal —
the 30m HMA reacts faster than the 1h one) or either side is still in warmup,
Layer 1 blocks — there is deliberately no trading signal without agreement.

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
# columns: timestamp, regime_30m, regime_1h, layer1_regime, layer1_pass
latest = result.iloc[-1]
if latest.layer1_pass:
    print(f"Regime: {latest.layer1_regime}")  # feed into Layer 2
```

Real-data sanity check (BTC, 6 months, 30m resampled from 15m Binance data):
regime distribution UP 32.3% / DOWN 34.5% / NEUTRAL 33.2%, Layer 1 pass rate
66.8% — plausible and not degenerate (no timeframe permanently dominates,
and the NEUTRAL/no-pass share is meaningful rather than near-zero, consistent
with two independent timeframes genuinely having to agree).

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
  classification, no-lookahead cross-timeframe alignment, Layer 1 pass logic,
  CLI with `--demo` and `--csv-1h`/`--csv-30m`.

### Tests
- `tests/test_layer1_regime.py` (repo root) — warmup-neutral behavior, the
  no-lookahead alignment regression test, and an end-to-end pass-agreement
  check.

*This skill provides analytical tools and information only. It does not
constitute financial advice or trading recommendations.*
