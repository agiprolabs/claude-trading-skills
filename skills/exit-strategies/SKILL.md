---
name: exit-strategies
description: Systematic exit rules, stop-loss methods, take-profit strategies, and trailing stop implementations for crypto trading
---

# Exit Strategies

Entries are easy, exits are everything. A mediocre entry with a disciplined exit will
outperform a perfect entry with no exit plan. This skill covers systematic, rule-based
exit methods for crypto and Solana token trading.

## Why Exits Matter

- **Entries** determine _if_ you participate. **Exits** determine _how much_ you keep.
- Most traders spend 90% of effort on entries and 10% on exits — invert this.
- Without defined exits you rely on emotion, which guarantees inconsistency.
- Every trade should have **three exits defined before entry**: stop loss, take profit,
  and trailing stop.

## Exit Categories

### 1. Stop Loss — Risk Management Exits

Predefined price level where you close the position to cap downside.

| Method | Description | Best For |
|--------|-------------|----------|
| Fixed percentage | Exit at entry − X% | Simple setups, beginners |
| ATR-based | Entry − ATR(14) × multiplier | Volatility-adaptive |
| Support level | Below nearest swing low | Technically defined risk |
| Maximum loss | Absolute SOL/USD cap | Account protection |

**ATR-based stop (recommended default):**

```python
import pandas_ta as ta

atr = df.ta.atr(length=14)
stop_loss = entry_price - (atr.iloc[-1] * 2.0)  # 2x ATR below entry
```

Multiplier guide:
- **1.5×** — Tight. High win rate needed. Good for scalps.
- **2.0×** — Standard. Balances noise filtering with risk.
- **3.0×** — Wide. For swing trades in volatile conditions.

See `references/stop_loss_methods.md` for complete methodology.

### 2. Take Profit — Target Exits

Predefined levels where you lock in gains.

**Fixed risk/reward targets:**

```python
risk = entry_price - stop_loss_price
tp_2r = entry_price + (risk * 2)  # 2:1 R:R
tp_3r = entry_price + (risk * 3)  # 3:1 R:R
tp_5r = entry_price + (risk * 5)  # 5:1 R:R
```

**Scaled exit framework (recommended for meme/PumpFun tokens):**

| Tranche | Size | Target | Action After |
|---------|------|--------|--------------|
| 1 | 25% | 2× risk | Move stop to breakeven |
| 2 | 25% | 3–5× risk | Trail remainder |
| 3 | 25% | 5–10× risk | Tighten trail |
| 4 | 25% | Trailing stop | Moonbag — let it ride |

**Market cap milestone exits:**

For PumpFun and meme tokens where R:R ratios are less meaningful:

```python
milestones = [
    {"mcap": 50_000,  "sell_pct": 0.25, "label": "Cover cost"},
    {"mcap": 100_000, "sell_pct": 0.25, "label": "Lock profit"},
    {"mcap": 500_000, "sell_pct": 0.25, "label": "Major profit"},
    # Hold 25% as moonbag with trailing stop
]
```

See `references/take_profit_strategies.md` for full methodology including Fibonacci
extension targets and volume-based exits.

### 3. Trailing Stop — Trend-Following Exits

Dynamic stops that follow price upward but never move down.

**Percentage trailing:**

```python
def percentage_trailing_stop(
    current_price: float,
    highest_since_entry: float,
    trail_pct: float = 0.10,
) -> tuple[float, bool]:
    """Return (stop_level, triggered)."""
    highest = max(highest_since_entry, current_price)
    stop = highest * (1 - trail_pct)
    return stop, current_price <= stop
```

**ATR trailing (Chandelier Exit):**

```python
def chandelier_exit(
    highs: list[float],
    atr_value: float,
    multiplier: float = 2.5,
    lookback: int = 22,
) -> float:
    """Highest high over lookback minus ATR * multiplier."""
    highest_high = max(highs[-lookback:])
    return highest_high - (atr_value * multiplier)
```

**EMA trailing:**

```python
# Exit when close < EMA for M consecutive bars
ema = df.ta.ema(length=20)
below_ema = df["close"] < ema
consecutive_below = below_ema.rolling(3).sum() == 3  # 3 bars below
```

Typical EMA periods: 10 (scalp), 20 (day trade), 50 (swing).

See `references/trailing_stops.md` for Parabolic SAR, SuperTrend, and step trailing.

### 4. Time-Based Exits

Exit if the trade hasn't moved in your favor within a defined window.

```python
bars_since_entry = current_bar - entry_bar
if bars_since_entry > max_hold_bars and current_pnl <= 0:
    exit_reason = "time_stop"
```

Guidelines:
- **Scalp**: 5–15 minutes
- **Day trade**: 4–8 hours
- **Swing**: 3–5 days
- **PumpFun snipe**: 2–10 minutes (token-specific)

Time stops prevent capital from sitting in dead trades.

### 5. Signal-Based Exits

Exit when the indicator that generated the entry signal reverses.

