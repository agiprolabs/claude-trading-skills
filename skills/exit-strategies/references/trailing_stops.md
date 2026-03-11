# Trailing Stops — Complete Reference

## Overview

A trailing stop follows price in the favorable direction and never moves against
the position. When price reverses by the trail amount, the position is closed.
Trailing stops let winners run while protecting accumulated profit.

**Core rule**: Trailing stops only move _up_ for longs (and _down_ for shorts).
They never widen.

## Percentage Trailing

The simplest trailing stop. Trail a fixed percentage below the highest price
since entry.

```python
def percentage_trail(
    prices: list[float],
    entry_price: float,
    trail_pct: float = 0.10,
) -> dict:
    """Simulate a percentage trailing stop.

    Args:
        prices: List of close prices after entry.
        entry_price: Price at entry.
        trail_pct: Trail distance as decimal (0.10 = 10%).

    Returns:
        Dict with exit_bar, exit_price, peak_price, pnl_pct.
    """
    peak = entry_price
    for i, price in enumerate(prices):
        peak = max(peak, price)
        stop_level = peak * (1 - trail_pct)
        if price <= stop_level:
            pnl = (price - entry_price) / entry_price
            return {
                "exit_bar": i,
                "exit_price": price,
                "peak_price": peak,
                "pnl_pct": round(pnl * 100, 2),
            }
    pnl = (prices[-1] - entry_price) / entry_price
    return {
        "exit_bar": len(prices) - 1,
        "exit_price": prices[-1],
        "peak_price": peak,
        "pnl_pct": round(pnl * 100, 2),
    }
```

### Recommended Trail Percentages

| Style | Trail % | Rationale |
|-------|---------|-----------|
| Scalp | 3–5% | Tight, locks quick gains |
| Day trade | 7–12% | Room for intraday noise |
| Swing trade | 15–25% | Accommodates multi-day swings |
| Meme/PumpFun | 20–35% | Extreme volatility needs wide trail |

**Tip**: If the trail is tighter than 1× ATR, you will be stopped by noise.

## ATR Trailing (Chandelier Exit)

Uses ATR to set a volatility-adaptive trailing distance. Named "Chandelier"
because it hangs from the highest high.

```python
def chandelier_exit(
    highs: list[float],
    closes: list[float],
    atr_values: list[float],
    multiplier: float = 2.5,
    lookback: int = 22,
) -> dict:
    """Calculate Chandelier Exit trailing stop.

    Args:
        highs: High prices.
        closes: Close prices.
        atr_values: ATR values aligned with price bars.
        multiplier: ATR multiplier.
        lookback: Period for highest high.

    Returns:
        Dict with exit info or None if not triggered.
    """
    for i in range(lookback, len(closes)):
        highest_high = max(highs[i - lookback : i + 1])
        stop = highest_high - (atr_values[i] * multiplier)
        if closes[i] <= stop:
            entry_approx = closes[lookback]
            pnl = (closes[i] - entry_approx) / entry_approx
            return {
                "exit_bar": i,
                "exit_price": closes[i],
                "stop_level": stop,
                "pnl_pct": round(pnl * 100, 2),
            }
    return None
```

### Recommended Parameters

| Parameter | Default | Crypto Adjustment |
|-----------|---------|-------------------|
| ATR period | 14 | 10 (faster adaptation) |
| Multiplier | 3.0 | 2.5 (tighter for 24/7 markets) |
| Lookback | 22 | 20 (fewer trading days concept) |

**Why ATR trailing is superior to fixed %**: A 10% trail might be tight for a
token with 15% daily swings but excessively wide for a stablecoin. ATR adapts
automatically.

## Parabolic SAR

The Parabolic Stop and Reverse (SAR) uses an acceleration factor that tightens
the stop as the trend progresses.

### Parameters

| Parameter | Standard | Crypto Recommended |
|-----------|----------|-------------------|
| AF start | 0.02 | 0.01 |
| AF increment | 0.02 | 0.01 |
| AF max | 0.20 | 0.15 |

Lower AF values for crypto because:
- Crypto has higher noise-to-signal ratio
- Standard parameters trigger too frequently
- The slower acceleration gives trends more room

### Usage with pandas-ta

```python
import pandas_ta as ta

# Standard parameters
sar_standard = df.ta.psar(af0=0.02, af=0.02, max_af=0.2)

# Crypto-adjusted parameters
sar_crypto = df.ta.psar(af0=0.01, af=0.01, max_af=0.15)

# Exit when price crosses below the SAR (for longs)
exit_signal = df["close"] < sar_crypto["PSARl_0.01_0.15"]
```

