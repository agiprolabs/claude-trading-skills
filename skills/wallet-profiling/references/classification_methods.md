# Wallet Classification Methods

Algorithms for categorizing Solana wallets by trading style, size, behavior type, and focus area.

## Style Classification (Hold Time)

Classify based on the **median hold time** of all closed trades. Use median rather than mean to avoid skew from forgotten positions.

### Algorithm

```python
def classify_style(hold_times_minutes: list[float]) -> str:
    """Classify wallet trading style from hold time distribution.

    Args:
        hold_times_minutes: List of hold durations in minutes for closed trades.

    Returns:
        Style label: sniper, scalper, day_trader, swing, or holder.
    """
    if not hold_times_minutes:
        return "unknown"

    import statistics
    median = statistics.median(hold_times_minutes)

    if median < 5:
        return "sniper"
    elif median < 60:
        return "scalper"
    elif median < 1440:       # 24 hours
        return "day_trader"
    elif median < 10080:      # 7 days
        return "swing"
    else:
        return "holder"
```

### Hold Time Distribution Analysis

Beyond the median, examine the full distribution shape:

| Distribution Shape | Interpretation |
|-------------------|----------------|
| Tight unimodal (low std) | Consistent strategy, single style |
| Bimodal | Two distinct strategies (e.g., scalp + swing) |
| Right-skewed | Primarily fast trades with occasional holds |
| Uniform/flat | No clear strategy, opportunistic |

```python
def analyze_hold_distribution(hold_times: list[float]) -> dict:
    """Analyze the shape of hold time distribution."""
    import statistics
    if len(hold_times) < 5:
        return {"shape": "insufficient_data"}

    median = statistics.median(hold_times)
    mean = statistics.mean(hold_times)
    stdev = statistics.stdev(hold_times)
    cv = stdev / mean if mean > 0 else 0

    return {
        "median_minutes": round(median, 1),
        "mean_minutes": round(mean, 1),
        "stdev_minutes": round(stdev, 1),
        "cv": round(cv, 2),
        "skew_direction": "right" if mean > median * 1.5 else "left" if mean < median * 0.67 else "symmetric",
        "consistency": "high" if cv < 0.5 else "medium" if cv < 1.0 else "low",
    }
```

## Size Classification (Trade Size)

Based on **median trade size in SOL** across all buy transactions.

```python
def classify_size(trade_sizes_sol: list[float]) -> str:
    """Classify wallet by typical trade size.

    Args:
        trade_sizes_sol: List of trade sizes in SOL.

    Returns:
        Size tier: whale, large, medium, or small.
    """
    if not trade_sizes_sol:
        return "unknown"

    import statistics
    median = statistics.median(trade_sizes_sol)

    if median > 100:
        return "whale"
    elif median > 10:
        return "large"
    elif median > 1:
        return "medium"
    else:
        return "small"
```

### Size Consistency

Check whether the wallet uses consistent sizing or varies dramatically:

```python
def sizing_consistency(trade_sizes: list[float]) -> str:
    """Assess how consistent trade sizing is."""
    import statistics
    if len(trade_sizes) < 5:
        return "insufficient_data"
    cv = statistics.stdev(trade_sizes) / statistics.mean(trade_sizes)
    if cv < 0.3:
        return "very_uniform"     # Likely bot or fixed-size strategy
    elif cv < 0.6:
        return "moderate"         # Adaptive but disciplined
    elif cv < 1.0:
        return "variable"         # Opportunistic sizing
    else:
        return "highly_variable"  # Erratic or conviction-based
```

## Bot vs. Human Detection

### Inter-Trade Interval Analysis

The primary signal for bot detection is the **coefficient of variation (CV)** of time gaps between consecutive trades.

