---
name: tf30m-hma-ema-momentum
description: 30-minute HMA20 gate + EMA5/EMA9 cross momentum strategy with a 4-part confirmation score (ROC, RSI, ADX, Volume), ATR stop/take-profit at 1:1 R:R, and direction-signal early exits. Includes a full state-machine engine and backtester.
---

# TF30M HMA20-EMA Cross Momentum

A rules-based trend-momentum strategy for the 30-minute timeframe. It only
takes a trade when three independent filters agree: a **Direction Gate**
(HMA20) that decides whether longs or shorts are even allowed, an **Entry
Trigger** (EMA5 crossing EMA9) that marks the setup, and a **Confirmation
Score** (ROC, RSI, ADX, Volume) that must pass at least 3 of 4 within a
3-bar window. Exits are deliberately fast: a fixed ATR stop / take-profit
(1:1) plus a direction-signal early exit.

The design separates indicators by role. HMA, EMA, and ROC are *direction*
indicators used for both entry and exit. RSI is *momentum confirmation* for
entry only. ADX and Volume are *quality* filters for entry only — they never
close a position, because a falling ADX or thinning volume signals a pause,
not a reversal.

```
Entry = Direction Gate AND Entry Trigger AND (Confirmation Score >= 3/4)
Exit  = HMA reverse  OR  EMA reverse  OR  ROC reverse   (any one)
```

## When It Works / When It Fails

- **Works**: sustained 30m directional moves with participation — the gate
  aligns with an EMA cross and momentum/volume confirm.
- **Fails**: chop. Repeated EMA crosses near a flat HMA generate setups that
  the confirmation window rejects, or entries that the fast signal exit
  stops out. Expect a high share of small SIGNAL exits in ranging regimes.

Pair this with the `regime-detection` skill and only run it when the 30m
regime is trending.

---

## 1. Parameters

| Component | Setting |
|-----------|---------|
| Timeframe | 30 minutes (evaluate on bar close) |
| Direction Gate | HMA(20) |
| Entry Trigger | EMA(5) cross EMA(9) |
| Momentum | ROC(9) |
| Confirmation | RSI(14), ADX(14), Volume SMA(20) |
| Volatility | ATR(14) |
| Stop Loss | entry ∓ ATR(14) × 1.5 |
| Take Profit | entry ± ATR(14) × 1.5 (R:R 1:1) |
| Position margin | 5% of current balance |
| Max positions | 1 per symbol |

---

## 2. Direction Gate (HMA20)

The gate is checked on the bar where the EMA cross occurs, using that bar's
**open** relative to HMA20, plus an HMA-slope guard.

```python
long_gate  = open > hma20 and hma20 >= hma20_prev   # HMA not sloping down
short_gate = open < hma20 and hma20 <= hma20_prev   # HMA not sloping up
```

If the gate fails, no confirmation window opens — an EMA cross alone is not
enough.

## 3. Entry Trigger (EMA5 / EMA9)

A trigger fires when EMA5 crosses EMA9 **on the same bar the gate passes**.
That bar starts a 3-bar Confirmation Window. Throughout the window EMA5 must
stay on the correct side of EMA9 and each bar's open must stay on the correct
side of HMA20.

## 4. Confirmation Score (3 of 4)

Each condition is worth 1 point. Need **≥ 3**.

| # | Condition | Long | Short |
|---|-----------|------|-------|
| 1 | ROC momentum | `roc9 > 0` | `roc9 < 0` |
| 2 | RSI direction | `rsi14 > 50` | `rsi14 < 50` |
| 3 | Trend strength | `adx14 >= 18 and adx14 > adx14_prev` | same |
| 4 | Volume | `volume >= volume_sma20` | same |

The score is evaluated each bar of the window. The trade opens on the first
bar that reaches 3/4 (entry price = that bar's close). If the window closes
(bar 3) still below 3, or any structural condition breaks, the setup fails
and the system waits for a **fresh** EMA cross under a passing gate.

## 5. Entry, Stop, Target

```python
entry_price = close                      # of the confirming bar
sl_distance = atr14 * 1.5
long_sl,  long_tp  = entry - sl_distance, entry + sl_distance
short_sl, short_tp = entry + sl_distance, entry - sl_distance
margin = balance * 0.05
```

An **Entry Snapshot** (direction, price, ATR, every indicator value, the
score, and which components passed) is stored for journaling and backtest
analysis. The snapshot is *record-only* — it does not create an exit rule
that all entry indicators must flip.

## 6. Exits

The exchange SL/TP is always live. On each bar close, if neither was hit, a
**direction-signal early exit** is evaluated:

```python
long_exit  = close < hma20 or ema_cross_down or roc9 < 0
short_exit = close > hma20 or ema_cross_up   or roc9 > 0
```

Any single condition closes 100% at market. ADX, Volume, and RSI are **never**
standalone exits in this version. Priority order: emergency risk → SL → TP →
signal exit → monitoring. If SL/TP already executed, no duplicate signal exit
is sent.

**No immediate reversal**: closing a long on a reverse signal cannot open a
short on the same bar (and vice-versa). The system returns to WAITING and
requires a new cross under a fresh gate.

---

## State Machine

```
WAITING
  → gate passes AND EMA cross           → LONG/SHORT_CONFIRMATION (bar 1..3)
  → score >= 3 within window            → LONG/SHORT_POSITION
  → SL / TP / signal exit               → RESET → WAITING
```

Bar-processing order (exactly as implemented in the engine): manage open
position first (intrabar SL/TP, then bar-close signal exit) → if a position
exists or a reversal was just blocked, stop → else start a new setup or
advance the active confirmation window.

See `references/strategy_spec.md` for the complete rule set, failure
conditions, and annotated pseudocode.

---

## Files

### Scripts
- `scripts/tf30m_hma_ema_strategy.py` — indicators (HMA, EMA, ROC, RSI, ADX,
  ATR, volume SMA), the `StrategyEngine` state machine, a bar-by-bar
  backtester, and a CLI. Run `--demo` for synthetic data or `--csv` for your
  own 30m OHLCV.

### References
- `references/strategy_spec.md` — full specification: gates, triggers,
  confirmation scoring, entry/exit logic, setup-failure rules, indicator
  classification, entry snapshot, and state-machine pseudocode.

---

## Quick Start

```bash
uv pip install pandas numpy

# Synthetic demo (mechanics + summary stats)
python scripts/tf30m_hma_ema_strategy.py --demo

# Your own 30m candles: CSV with open,high,low,close,volume (ascending time)
python scripts/tf30m_hma_ema_strategy.py --csv candles_30m.csv --balance 10000
```

Programmatic use:

```python
from tf30m_hma_ema_strategy import run_backtest, summarize
engine, indicators = run_backtest(df, balance=10_000)
print(summarize(engine, 10_000))
for trade in engine.trades:
    print(trade.direction, trade.reason, trade.pnl_pct, trade.snapshot)
```

## Integration with Other Skills

| Skill | Integration |
|-------|------------|
| `pandas-ta` / `ta-lib` | Alternative indicator implementations |
| `regime-detection` | Filter: only run in trending 30m regimes |
| `atr` via `custom-indicators` | Volatility inputs for stop sizing |
| `position-sizing` | Replace the flat 5% margin with vol-adjusted sizing |
| `risk-management` | Portfolio guardrails around per-symbol trades |
| `vectorbt` / `backtrader` | Larger-scale parameter sweeps and analytics |
| `trade-journal` | Persist the Entry Snapshot per trade |

*This skill provides analytical tools and information only. It does not
constitute financial advice or trading recommendations.*
