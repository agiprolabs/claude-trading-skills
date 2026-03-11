# Stop Loss Methods — Complete Reference

## Overview

A stop loss is a predefined price level at which a position is closed to limit
downside. Every trade must have a stop loss defined before entry. This reference
covers all major stop loss methods, when to use each, and common anti-patterns.

## Fixed Percentage Stops

Exit when the position declines by a fixed percentage from entry.

| Stop % | Use Case | Notes |
|--------|----------|-------|
| 5% | Tight scalps on liquid pairs | Requires high win rate (>60%) |
| 10% | Day trades on mid-cap tokens | Good balance for moderate volatility |
| 15% | Swing trades on volatile tokens | Allows room for crypto noise |
| 20% | Wide stops for high-conviction plays | Max recommended for single trade |

**Calculation:**

```python
def fixed_pct_stop(entry_price: float, stop_pct: float) -> float:
    """Calculate fixed percentage stop loss price.

    Args:
        entry_price: Price at entry.
        stop_pct: Stop percentage as decimal (0.10 = 10%).

    Returns:
        Stop loss price.
    """
    return entry_price * (1 - stop_pct)
```

**When to use:** Simple setups where volatility analysis is not available or when
you need a quick, predictable risk cap.

**Limitation:** Not adaptive to market conditions. A 10% stop may be too tight
in high-volatility environments and too wide in low-volatility ones.

## ATR-Based Stops

Use Average True Range to set stops that adapt to current volatility.

**Core calculation:**

```python
def atr_stop(
    entry_price: float,
    atr_value: float,
    multiplier: float = 2.0,
) -> float:
    """Calculate ATR-based stop loss.

    Args:
        entry_price: Price at entry.
        atr_value: Current ATR(14) value.
        multiplier: ATR multiplier (1.5 tight, 2.0 standard, 3.0 wide).

    Returns:
        Stop loss price.
    """
    return entry_price - (atr_value * multiplier)
```

### Multiplier Guide

| Multiplier | Style | Win Rate Needed | Typical R:R |
|-----------|-------|-----------------|-------------|
| 1.0× | Very tight | >65% | 1:1 – 2:1 |
| 1.5× | Tight | >55% | 2:1 – 3:1 |
| 2.0× | Standard | >45% | 3:1 – 5:1 |
| 2.5× | Moderate | >40% | 4:1 – 6:1 |
| 3.0× | Wide | >35% | 5:1 – 10:1 |

### ATR Period by Timeframe

| Timeframe | ATR Period | Rationale |
|-----------|-----------|-----------|
| 1-minute | ATR(7) | Fast adaptation to micro-volatility |
| 5-minute | ATR(10) | Balance of speed and stability |
| 15-minute | ATR(14) | Standard, most widely tested |
| 1-hour | ATR(14) | Standard |
| 4-hour | ATR(14–20) | Smoother, fewer whipsaws |
| Daily | ATR(14–20) | Standard swing trading period |

### Example

Entry at $1.00, ATR(14) = $0.08:

- 1.5× ATR stop: $1.00 − ($0.08 × 1.5) = $0.88 (12% risk)
- 2.0× ATR stop: $1.00 − ($0.08 × 2.0) = $0.84 (16% risk)
- 3.0× ATR stop: $1.00 − ($0.08 × 3.0) = $0.76 (24% risk)

## Volatility-Adjusted Stops

Adapt stop distance based on the _current volatility regime_ rather than
a fixed multiplier.

```python
import numpy as np

def volatility_adjusted_stop(
    entry_price: float,
    atr_value: float,
    atr_history: list[float],
    base_multiplier: float = 2.0,
) -> float:
    """Widen/tighten stop based on volatility percentile.

    High volatility → wider stop. Low volatility → tighter stop.
    """
    percentile = np.searchsorted(
        np.sort(atr_history), atr_value
    ) / len(atr_history)

    # Scale multiplier: 0.7× at low vol, 1.3× at high vol
    vol_scale = 0.7 + (percentile * 0.6)
    adjusted_mult = base_multiplier * vol_scale

    return entry_price - (atr_value * adjusted_mult)
```

