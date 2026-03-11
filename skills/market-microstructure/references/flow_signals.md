# Flow Signals — Orderflow Metrics and Interpretation

## Signal Catalog

This reference covers every flow signal used in microstructure analysis, with formulas,
computation code, interpretation ranges, and combination strategies.

## 1. Buy/Sell Volume Ratio

**Formula:**
```
buy_ratio = buy_volume_usd / (buy_volume_usd + sell_volume_usd)
```

**Range:** 0.0 to 1.0 (0.5 = perfectly balanced)

| Value | Interpretation |
|-------|---------------|
| > 0.70 | Strong buy pressure — aggressive accumulation |
| 0.60 – 0.70 | Moderate buy pressure |
| 0.45 – 0.60 | Neutral / balanced |
| 0.30 – 0.45 | Moderate sell pressure |
| < 0.30 | Strong sell pressure — aggressive distribution |

## 2. Net Flow

**Formula:**
```
net_flow = buy_volume_usd - sell_volume_usd
```

**Range:** Unbounded (positive = net buying, negative = net selling)

Net flow is best used as a **trend indicator** rather than absolute value. Track
the rolling sum over 1h, 4h, and 24h windows:

```python
def rolling_net_flow(trades: list[dict], window_seconds: int) -> float:
    """Compute net flow over a rolling window."""
    cutoff = time.time() - window_seconds
    recent = [t for t in trades if t["timestamp"] >= cutoff]
    buy_vol = sum(t["volume_usd"] for t in recent if t["side"] == "buy")
    sell_vol = sum(t["volume_usd"] for t in recent if t["side"] == "sell")
    return buy_vol - sell_vol
```

## 3. Trade Count Ratio

**Formula:**
```
trade_count_ratio = buy_trades / (buy_trades + sell_trades)
```

This differs from volume ratio because it weights each trade equally regardless of
size. Divergence between volume ratio and count ratio is informative:

| Volume Ratio | Count Ratio | Interpretation |
|-------------|-------------|---------------|
| High | High | Broad-based buying across all sizes |
| High | Low | Few large buys dominating (whale accumulation) |
| Low | High | Many small buys but large sells (distribution) |
| Low | Low | Broad-based selling |

## 4. Large Trade Ratio

**Formula:**
```
large_trade_ratio = whale_volume / total_volume
```

Where whale_volume includes trades > 50 SOL equivalent.

| Value | Interpretation |
|-------|---------------|
| > 0.50 | Whale-dominated market — follow the whales |
| 0.20 – 0.50 | Mixed market with significant whale presence |
| < 0.20 | Retail-dominated — less directional conviction |

### Large Trade Direction

More useful than just the ratio is the **direction** of large trades:

```python
def large_trade_direction(trades: list[dict], threshold_usd: float = 5000) -> dict:
    """Analyze direction of large trades."""
    large = [t for t in trades if t["volume_usd"] >= threshold_usd]
    if not large:
        return {"whale_buy_pct": 0.5, "whale_count": 0}
    buy_vol = sum(t["volume_usd"] for t in large if t["side"] == "buy")
    total_vol = sum(t["volume_usd"] for t in large)
    return {
        "whale_buy_pct": buy_vol / total_vol if total_vol > 0 else 0.5,
        "whale_count": len(large),
        "whale_volume_usd": total_vol,
    }
```

## 5. Volume Acceleration

**Formula:**
```
volume_acceleration = current_period_volume / previous_period_volume
```

| Value | Interpretation |
|-------|---------------|
| > 3.0 | Volume spike — significant event, check direction |
| 2.0 – 3.0 | Surging volume — breakout or breakdown likely |
| 1.0 – 2.0 | Growing interest |
| 0.5 – 1.0 | Declining interest |
| < 0.5 | Volume drying up — consolidation or abandonment |

**Important:** Always pair volume acceleration with direction. A 5x volume spike
that is 90% sells means something very different than 90% buys.

## 6. Unique Trader Count

**Formula:**
```
unique_traders = len(set(t["wallet"] for t in trades_in_period))
```

Track this over time to measure genuine interest growth:

