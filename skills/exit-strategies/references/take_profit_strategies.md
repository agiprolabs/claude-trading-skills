# Take Profit Strategies — Complete Reference

## Overview

Take profit (TP) rules define where and how you lock in gains. Without TP rules,
winning trades reverse into losses. This reference covers fixed R:R targets, scaled
exits, market cap milestones, Fibonacci extensions, and volume-based exits.

## Fixed Risk/Reward Targets

### Methodology

1. Define risk: `risk = entry_price - stop_loss_price`
2. Set TP: `tp = entry_price + (risk × R_ratio)`

```python
def calculate_rr_targets(
    entry: float,
    stop: float,
    ratios: list[float] = [2.0, 3.0, 5.0],
) -> list[dict]:
    """Calculate take profit levels at specified R:R ratios.

    Args:
        entry: Entry price.
        stop: Stop loss price.
        ratios: List of risk/reward ratios.

    Returns:
        List of dicts with ratio, price, and gain percentage.
    """
    risk = entry - stop
    targets = []
    for r in ratios:
        tp_price = entry + (risk * r)
        gain_pct = (tp_price - entry) / entry * 100
        targets.append({
            "ratio": f"{r:.1f}:1",
            "price": round(tp_price, 6),
            "gain_pct": round(gain_pct, 2),
        })
    return targets
```

### Recommended Ratios by Style

| Trading Style | Min R:R | Target R:R | Notes |
|--------------|---------|------------|-------|
| Scalp | 1.5:1 | 2:1 | High win rate compensates for lower R:R |
| Day trade | 2:1 | 3:1 | Standard for intraday setups |
| Swing trade | 3:1 | 5:1 | Wider stops need bigger targets |
| PumpFun snipe | 5:1 | 10:1+ | Low win rate, need big winners |

### Break-Even Analysis

Minimum win rate needed to be profitable at each R:R (excluding fees):

| R:R | Required Win Rate |
|-----|-------------------|
| 1:1 | >50% |
| 2:1 | >33% |
| 3:1 | >25% |
| 5:1 | >17% |
| 10:1 | >9% |

This is why high R:R strategies can be profitable with low win rates.

## Scaled Exit Framework

Selling the entire position at one level is suboptimal. Scaled exits capture
profits progressively while keeping exposure to further upside.

### Standard 4-Tranche Model

```python
SCALED_EXIT_PLAN = [
    {
        "tranche": 1,
        "sell_pct": 0.25,
        "target_rr": 2.0,
        "label": "Cover cost + small profit",
        "post_action": "Move stop to breakeven",
    },
    {
        "tranche": 2,
        "sell_pct": 0.25,
        "target_rr": 4.0,
        "label": "Meaningful profit locked",
        "post_action": "Trail stop at 2× entry",
    },
    {
        "tranche": 3,
        "sell_pct": 0.25,
        "target_rr": 8.0,
        "label": "Major profit captured",
        "post_action": "Tighten trail to 10% from peak",
    },
    {
        "tranche": 4,
        "sell_pct": 0.25,
        "target_rr": None,
        "label": "Moonbag — trailing stop only",
        "post_action": "Trail with EMA(20) or 15% from peak",
    },
]
```

### Why Scaled Exits Work

- **Tranche 1** removes psychological pressure — you have locked in some profit.
- **Moving to breakeven** after Tranche 1 makes the trade risk-free.
- **Tranches 2–3** capture the majority of the move.
- **Tranche 4 (moonbag)** captures outlier moves at zero additional risk.

### Aggressive Variant (PumpFun / Meme Tokens)

For extremely volatile tokens where moves are fast and violent:

```python
AGGRESSIVE_PLAN = [
    {"sell_pct": 0.50, "target_rr": 2.0, "label": "Half out, secure base"},
    {"sell_pct": 0.25, "target_rr": 5.0, "label": "Quarter at 5×"},
    {"sell_pct": 0.25, "target_rr": None, "label": "Trail with 20% stop"},
]
```

