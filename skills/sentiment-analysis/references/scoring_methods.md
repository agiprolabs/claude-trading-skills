# Sentiment Scoring Methods

Comprehensive reference for keyword-based scoring, composite indices, temporal
decay, and contrarian signal detection.

## Keyword-Based Sentiment

### Approach

Score text by matching tokens against curated positive/negative word lists
weighted by intensity. No ML model required — runs anywhere with zero
dependencies.

### Crypto-Specific Word Lists

**Bullish Keywords** (word: weight):

```
moon: 2, bullish: 2, pump: 1, breakout: 2, buy: 1, long: 1,
accumulate: 2, undervalued: 2, gem: 1, rocket: 1, ath: 1, rally: 2,
surge: 2, soar: 2, lambo: 1, diamond: 1, hodl: 1, dip: 1 (as in "buy the dip"),
alpha: 1, gainz: 1, moonshot: 2, parabolic: 2, reversal: 1, recovery: 1,
bottom: 1, support: 1, accumulation: 2, institutional: 1, adoption: 2
```

**Bearish Keywords** (word: weight):

```
dump: 2, bearish: 2, crash: 2, scam: 3, rug: 3, sell: 1, short: 1,
overvalued: 2, dead: 2, rekt: 1, ponzi: 3, exit: 1, fraud: 3,
bubble: 2, collapse: 2, liquidation: 2, capitulation: 2, resistance: 1,
distribution: 1, top: 1, overbought: 1, bagholding: 2, worthless: 3,
hack: 3, exploit: 3, insolvent: 3, bankrupt: 3, warning: 2
```

### Scoring Formula

```python
def keyword_score(text: str, bullish: dict, bearish: dict) -> float:
    """Score text from -1.0 (bearish) to +1.0 (bullish).

    Formula: (bull_sum - bear_sum) / (bull_sum + bear_sum)
    Returns 0.0 if no keywords matched.
    """
    words = text.lower().split()
    bull = sum(bullish.get(w, 0) for w in words)
    bear = sum(bearish.get(w, 0) for w in words)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total
```

### Limitations

- Misses sarcasm: "Great, another rug pull" scores partially bullish
- Context-blind: "not bullish" scores as bullish
- Language-specific: English only without translation
- Gameable: Bots can flood channels with keyword-loaded posts

### Mitigation Strategies

- Require minimum text length (> 10 words) to reduce noise
- Weight by engagement: higher-engagement posts count more
- Apply author reputation scoring (account age, follower count)
- Use bigrams for negation detection: "not bullish" -> bearish

## Mention Velocity

### Definition

Rate of token mentions compared to a historical baseline:

```
velocity = mentions_current_period / baseline_mentions_per_period
```

### Baseline Computation

Use a 30-day rolling average as baseline:

```python
def compute_velocity(
    current_mentions: int,
    period_hours: float,
    daily_baseline: float,
) -> float:
    """Compute mention velocity as multiple of baseline.

    Args:
        current_mentions: Mentions observed in the current period.
        period_hours: Length of current observation period in hours.
        daily_baseline: 30-day average daily mentions.

    Returns:
        Velocity as a multiple of baseline (1.0 = normal).
    """
    hourly_baseline = daily_baseline / 24.0
    if hourly_baseline <= 0:
        return 0.0
    hourly_current = current_mentions / max(period_hours, 0.1)
    return hourly_current / hourly_baseline
```

### Interpretation

| Velocity | Meaning |
|----------|---------|
| 0.0-0.5 | Below normal — low interest |
| 0.5-1.5 | Normal range |
| 1.5-3.0 | Elevated — growing interest |
| 3.0-10.0 | Trending — significant event |
| > 10.0 | Viral — major event or coordinated activity |

### Combined Velocity + Polarity Signals

| Velocity | Polarity | Signal |
|----------|----------|--------|
| > 5x | > +0.5 | Euphoria — potential top |
| > 5x | < -0.5 | Panic — potential bottom |
| > 5x | Near 0 | Controversy — uncertain |
| < 0.3x | Any | Forgotten — check if project is dead |

## Fear & Greed Index

### Alternative.me Composition

The crypto Fear & Greed Index uses these components:

| Component | Weight | Source |
|-----------|--------|--------|
| Volatility | 25% | Current vs 30/90-day avg |
| Market Momentum/Volume | 25% | Current vs 30/90-day avg |
| Social Media | 15% | Twitter/Reddit mentions + engagement |
| Surveys | 15% | Community polls (when available) |
| Bitcoin Dominance | 10% | BTC market cap share |
| Google Trends | 10% | Search volume for crypto terms |

