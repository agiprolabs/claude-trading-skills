# Exposure Limits

Detailed position and portfolio exposure constraints for crypto trading risk management.

## Single Position Limits

### By Token Type

Token classification determines maximum position size as a percentage of total account value:

| Token Type | Examples | Max Position | Rationale |
|---|---|---|---|
| Blue chip | SOL, ETH, BTC | 10% | High liquidity, lower rug risk |
| Large cap | RAY, JUP, BONK | 7% | Established but more volatile |
| Mid cap | Top 100 by mcap | 5% | Moderate liquidity risk |
| Small cap | Top 500 by mcap | 2% | Significant liquidity/rug risk |
| Micro cap | Sub-$10M mcap | 1% | Very high risk |
| PumpFun/meme | New launches | 0.5% | Assume potential 100% loss |

### By Strategy Type

Different strategies carry different risk profiles:

| Strategy | Max Position | Rationale |
|---|---|---|
| Trend following | 5% | Wider stops, longer holds |
| Mean reversion | 3% | Can gap through stop levels |
| Momentum/scalp | 2% | High frequency, errors compound |
| Breakout | 3% | False breakouts are common |
| PumpFun snipe | 0.5% | Binary outcome expected |

### By Confidence Level

Scale position size with conviction, but never exceed token-type limits:

| Confidence | Size Multiplier | Criteria |
|---|---|---|
| High | 100% of allowed max | Multiple confirming signals, strong setup |
| Medium | 50% of allowed max | Decent setup, some conflicting signals |
| Low | 25% of allowed max | Marginal setup, taking for diversification |

**Example**: High confidence on a mid-cap token = 5% × 100% = 5% position. Low confidence on same = 5% × 25% = 1.25%.

## Portfolio-Level Limits

### Total Exposure

Percentage of total account value deployed in open positions:

| Market Condition | Max Exposure | Cash Reserve |
|---|---|---|
| Strong trend, low vol | 80% | 20% |
| Normal conditions | 60% | 40% |
| High volatility | 40% | 60% |
| Drawdown >10% | 30% | 70% |
| Drawdown >15% | 20% | 80% |
| Circuit breaker active | 0% (existing only) | 100% |

### Cash Reserve Purpose

The cash reserve serves multiple functions:
1. **Opportunity capital**: Ability to take advantage of sudden setups
2. **Margin buffer**: Prevents forced liquidations on leveraged positions
3. **Psychological comfort**: Reduces pressure to exit positions prematurely
4. **Drawdown cushion**: Limits portfolio drawdown speed

### Maximum Concurrent Positions

| Account Size (SOL) | Max Positions | Rationale |
|---|---|---|
| <10 | 3 | Focus, meaningful size per trade |
| 10–50 | 5 | Moderate diversification |
| 50–200 | 7 | Balanced diversification |
| 200–1000 | 10 | Full diversification |
| >1000 | 15 | Diminishing returns beyond this |

### Sector Concentration

Maximum allocation to any single narrative or sector:

| Sector | Max Allocation |
|---|---|
| DeFi protocols | 30% |
| Meme/culture tokens | 15% |
| Infrastructure/L1/L2 | 30% |
| Gaming/NFT-adjacent | 20% |
| AI tokens | 20% |
| Stablecoins (non-reserve) | 10% |

## Correlation Management

### The Correlation Problem

During normal markets, crypto assets may show moderate correlation (0.3–0.5). During sell-offs, correlations spike to 0.7–0.9+. A "diversified" portfolio of 10 crypto tokens may behave like 2–3 independent positions in a crash.

### Effective Diversification

**What does NOT diversify well**:
- Multiple meme tokens (all driven by same sentiment)
- Multiple DeFi tokens (correlated with DeFi TVL)
- Multiple tokens on the same chain (correlated with chain activity)
- Long-only positions across any crypto tokens (all correlate with BTC)

**What DOES diversify**:
- Different strategies: trend + mean-reversion + market-neutral
- Different timeframes: scalp + swing + position
- Different exposures: long + short (when available)
- Cash reserves (zero correlation by definition)

### Correlation Buckets

Group positions into correlation buckets and apply limits per bucket:

| Bucket | Contents | Max Allocation |
|---|---|---|
| BTC-correlated | BTC, SOL, ETH, major L1s | 30% |
| DeFi | DEX tokens, lending, yield | 20% |
| Meme | All meme/culture tokens | 15% |
| Stablecoin yield | LP positions, lending | 20% |
| Uncorrelated | Market-neutral strategies | No limit |

### Calculating Portfolio Correlation

```python
import numpy as np

def portfolio_correlation(returns_matrix: np.ndarray) -> float:
    """Average pairwise correlation of portfolio assets.

    Args:
        returns_matrix: N×T matrix (N assets, T time periods).

    Returns:
        Average pairwise correlation coefficient.
    """
    corr = np.corrcoef(returns_matrix)
    n = corr.shape[0]
    # Extract upper triangle (excluding diagonal)
    upper = corr[np.triu_indices(n, k=1)]
    return float(np.mean(upper))
```

## Dynamic Limit Adjustments

### Tightening During Drawdowns

When the portfolio is in drawdown, tighten all limits proportionally:

```python
def adjusted_limit(base_limit: float, drawdown: float) -> float:
    """Reduce limits during drawdowns.

    Args:
        base_limit: Normal limit (e.g., 0.05 for 5%).
        drawdown: Current drawdown as fraction (e.g., 0.10 for 10%).

    Returns:
        Adjusted limit, reduced proportionally.
    """
    if drawdown < 0.05:
        return base_limit
    elif drawdown < 0.10:
        return base_limit * 0.75
    elif drawdown < 0.15:
        return base_limit * 0.50
    else:
        return base_limit * 0.25
```

### Widening During Strong Performance

Expand limits cautiously when the portfolio is performing well:

- Only expand after 20+ days of positive equity curve slope
- Maximum expansion: 125% of base limits (never more)
- Revert to base limits immediately if drawdown begins
- Never expand PumpFun or micro-cap limits regardless of performance

### Seasonal Adjustments

Historical crypto volatility patterns suggest:
- **Reduce exposure**: During major token unlock events, regulatory announcements
- **Standard exposure**: Normal market conditions
- **Increase caution**: Holiday periods (low liquidity), end-of-quarter (fund rebalancing)

## Implementation Checklist

- [ ] Define token-type classification for each traded asset
- [ ] Set strategy-specific position limits
- [ ] Configure total exposure limits for current market regime
- [ ] Set up sector tracking and concentration alerts
- [ ] Calculate correlation buckets and apply bucket limits
- [ ] Implement dynamic adjustment based on drawdown level
- [ ] Review and update limits monthly