Taking 50% off early is appropriate when the median outcome is a loss and you
need to capitalize aggressively on winners.

## Market Cap Milestone Exits

For PumpFun and meme tokens, absolute price targets are less meaningful than
market cap milestones since these tokens start from near-zero.

```python
MCAP_MILESTONES = [
    {"mcap": 30_000,   "sell_pct": 0.25, "note": "Cover entry cost"},
    {"mcap": 100_000,  "sell_pct": 0.25, "note": "Lock solid profit"},
    {"mcap": 500_000,  "sell_pct": 0.25, "note": "Major milestone"},
    {"mcap": 1_000_000, "sell_pct": 0.25, "note": "Moonbag exit or trail"},
]
```

### Market Cap to Price Conversion

```python
def mcap_to_price(target_mcap: float, total_supply: float) -> float:
    """Convert market cap target to token price."""
    return target_mcap / total_supply
```

Ensure you use **circulating supply**, not total supply, for accurate mcap
calculations. On PumpFun, total supply is typically 1 billion tokens.

## Fibonacci Extension Targets

Use Fibonacci extensions from the initial impulse move to project take profit
levels during continuation.

### Key Extension Levels

| Level | Use |
|-------|-----|
| 1.000 | Measured move (100% extension) |
| 1.272 | Conservative TP |
| 1.618 | Standard TP — most commonly respected |
| 2.000 | Aggressive TP |
| 2.618 | Strong trend TP |
| 4.236 | Euphoric extension — rare but happens in crypto |

### Calculation

```python
def fibonacci_extensions(
    swing_low: float,
    swing_high: float,
    pullback_low: float,
    levels: list[float] = [1.0, 1.272, 1.618, 2.618, 4.236],
) -> list[dict]:
    """Calculate Fibonacci extension levels.

    Args:
        swing_low: Start of the impulse move.
        swing_high: End of the impulse move.
        pullback_low: Low of the retracement.
        levels: Extension ratios to calculate.

    Returns:
        List of dicts with level and price.
    """
    impulse = swing_high - swing_low
    results = []
    for lvl in levels:
        price = pullback_low + (impulse * lvl)
        results.append({"level": lvl, "price": round(price, 6)})
    return results
```

### Example

Swing low: $0.001, Swing high: $0.010, Pullback: $0.006

- 1.000 ext: $0.006 + $0.009 × 1.000 = $0.015
- 1.618 ext: $0.006 + $0.009 × 1.618 = $0.0206
- 2.618 ext: $0.006 + $0.009 × 2.618 = $0.0296

## Volume-Based Exits

Exit when buying pressure fades, regardless of price level.

```python
def check_volume_exit(
    recent_volume: float,
    baseline_volume: float,
    threshold: float = 0.3,
) -> bool:
    """Signal exit when recent volume drops below threshold of baseline.

    Args:
        recent_volume: Average volume over last N bars (e.g., 5).
        baseline_volume: Average volume over longer period (e.g., 50).
        threshold: Ratio below which volume is considered weak.

    Returns:
        True if volume exit should trigger.
    """
    if baseline_volume == 0:
        return False
    return recent_volume < (baseline_volume * threshold)
```

Volume exits are especially important for:
- Meme tokens where volume drives 100% of price action
- Low-float tokens where a few large sellers can crash price
- Tokens post-pump where volume naturally decays

## Combining Take Profit Methods

The most robust approach combines multiple methods:

1. **Primary TP**: Scaled R:R exits (Tranches 1–3)
2. **Moonbag TP**: Trailing stop on final tranche
3. **Override**: Volume-based exit if volume collapses before TP is reached
4. **Ceiling**: Fibonacci 2.618 or 4.236 as maximum expectation

The scaled exit handles the common case. The volume exit protects against
momentum death. The Fibonacci extension provides a reality check on targets.