```python
# RSI reversal exit
rsi = df.ta.rsi(length=14)
if position == "long" and rsi.iloc[-1] > 70:
    exit_reason = "rsi_overbought"

# MACD crossover exit
macd = df.ta.macd()
if macd["MACDs_12_26_9"].iloc[-1] < macd["MACDh_12_26_9"].iloc[-1]:
    exit_reason = "macd_bearish_cross"
```

Signal exits work well when combined with trailing stops — the signal triggers
tightening the trail rather than an immediate full exit.

### 6. Liquidity-Based Exits

Exit when volume or liquidity deteriorates, signaling reduced ability to exit cleanly.

```python
recent_vol = df["volume"].rolling(10).mean().iloc[-1]
baseline_vol = df["volume"].rolling(50).mean().iloc[-1]

if recent_vol < baseline_vol * 0.3:  # Volume dropped to 30% of baseline
    exit_reason = "liquidity_deterioration"
```

Critical for low-cap Solana tokens where liquidity can evaporate rapidly.

## PumpFun-Specific Exit Rules

PumpFun tokens have unique dynamics requiring specialized exit logic.

### Pre-Graduation Exits

Tokens on the bonding curve before reaching 85 SOL fill:

```python
bonding_fill_pct = current_fill_sol / 85.0

if bonding_fill_pct > 0.90:
    # Near graduation — decide: hold through or exit before
    # Graduation creates volatility spike, both up and down
    pass

if bonding_fill_pct < 0.50 and time_since_entry > 300:  # 5 min
    exit_reason = "stalled_bonding_curve"
```

### Volume Decay Exits

```python
buy_vol_1m = get_buy_volume(token, "1m")
buy_vol_5m = get_buy_volume(token, "5m") / 5  # Normalize to per-minute

if buy_vol_1m < buy_vol_5m * 0.3:
    exit_reason = "buy_volume_decay"
```

### Time Decay for PumpFun

Most PumpFun tokens that will succeed show momentum within the first few minutes:

| Timeframe | Action |
|-----------|--------|
| 0–2 min | Hold — too early to judge |
| 2–5 min | Exit if no 2× from entry |
| 5–10 min | Exit if no 3× from entry |
| 10+ min | Should be trailing, not hoping |

## Combining Exit Rules

A complete exit plan layers multiple rules. Here is a recommended template:

```python
exit_plan = {
    "hard_stop": {
        "type": "fixed_percentage",
        "value": 0.20,  # -20% max loss
        "priority": 1,   # Checked first, always honored
    },
    "atr_stop": {
        "type": "atr_trailing",
        "multiplier": 2.5,
        "atr_length": 14,
        "priority": 2,
    },
    "take_profit": {
        "type": "scaled",
        "tranches": [
            {"at_rr": 2, "sell_pct": 0.25},
            {"at_rr": 4, "sell_pct": 0.25},
            {"at_rr": 8, "sell_pct": 0.25},
        ],
        "priority": 3,
    },
    "time_stop": {
        "type": "max_bars",
        "value": 50,
        "condition": "if_not_profitable",
        "priority": 4,
    },
}
```

**Priority hierarchy**: Hard stop > ATR trailing > Take profit > Time stop.

The hard stop is always active and never overridden. The ATR trailing stop activates
after the first take-profit tranche fills. The time stop only fires if the trade is
not yet profitable.

## Common Exit Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| No stop loss | Unlimited downside | Always define max loss before entry |
| Moving stops wider | Increases risk after the fact | Never move stops away from price |
| Not taking profits | Winners become losers | Use scaled exits |
| All-or-nothing exits | Leaves money on the table or exits too early | Scale out in tranches |
| Round-number stops | Cluster with other traders, get hunted | Offset by small random amount |
| Too-tight stops | Stopped out by normal volatility | Use ATR-based stops |
| Hoping instead of trailing | Gives back profits | Activate trail after first TP |
| Ignoring liquidity | Cannot exit at intended price | Check spread and depth before sizing |

## Integration with Other Skills

- **`position-sizing`** — Size the position based on the stop loss distance.
  `position_size = (account_risk * account_balance) / (entry - stop_loss)`
- **`risk-management`** — Exits are the mechanism that enforces risk limits.
- **`pandas-ta`** — Use ATR, EMA, RSI, MACD for signal-based and trailing exits.
- **`slippage-modeling`** — Estimate execution cost of the exit to set realistic targets.
- **`liquidity-analysis`** — Verify exit liquidity before entering a position.

## Files

### References
- `references/stop_loss_methods.md` — Complete stop loss methodology and anti-patterns
- `references/take_profit_strategies.md` — Scaled exits, R:R targets, Fibonacci extensions
- `references/trailing_stops.md` — Trailing stop implementations and parameter guidance

### Scripts
- `scripts/exit_simulator.py` — Simulate and compare exit strategies on synthetic price data
- `scripts/stop_loss_calculator.py` — Calculate stop levels, position sizes, and R:R targets
