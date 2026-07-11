# TF30M HMA20-EMA Cross Momentum — Full Specification

Complete rule reference for the 30-minute HMA20 gate + EMA5/EMA9 cross
momentum strategy. This is the source of truth the engine in
`scripts/tf30m_hma_ema_strategy.py` implements.

---

## 1. General Settings

| Item | Value |
|------|-------|
| Timeframe | 30 minutes |
| HMA | HMA(20) |
| EMA fast / slow | EMA(5) / EMA(9) |
| ROC | ROC(9) |
| RSI | RSI(14) |
| ADX | ADX(14) |
| Volume average | Volume SMA(20) |
| ATR | ATR(14) |
| Position margin | 5% of current account balance |
| Stop-loss distance | ATR(14) × 1.5 |
| Risk-to-reward | 1 : 1 |
| Take-profit distance | ATR(14) × 1.5 |
| Max positions | 1 per symbol |
| Entry evaluation | on 30m bar close |
| Signal exit evaluation | on 30m bar close |
| SL / TP | live at all times while a position is open |

---

## 2. System Structure

Three parts:

1. **Direction Gate** — HMA20 decides whether the system may look for a Long
   or a Short.
2. **Entry Trigger** — EMA5 crossing EMA9 begins a setup.
3. **Confirmation Score** — ROC, RSI, ADX, and Volume validate setup quality.

```
Entry = HMA20 Gate  AND  EMA5/EMA9 Trigger  AND  (Confirmation >= 3 of 4)
```

---

## 3. Long Direction Gate

Passes when the open of the EMA-cross bar is above HMA20, and HMA20 is not
sloping down:

```
open > hma20  AND  hma20 >= hma20_prev
```

If the open is not above HMA20, no Long setup starts — even if EMA5 crosses
above EMA9.

## 4. Long Entry Trigger

Fires when EMA5 crosses **above** EMA9, with the Long Gate passing on the same
bar. On trigger:

1. The cross bar is Bar 1.
2. A 3-bar Long Confirmation Window opens (Bar 1 → Bar 3).
3. Confirmation is evaluated across the window.
4. EMA5 must stay above EMA9.
5. Each bar's open must stay above HMA20.

## 5. Long Confirmation Score

Four conditions, 1 point each, need ≥ 3:

1. **ROC** — `roc9 > 0`
2. **RSI** — `rsi14 > 50`
3. **ADX** — `adx14 >= 18 AND adx14 > adx14_prev`
4. **Volume** — `volume >= volume_sma20`

```
long_score = (roc9 > 0)
           + (rsi14 > 50)
           + (adx14 >= 18 and adx14 > adx14_prev)
           + (volume >= volume_sma20)
require: long_score >= 3
```

## 6. Long Entry

```
IF open > hma20
   AND hma20 >= hma20_prev
   AND long_setup_active
   AND ema5 > ema9
   AND long_confirmation_score >= 3
   AND confirmation_bar <= 3
   AND no_open_position
THEN open long
```

- Entry price = close of the confirming bar.
- `long_sl = entry - atr14 * 1.5`
- `long_tp = entry + atr14 * 1.5`
- `margin = balance * 0.05`

## 7. Long Setup Failure

Failed if any of:

1. Bar 3 reached with score still < 3.
2. EMA5 crosses below EMA9 during the window.
3. EMA5 ≤ EMA9.
4. Any bar's open ≤ HMA20 during the setup.
5. HMA20 begins sloping down (`hma20 < hma20_prev`).
6. A Short trigger occurs before the Long setup completes.
7. A position is already open.

On failure: cancel the window, reset the score, do **not** reuse the same EMA
cross, and wait for a new EMA5-cross-above-EMA9 that occurs while the Long
Gate passes.

---

## 8–12. Short Side (mirror image)

- **Gate**: `open < hma20 AND hma20 <= hma20_prev`
- **Trigger**: EMA5 crosses **below** EMA9 with the gate passing.
- **Confirmation**: `roc9 < 0`, `rsi14 < 50`, `adx14 >= 18 and adx14 >
  adx14_prev`, `volume >= volume_sma20`; need ≥ 3.
- **Entry**: symmetric; `short_sl = entry + atr14*1.5`, `short_tp = entry -
  atr14*1.5`.
- **Failure**: symmetric to the long side (EMA cross up, open ≥ HMA20, HMA
  sloping up, a Long trigger first, etc.). Reset and wait for a fresh
  EMA5-cross-below-EMA9 under a passing gate.

---

## 13. Entry Snapshot

On position open, record:

```
entry_direction, entry_price, entry_atr, entry_hma20, entry_ema5, entry_ema9,
entry_roc9, entry_rsi14, entry_adx14, entry_volume,
entry_confirmation_score, entry_confirmation_components
```

Example: `ROC=TRUE RSI=TRUE ADX=FALSE Volume=TRUE → Score 3/4`.

The snapshot is for logging, analysis, and backtesting. It does **not** imply
that every indicator that passed at entry must flip before exit — exit uses
only the direction indicators (§15–16).

---

## 14. Indicator Classification

| Role | Indicators | Used for |
|------|-----------|----------|
| Direction | HMA20, EMA5/EMA9, ROC9 | entry **and** exit |
| Momentum confirmation | RSI14 | entry (may warn; not a solo exit) |
| Quality | ADX14, Volume vs SMA20 | entry quality only |

Rules: never close on falling ADX alone; never close on below-average volume
alone. A falling ADX or thin volume is a pause, not a reversal.