```python
def unique_trader_trend(
    current_traders: int, previous_traders: int
) -> float:
    """Compute unique trader growth rate."""
    if previous_traders == 0:
        return 0.0
    return (current_traders - previous_traders) / previous_traders
```

| Trend | Interpretation |
|-------|---------------|
| > +0.20 | Rapidly growing community |
| 0 to +0.20 | Stable/growing |
| -0.20 to 0 | Declining interest |
| < -0.20 | Rapid exodus |

## 7. Token Velocity

**Formula:**
```
velocity = daily_traded_volume / circulating_supply
```

Where both are measured in token units (not USD).

| Velocity | Interpretation |
|----------|---------------|
| < 0.01 | Very low — strong holding behavior or dead token |
| 0.01 – 0.05 | Normal for established tokens |
| 0.05 – 0.20 | Active speculation |
| 0.20 – 1.00 | Extremely high turnover — likely wash trading or hype peak |
| > 1.00 | Almost certainly artificial volume |

## 8. Trade Size Entropy

**Formula:**
```
entropy = -sum(p * log2(p) for p in bucket_probabilities)
```

Where `bucket_probabilities` is the distribution of trades across size buckets.

| Entropy | Interpretation |
|---------|---------------|
| > 2.0 | Diverse trade sizes — organic market |
| 1.0 – 2.0 | Moderate diversity |
| < 1.0 | Concentrated sizes — possible bot/wash activity |

```python
import math

def trade_size_entropy(trades: list[dict], buckets: int = 10) -> float:
    """Compute Shannon entropy of trade size distribution."""
    if not trades:
        return 0.0
    sizes = [t["volume_usd"] for t in trades]
    min_s, max_s = min(sizes), max(sizes)
    if min_s == max_s:
        return 0.0
    width = (max_s - min_s) / buckets
    counts = [0] * buckets
    for s in sizes:
        idx = min(int((s - min_s) / width), buckets - 1)
        counts[idx] += 1
    total = len(sizes)
    probs = [c / total for c in counts if c > 0]
    return -sum(p * math.log2(p) for p in probs)
```

## Composite Momentum Score

Combine signals into a single score from -100 to +100:

### Component Weights

| Component | Weight | Range Mapped |
|-----------|--------|-------------|
| Buy Volume Ratio | 40% | 0–1 → -40 to +40 |
| Volume Acceleration | 20% | clamped → -20 to +20 |
| Whale Buy Direction | 25% | 0–1 → -25 to +25 |
| Unique Trader Trend | 15% | clamped → -15 to +15 |

### Formula

```python
score = (
    (buy_ratio - 0.5) * 80          # [-40, +40]
    + clamp((vol_accel - 1) * 20, -20, 20)  # [-20, +20]
    + (whale_buy_pct - 0.5) * 50     # [-25, +25]
    + clamp(trader_trend * 15, -15, 15)      # [-15, +15]
)
score = clamp(score, -100, 100)
```

### Score Interpretation

| Score | Label | Suggested Action |
|-------|-------|-----------------|
| +60 to +100 | Strong Accumulation | Consider entry if other factors align |
| +20 to +60 | Moderate Buying | Monitor for continuation |
| -20 to +20 | Neutral | No clear directional signal |
| -60 to -20 | Moderate Selling | Caution on new entries |
| -100 to -60 | Strong Distribution | Avoid entries, consider exits |

## Signal Freshness

Flow signals decay rapidly. Recommended maximum signal age:

| Signal | Max Useful Age |
|--------|---------------|
| Buy/sell ratio | 1 hour for scalping, 4 hours for swing |
| Net flow | 4 hours |
| Volume acceleration | Current period only |
| Unique traders | 24 hours |
| Token velocity | 24 hours |

Always display the timestamp of the most recent trade in the dataset so the user
knows how fresh the data is.

## Combining with Price Action

Flow signals are most powerful when confirmed by price:

- **Bullish divergence:** Increasing buy ratio + flat/declining price = accumulation
- **Bearish divergence:** Increasing sell ratio + flat/rising price = distribution
- **Confirmation:** Buy ratio and price both increasing = trend continuation