This prevents being stopped out during volatility spikes while keeping stops
tight during quiet markets.

## Support-Based Stops

Place stop below the nearest significant support level.

**Identification methods:**
1. **Swing low**: Lowest low in the last N bars
2. **Volume profile**: Below the nearest high-volume node
3. **Round numbers**: Below psychological levels (with offset)
4. **Previous resistance turned support**: Below the flip level

```python
def support_stop(
    swing_low: float,
    offset_pct: float = 0.02,
) -> float:
    """Place stop below swing low with offset to avoid stop hunts.

    Args:
        swing_low: Nearest swing low price.
        offset_pct: Buffer below swing low (default 2%).

    Returns:
        Stop loss price.
    """
    return swing_low * (1 - offset_pct)
```

**Important**: Always add an offset below the support level. Placing stops
exactly at support is where everyone else puts them — market makers and bots
target these clusters.

## Time Stops

Exit if the trade has not moved favorably within a defined number of bars.

```python
def check_time_stop(
    bars_held: int,
    max_hold: int,
    current_pnl_pct: float,
    threshold: float = 0.0,
) -> bool:
    """Return True if time stop is triggered.

    Only triggers if the trade is not meaningfully profitable.
    """
    return bars_held >= max_hold and current_pnl_pct <= threshold
```

| Style | Max Hold | Threshold |
|-------|----------|-----------|
| PumpFun snipe | 5–20 bars (1m) | Must be >+50% |
| Scalp | 15–30 bars (1m) | Must be >0% |
| Day trade | 20–50 bars (15m) | Must be >0% |
| Swing | 10–20 bars (4h) | Must be >breakeven |

## Combining Stop Methods

Use a layered approach:

1. **Hard stop (always active)**: Maximum acceptable loss — never violated.
   Typically 20% for crypto.
2. **Indicator stop (primary)**: ATR-based or support-based. This is your
   actual stop for most trades.
3. **Time stop (secondary)**: Eject dead trades that neither hit stop nor
   profit target.

```python
def evaluate_stops(
    entry_price: float,
    current_price: float,
    hard_stop: float,
    indicator_stop: float,
    bars_held: int,
    max_hold: int,
) -> str | None:
    """Check all stop conditions in priority order."""
    if current_price <= hard_stop:
        return "hard_stop"
    if current_price <= indicator_stop:
        return "indicator_stop"
    pnl_pct = (current_price - entry_price) / entry_price
    if bars_held >= max_hold and pnl_pct <= 0:
        return "time_stop"
    return None  # No stop triggered
```

## Stop Placement Anti-Patterns

### Round Numbers

Placing stops at $1.00, $0.50, $10.00 etc. These are the most common stop
levels and frequently targeted by large players.

**Fix**: Offset by 1–3% below the round number.

### Too Tight

Stops inside the normal noise range of the asset. If ATR is 8% and your stop
is 3%, you will be stopped out by random fluctuation.

**Fix**: Stop should be at minimum 1× ATR from entry. Ideally 1.5–2×.

### Too Wide

Stops so far from entry that a single loss wipes out many winners.

**Fix**: If the required stop distance implies risk >5% of account, reduce
position size rather than widening the stop.

### Moving Stops Away from Price

Widening a stop after entry because the trade is going against you. This
violates the original risk assessment.

**Fix**: The stop defined at entry is final. If it is hit, accept the loss.

### No Stop at All

Hoping the trade recovers. In crypto, tokens can go to zero. A -50% loss
requires a +100% gain to recover.

**Fix**: Every trade gets a stop. No exceptions.

## Quick Reference

| Method | Formula | Adaptive | Complexity |
|--------|---------|----------|------------|
| Fixed % | `entry × (1 − pct)` | No | Low |
| ATR-based | `entry − ATR × mult` | Yes | Medium |
| Vol-adjusted | ATR + percentile scaling | Yes | Medium |
| Support-based | `swing_low × (1 − offset)` | Partially | Medium |
| Time stop | Bars held > max | N/A | Low |
| Combined | Priority stack | Yes | High |