```python
def bot_probability(trade_timestamps: list[float]) -> float:
    """Estimate probability that a wallet is operated by a bot.

    Uses inter-trade interval regularity as the primary signal.
    CV < 0.3 is highly suggestive of automated execution.

    Args:
        trade_timestamps: Unix timestamps of trades, sorted ascending.

    Returns:
        Probability from 0.0 (definitely human) to 1.0 (definitely bot).
    """
    if len(trade_timestamps) < 10:
        return 0.0  # Insufficient data

    import statistics

    intervals = [
        trade_timestamps[i + 1] - trade_timestamps[i]
        for i in range(len(trade_timestamps) - 1)
    ]
    intervals = [i for i in intervals if i > 0]  # Remove duplicates
    if len(intervals) < 5:
        return 0.0

    mean_interval = statistics.mean(intervals)
    std_interval = statistics.stdev(intervals)
    cv = std_interval / mean_interval if mean_interval > 0 else 999

    # Score components
    timing_score = max(0, 1.0 - cv / 0.5)  # Low CV = more bot-like

    # Check for round-number intervals (e.g., exactly 60s, 300s)
    round_count = sum(1 for i in intervals if i % 10 < 1 or i % 10 > 9)
    round_pct = round_count / len(intervals)
    round_score = round_pct  # Higher = more bot-like

    # 24/7 activity (humans sleep, bots don't)
    from datetime import datetime, timezone
    hours = [datetime.fromtimestamp(t, tz=timezone.utc).hour for t in trade_timestamps]
    unique_hours = len(set(hours))
    hour_coverage = unique_hours / 24
    hour_score = hour_coverage  # Trading across all hours = more bot-like

    # Weighted combination
    probability = (timing_score * 0.5 + round_score * 0.25 + hour_score * 0.25)
    return round(min(1.0, max(0.0, probability)), 2)
```

### Additional Bot Indicators

| Indicator | Bot Signal | Human Signal |
|-----------|-----------|-------------|
| Trade timing CV | < 0.3 | > 0.8 |
| Active hours per day | > 20 | 8–16 |
| Weekend activity | Same as weekday | Reduced |
| Size variance | Very low (CV < 0.2) | Moderate (CV 0.4–1.0) |
| Response to price moves | Immediate (< 2 blocks) | Delayed (minutes) |

## Focus Area Detection

Classify wallets by which protocols and token types they interact with most.

```python
def classify_focus(
    token_types: list[str],
    programs_used: list[str],
) -> str:
    """Classify wallet focus area based on interaction patterns.

    Args:
        token_types: List like ["pumpfun", "raydium", "pumpfun", "orca", ...].
        programs_used: List of program IDs or labels interacted with.

    Returns:
        Focus label: pumpfun_specialist, dex_trader, defi_farmer,
                     nft_trader, or multi_strategy.
    """
    if not token_types:
        return "unknown"

    total = len(token_types)
    from collections import Counter
    type_counts = Counter(token_types)

    pumpfun_pct = type_counts.get("pumpfun", 0) / total

    program_counts = Counter(programs_used)
    lp_programs = {"raydium_amm", "orca_whirlpool", "meteora_dlmm"}
    lp_interactions = sum(program_counts.get(p, 0) for p in lp_programs)
    lp_pct = lp_interactions / max(len(programs_used), 1)

    nft_programs = {"metaplex", "tensor", "magic_eden"}
    nft_interactions = sum(program_counts.get(p, 0) for p in nft_programs)
    nft_pct = nft_interactions / max(len(programs_used), 1)

    if pumpfun_pct > 0.7:
        return "pumpfun_specialist"
    elif nft_pct > 0.5:
        return "nft_trader"
    elif lp_pct > 0.4:
        return "defi_farmer"
    elif pumpfun_pct < 0.3:
        return "dex_trader"
    else:
        return "multi_strategy"
```

## Composite Classification

Combine all classifiers into a single wallet profile:

```python
def build_profile(
    hold_times: list[float],
    trade_sizes: list[float],
    timestamps: list[float],
    token_types: list[str],
    programs: list[str],
) -> dict:
    """Build a complete wallet classification profile."""
    return {
        "style": classify_style(hold_times),
        "size_tier": classify_size(trade_sizes),
        "bot_probability": bot_probability(timestamps),
        "focus": classify_focus(token_types, programs),
        "hold_distribution": analyze_hold_distribution(hold_times),
        "sizing_consistency": sizing_consistency(trade_sizes),
        "trade_count": len(hold_times),
    }
```

## Confidence Levels

| Trade Count | Confidence | Recommendation |
|-------------|-----------|----------------|
| < 10 | Very Low | Do not classify |
| 10–29 | Low | Tentative classification only |
| 30–99 | Moderate | Reasonable classification |
| 100–499 | High | Reliable classification |
| 500+ | Very High | Strong statistical basis |