### Building a Custom Fear/Greed Score

For token-specific sentiment, build a custom index:

```python
def custom_fear_greed(
    price_vs_sma30: float,    # price / SMA(30) - 1.0
    volume_vs_avg: float,     # volume / avg_volume(30)
    social_polarity: float,   # -1.0 to +1.0
    funding_rate: float,      # perpetual funding rate
    holder_growth_pct: float, # 7d holder count change %
) -> int:
    """Compute custom fear/greed index (0-100).

    Each component maps to 0-100, then weighted average.
    """
    # Price momentum: -20% below SMA = 0, +20% above = 100
    c_price = min(100, max(0, (price_vs_sma30 + 0.2) / 0.4 * 100))

    # Volume: 0.5x avg = 0, 2.0x avg = 100
    c_volume = min(100, max(0, (volume_vs_avg - 0.5) / 1.5 * 100))

    # Social: -1.0 = 0, +1.0 = 100
    c_social = (social_polarity + 1.0) / 2.0 * 100

    # Funding: -0.05% = 0 (fear), +0.05% = 100 (greed)
    c_funding = min(100, max(0, (funding_rate + 0.0005) / 0.001 * 100))

    # Holder growth: -5% = 0, +5% = 100
    c_holders = min(100, max(0, (holder_growth_pct + 5) / 10 * 100))

    score = int(
        0.25 * c_price
        + 0.20 * c_volume
        + 0.25 * c_social
        + 0.15 * c_funding
        + 0.15 * c_holders
    )
    return min(100, max(0, score))
```

## Composite Sentiment Score

### Construction

Combine all available signals into a single -100 to +100 score:

```
composite = w1 * social_polarity_norm
          + w2 * velocity_norm
          + w3 * fear_greed_norm
          + w4 * funding_norm
```

### Default Weights

| Component | Weight | Rationale |
|-----------|--------|-----------|
| Social polarity | 0.30 | Direct sentiment measure |
| Fear/greed index | 0.30 | Broad market context |
| Funding rate | 0.25 | Reveals leveraged positioning |
| Mention velocity | 0.15 | Activity level indicator |

### Normalization

All components must be normalized to the -1.0 to +1.0 range before weighting:

- Social polarity: already -1.0 to +1.0
- Velocity: `min(velocity / 10.0, 1.0)` (caps at 10x baseline)
- Fear/greed: `(value - 50) / 50` (0-100 -> -1 to +1)
- Funding: `-10.0 * rate`, clamped to [-1, 1] (contrarian: inverted)

## Temporal Decay

Recent data points carry more weight than older ones:

```python
def temporal_weight(age_hours: float, half_life_hours: float = 6.0) -> float:
    """Exponential decay weight based on data age.

    Args:
        age_hours: How old the data point is in hours.
        half_life_hours: Hours until weight drops to 50%.

    Returns:
        Weight from 0.0 to 1.0.
    """
    import math
    return math.exp(-0.693 * age_hours / half_life_hours)
```

| Age (hours) | Weight (6h half-life) |
|-------------|----------------------|
| 0 | 1.000 |
| 3 | 0.707 |
| 6 | 0.500 |
| 12 | 0.250 |
| 24 | 0.063 |
| 48 | 0.004 |

## Contrarian Signal Detection

### Rules

1. **Extreme Fear Buy Signal**: Composite < -70 AND velocity > 5x
   - Crowd is panicking — historically precedes bounces
2. **Extreme Greed Sell Signal**: Composite > +70 AND velocity > 5x
   - Crowd is euphoric — historically precedes corrections
3. **Funding Divergence**: Funding > 0.05% but price declining
   - Longs trapped — liquidation cascade risk
4. **Silent Accumulation**: Velocity < 0.3x but holder count increasing
   - Smart money accumulating while retail is disinterested

### Confidence Levels

| Signals Aligned | Confidence |
|----------------|------------|
| 1 | Low — single indicator, could be noise |
| 2 | Moderate — worth monitoring |
| 3+ | High — strong contrarian setup |

### Historical Context

Extreme Fear & Greed readings (< 10 or > 90) have historically occurred
during 5-10% of trading days. The signal is valuable precisely because
it is rare. Do not lower thresholds to generate more signals.