---

## 15. Long Early Exit

Close 100% immediately when any one direction signal reverses:

```
IF close < hma20  OR  ema5_cross_below_ema9  OR  roc9 < 0
THEN close long 100%
```

No waiting for multiple signals, TP, or SL. Not ADX-down, volume-down, or
RSI<50 as a solo exit.

## 16. Short Early Exit

```
IF close > hma20  OR  ema5_cross_above_ema9  OR  roc9 > 0
THEN close short 100%
```

---

## 17. Exit Priority

1. Emergency risk protection
2. Stop Loss
3. Take Profit
4. Direction signal exit (on bar close)
5. Position monitoring

If SL or TP already executed, do not send a duplicate signal exit.

## 18. No Immediate Reversal

Closing a Long on a reverse signal must not open a Short on the same bar (and
vice-versa). After any exit: reset the setup, return to WAITING, wait for a
new EMA cross, re-pass the HMA20 gate, and open a fresh confirmation window.
The system does not auto-reverse off the exit signal.

---

## 19. State Machine

States: `WAITING`, `LONG_CONFIRMATION`, `SHORT_CONFIRMATION`,
`LONG_POSITION`, `SHORT_POSITION`, `EXITING`, `RESET`.

```
Long flow:
WAITING
  → open > hma20 and hma20 not down
  → EMA5 cross above EMA9
  → LONG_CONFIRMATION (bar 1..3)
  → ROC/RSI/ADX/Volume >= 3 of 4
  → LONG_POSITION  (SL = ATR*1.5, TP = ATR*1.5)
  → check exit every bar close
  → close < hma20 OR EMA cross down OR roc9 < 0
  → close long 100% → RESET → WAITING

Short flow: mirror image.
```

---

## 20. Pseudocode (per 30m bar close)

```
ON_EACH_30M_BAR_CLOSE:

  compute hma20, ema5, ema9, roc9, rsi14, adx14, volume_sma20, atr14
  detect ema_cross_up, ema_cross_down
  block_new_entry_for_current_bar = FALSE

  # SL/TP are always live (checked intrabar against high/low).

  IF position == LONG:
      long_exit = close < hma20 OR ema_cross_down OR roc9 < 0
      IF long_exit:
          close_long_100(); reset_all(); state = WAITING
          block_new_entry_for_current_bar = TRUE
          RETURN

  IF position == SHORT:
      short_exit = close > hma20 OR ema_cross_up OR roc9 > 0
      IF short_exit:
          close_short_100(); reset_all(); state = WAITING
          block_new_entry_for_current_bar = TRUE
          RETURN

  IF position_exists: RETURN
  IF block_new_entry_for_current_bar: RETURN

  IF state == WAITING:
      long_gate = open > hma20 AND hma20 >= hma20_prev
      IF long_gate AND ema_cross_up:
          state = LONG_CONFIRMATION; confirmation_bar = 1; RETURN

  IF state == WAITING:
      short_gate = open < hma20 AND hma20 <= hma20_prev
      IF short_gate AND ema_cross_down:
          state = SHORT_CONFIRMATION; confirmation_bar = 1; RETURN

  IF state == LONG_CONFIRMATION:
      IF open <= hma20 OR hma20 < hma20_prev OR ema5 <= ema9 OR ema_cross_down:
          fail_long(); state = WAITING; RETURN
      long_score = (roc9>0) + (rsi14>50)
                 + (adx14>=18 AND adx14>adx14_prev) + (volume>=volume_sma20)
      IF long_score >= 3:
          entry = close; dist = atr14*1.5
          open_long(margin=balance*0.05, sl=entry-dist, tp=entry+dist)
          save_snapshot(); state = LONG_POSITION; reset_confirmation(); RETURN
      IF confirmation_bar >= 3:
          fail_long(); state = WAITING; RETURN
      confirmation_bar += 1

  IF state == SHORT_CONFIRMATION:
      IF open >= hma20 OR hma20 > hma20_prev OR ema5 >= ema9 OR ema_cross_up:
          fail_short(); state = WAITING; RETURN
      short_score = (roc9<0) + (rsi14<50)
                  + (adx14>=18 AND adx14>adx14_prev) + (volume>=volume_sma20)
      IF short_score >= 3:
          entry = close; dist = atr14*1.5
          open_short(margin=balance*0.05, sl=entry+dist, tp=entry-dist)
          save_snapshot(); state = SHORT_POSITION; reset_confirmation(); RETURN
      IF confirmation_bar >= 3:
          fail_short(); state = WAITING; RETURN
      confirmation_bar += 1
```

**Implementation note on the confirmation window.** Following the pseudocode
literally, `START SETUP` sets `confirmation_bar = 1` and returns on the cross
bar, so the score is first evaluated on the next bar. The counter therefore
enumerates the three evaluation bars after the cross. The engine reproduces
this exactly; if you prefer to also score the cross bar itself, evaluate the
confirmation block before returning in `START SETUP`.

---

## 21. Final Rule Summary

**Long entry**: `open > hma20` AND HMA not down AND EMA5 cross above EMA9 AND,
within 3 bars, ≥ 3 of {ROC9>0, RSI14>50, ADX14≥18 & rising, Volume≥SMA20}.

**Long exit**: `close < hma20` OR EMA5 cross below EMA9 OR `roc9 < 0` → close
100%.

**Short entry / exit**: mirror image.

ADX and Volume are entry-quality filters only.
