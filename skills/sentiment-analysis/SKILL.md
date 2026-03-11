---
name: sentiment-analysis
description: Market sentiment extraction from social media, news, and on-chain data including mention velocity, fear and greed indices, and influencer tracking
---

# Sentiment Analysis

Extract and quantify market sentiment from social media, news feeds, and on-chain
data to identify crowd positioning and potential contrarian opportunities.

## When to Use This Skill

- Gauge crowd sentiment before entering or exiting a position
- Detect euphoria/panic extremes that precede reversals
- Monitor social mention velocity for early trend detection
- Track influencer activity around specific tokens
- Build composite sentiment scores for systematic strategies

## Core Concepts

### Sentiment Data Sources

| Source | Data Type | Access |
|--------|-----------|--------|
| Twitter/X | Post text, engagement, follower counts | API (paid tiers) |
| Reddit | Subreddit posts, comments, upvotes | Reddit API |
| Telegram | Channel messages, member counts | Bot API or scraping |
| Discord | Server activity, message volume | Bot integration |
| News | Headlines, article text | NewsAPI, RSS feeds |
| CoinGecko | Community stats, developer activity | Free API |
| Alternative.me | Fear & Greed Index | Free API |
| On-chain | Funding rates, exchange flows | Exchange APIs |

See `references/data_sources.md` for complete API details, rate limits, and access
patterns for each source.

### Sentiment Metrics

**Mention Velocity** — Rate of token mentions over time:

```python
mention_velocity = mentions_last_hour / baseline_hourly_mentions
# > 3.0 = trending, > 10.0 = viral
```

**Sentiment Polarity** — Positive vs negative tone:

```python
polarity = (positive_count - negative_count) / total_count
# Range: -1.0 (all negative) to +1.0 (all positive)
```

**Fear & Greed Index** — Composite market mood (0-100):

| Range | Label | Typical Signal |
|-------|-------|----------------|
| 0-24 | Extreme Fear | Potential accumulation zone |
| 25-44 | Fear | Below-average sentiment |
| 45-55 | Neutral | No strong directional bias |
| 56-74 | Greed | Above-average sentiment |
| 75-100 | Extreme Greed | Potential distribution zone |

**Social Volume** — Total mentions across platforms:

```python
social_volume_z = (current_volume - mean_30d) / std_30d
# z > 2.0 suggests unusual activity
```

### On-Chain Sentiment Proxies

On-chain data reveals what participants are doing, not just saying:

**Funding Rates** — Perpetual futures cost of carry:

```python
# Positive funding = longs pay shorts (bullish crowding)
# Negative funding = shorts pay longs (bearish crowding)
funding_sentiment = -1.0 * normalize(funding_rate, -0.1, 0.1)
# Inverted: high positive funding is contrarian bearish
```

**Long/Short Ratio** — Proportion of leveraged positions:

```python
ls_ratio = long_accounts / short_accounts
# > 2.0 = crowded long, < 0.5 = crowded short
ls_sentiment = -1.0 * normalize(ls_ratio, 0.5, 2.0)
```

**Exchange Flows** — Net deposits/withdrawals:

```python
net_flow = exchange_inflows - exchange_outflows
# Positive net flow (deposits) = bearish (selling pressure)
# Negative net flow (withdrawals) = bullish (accumulation)
flow_sentiment = -1.0 * normalize(net_flow, -threshold, threshold)
```

### Keyword-Based Sentiment Scoring

A simple, LLM-free approach using curated word lists:

```python
BULLISH_KEYWORDS = {
    "moon": 2, "bullish": 2, "pump": 1, "breakout": 2,
    "buy": 1, "long": 1, "accumulate": 2, "undervalued": 2,
    "gem": 1, "rocket": 1, "ath": 1, "rally": 2,
}
BEARISH_KEYWORDS = {
    "dump": 2, "bearish": 2, "crash": 2, "scam": 3,
    "rug": 3, "sell": 1, "short": 1, "overvalued": 2,
    "dead": 2, "rekt": 1, "ponzi": 3, "exit": 1,
}

def score_text(text: str) -> float:
    """Score text from -1.0 (bearish) to +1.0 (bullish)."""
    words = text.lower().split()
    bull_score = sum(BULLISH_KEYWORDS.get(w, 0) for w in words)
    bear_score = sum(BEARISH_KEYWORDS.get(w, 0) for w in words)
    total = bull_score + bear_score
    if total == 0:
        return 0.0
    return (bull_score - bear_score) / total
```

See `references/scoring_methods.md` for the full methodology, temporal decay
weighting, and composite score construction.

### Composite Sentiment Score

Combine multiple signals into a single score:

```python
def composite_sentiment(
    social_polarity: float,    # -1.0 to +1.0
    mention_velocity: float,   # 0 to inf
    fear_greed: int,           # 0 to 100
    funding_rate: float,       # -0.1 to +0.1
    weights: dict | None = None,
) -> float:
    """Compute weighted composite sentiment score (-100 to +100).

    Args:
        social_polarity: Average polarity of social mentions.
        mention_velocity: Current velocity vs baseline.
        fear_greed: Fear & Greed index reading.
        funding_rate: Current perpetual funding rate.
        weights: Optional custom weights.

    Returns:
        Composite score from -100 (extreme fear) to +100 (extreme greed).
    """
    w = weights or {
        "social": 0.30,
        "velocity": 0.15,
        "fear_greed": 0.30,
        "funding": 0.25,
    }
    # Normalize each component to -1.0 to +1.0
    s_social = social_polarity
    s_velocity = min(mention_velocity / 10.0, 1.0)  # Cap at 10x
    s_fg = (fear_greed - 50) / 50.0  # 0-100 -> -1 to +1
    s_funding = -10.0 * funding_rate  # Contrarian: high funding = bearish
    s_funding = max(-1.0, min(1.0, s_funding))

    raw = (
        w["social"] * s_social
        + w["velocity"] * s_velocity
        + w["fear_greed"] * s_fg
        + w["funding"] * s_funding
    )
    return round(raw * 100, 1)
```

### Contrarian Signals

Extreme sentiment readings often precede reversals:

| Condition | Interpretation |
|-----------|----------------|
| Composite < -70 | Extreme fear — historically a buying zone |
| Composite > +70 | Extreme greed — historically a selling zone |
| Velocity > 10x + polarity > 0.6 | Euphoric spike — fade potential |
| Velocity > 10x + polarity < -0.6 | Panic spike — bounce potential |
| Funding > 0.05% + LS ratio > 2.0 | Crowded long — liquidation risk |
| Funding < -0.05% + LS ratio < 0.5 | Crowded short — squeeze risk |

**Key principle**: Sentiment is most useful at extremes. Neutral readings
(composite between -30 and +30) have low predictive value.

### Influencer Tracking

Monitor high-follower accounts for early signal detection:

```python
def influencer_signal(
    posts: list[dict],
    min_followers: int = 50_000,
    lookback_hours: int = 24,
) -> dict:
    """Detect influencer activity around a token.

    Args:
        posts: List of posts with 'followers', 'timestamp', 'sentiment'.
        min_followers: Minimum follower count to qualify as influencer.
        lookback_hours: Time window in hours.

    Returns:
        Dict with influencer_count, avg_sentiment, total_reach.
    """
    cutoff = time.time() - (lookback_hours * 3600)
    relevant = [
        p for p in posts
        if p["followers"] >= min_followers and p["timestamp"] >= cutoff
    ]
    if not relevant:
        return {"influencer_count": 0, "avg_sentiment": 0.0, "total_reach": 0}
    return {
        "influencer_count": len(relevant),
        "avg_sentiment": sum(p["sentiment"] for p in relevant) / len(relevant),
        "total_reach": sum(p["followers"] for p in relevant),
    }
```

## Integration With Other Skills

| Skill | Integration Point |
|-------|------------------|
| `position-sizing` | Reduce size in extreme greed, increase in extreme fear |
| `risk-management` | Tighten stops when sentiment diverges from price |
| `regime-detection` | Sentiment confirms or contradicts regime classification |
| `feature-engineering` | Sentiment metrics as ML features |
| `signal-classification` | Sentiment as input to signal scoring models |
| `whale-tracking` | Combine whale activity with social sentiment |
| `token-holder-analysis` | Holder growth/decline as sentiment proxy |

## Practical Workflow

```
1. Fetch fear/greed index          → Market-wide mood
2. Pull social data for token      → Token-specific sentiment
3. Score text with keyword method  → Polarity scores
4. Compute mention velocity        → Trending detection
5. Check on-chain proxies          → Funding, flows
6. Calculate composite score       → Single decision input
7. Flag contrarian signals         → Extreme readings
8. Integrate with position sizing  → Adjust allocation
```

## Limitations and Warnings

- **Sentiment is noisy.** Individual readings are unreliable — use trends and extremes.
- **Social data is gameable.** Bot activity can inflate mention counts.
- **Keyword scoring is crude.** It misses sarcasm, context, and nuance.
- **Lag exists.** By the time sentiment is measurable, price may have moved.
- **Not financial advice.** Sentiment data is for informational and analytical purposes only.
- **API access varies.** Twitter/X API pricing has changed frequently. Budget accordingly.
- **Survivorship bias.** Tokens that go to zero stop being discussed — absence of mentions is also a signal.

## Files

### References
- `references/data_sources.md` — API details, rate limits, and access patterns for all sentiment data sources
- `references/scoring_methods.md` — Keyword lists, composite scoring methodology, temporal decay, contrarian logic

### Scripts
- `scripts/sentiment_scanner.py` — Fetches live sentiment data from free APIs, computes composite scores, flags contrarian signals
- `scripts/keyword_sentiment.py` — Standalone keyword-based text sentiment analyzer with synthetic demo data