### Strengths and Weaknesses

- **Strength**: Self-tightening — the longer the trend, the closer the stop.
- **Strength**: No lookback period needed.
- **Weakness**: Whipsaws in ranging markets.
- **Weakness**: Cannot be used in isolation — combine with trend filter.

## EMA Trailing

Exit when price closes below an EMA for M consecutive bars.

```python
def ema_trailing_stop(
    closes: list[float],
    ema_values: list[float],
    consecutive_required: int = 2,
) -> dict | None:
    """Exit on M consecutive closes below EMA.

    Args:
        closes: Close prices.
        ema_values: EMA values aligned with closes.
        consecutive_required: Number of consecutive closes below EMA.

    Returns:
        Exit info dict or None.
    """
    below_count = 0
    for i in range(len(closes)):
        if closes[i] < ema_values[i]:
            below_count += 1
            if below_count >= consecutive_required:
                return {
                    "exit_bar": i,
                    "exit_price": closes[i],
                    "ema_value": ema_values[i],
                }
        else:
            below_count = 0
    return None
```

### EMA Period Selection

| Style | EMA Period | Consecutive Bars | Rationale |
|-------|-----------|-----------------|-----------|
| Scalp | EMA(8–10) | 1–2 | Fast reaction |
| Day trade | EMA(20) | 2–3 | Filters intrabar noise |
| Swing | EMA(50) | 2–3 | Major trend following |
| Position | EMA(100–200) | 3–5 | Very slow, big picture |

**Requiring consecutive bars** is critical. A single close below the EMA in a
strong uptrend is normal — requiring 2–3 confirms the trend has actually changed.

## SuperTrend as Trailing Stop

SuperTrend combines ATR with a directional component. It stays below price in
uptrends and above price in downtrends.

### Calculation

```python
def supertrend(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    atr_values: list[float],
    multiplier: float = 3.0,
) -> list[float]:
    """Calculate SuperTrend values.

    Args:
        highs, lows, closes: OHLC data.
        atr_values: ATR values.
        multiplier: ATR multiplier.

    Returns:
        List of SuperTrend stop levels.
    """
    st = [0.0] * len(closes)
    for i in range(1, len(closes)):
        mid = (highs[i] + lows[i]) / 2
        upper = mid + (atr_values[i] * multiplier)
        lower = mid - (atr_values[i] * multiplier)

        # Lower band only moves up
        if closes[i - 1] > st[i - 1]:
            st[i] = max(lower, st[i - 1]) if closes[i] > lower else upper
        else:
            st[i] = min(upper, st[i - 1]) if closes[i] < upper else lower
    return st
```

### Recommended Parameters

| Volatility Regime | ATR Period | Multiplier |
|-------------------|-----------|------------|
| Low | 10 | 2.0 |
| Normal | 10 | 3.0 |
| High | 10 | 4.0 |

## Step Trailing (Ratchet Stop)

Move the stop up in discrete steps as the trade hits milestones.

```python
RATCHET_LEVELS = [
    {"trigger_rr": 2.0, "stop_to": "breakeven"},
    {"trigger_rr": 3.0, "stop_to": "1r_profit"},
    {"trigger_rr": 5.0, "stop_to": "3r_profit"},
    {"trigger_rr": 10.0, "stop_to": "7r_profit"},
]
```

| When Price Reaches | Move Stop To | Locked Profit |
|-------------------|-------------|---------------|
| 2× risk | Breakeven (entry) | 0 (risk-free) |
| 3× risk | 1× risk above entry | 1R locked |
| 5× risk | 3× risk above entry | 3R locked |
| 10× risk | 7× risk above entry | 7R locked |

**Advantage**: Simple mental model. You always know exactly where your stop is.
**Disadvantage**: Leaves more on the table than smooth trailing in strong trends.

## Implementation Notes

- **Check on bar close, not intra-bar.** Wicks frequently violate stop levels
  then recover. Use closing price to avoid false triggers.
- **Activation delay.** Wait until 1R profit before enabling the trail. This
  prevents being stopped by initial noise after entry.
- **Combine fast + slow trails.** Use a fast trail (8% or ATR×1.5) for partial
  exit (50%) and a slow trail (20% or ATR×3.0) for the moonbag remainder.
