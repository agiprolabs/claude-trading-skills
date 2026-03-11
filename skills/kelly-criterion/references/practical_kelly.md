# Kelly Criterion — Practical Application Guide

## Estimating Edge from Trading Data

### Required Metrics

From a set of completed trades (P&L values):

```python
trades = [0.5, -0.3, 0.8, -0.2, 0.4, -0.35, ...]  # P&L per trade

wins = [t for t in trades if t > 0]
losses = [t for t in trades if t < 0]

win_rate = len(wins) / len(trades)               # p
avg_win = sum(wins) / len(wins)                   # average win
avg_loss = abs(sum(losses) / len(losses))         # average loss (positive)
payoff_ratio = avg_win / avg_loss                 # b
edge = win_rate * payoff_ratio - (1 - win_rate)   # expected value per unit
```

### Minimum Sample Sizes

| Sample Size | Reliability | Recommendation |
|------------|-------------|----------------|
| < 20 trades | Very unreliable | Do not use Kelly at all |
| 20-50 trades | Poor | 0.1x Kelly maximum, if any |
| 50-100 trades | Moderate | 0.25x Kelly |
| 100-200 trades | Good | 0.25x - 0.5x Kelly |
| 200+ trades | Strong | Up to 0.5x Kelly |

Never use full Kelly regardless of sample size.

---

## Confidence Intervals for Win Rate

### Wilson Score Interval

The Wilson interval is preferred over the naive interval for proportions because it handles edge cases (win rate near 0 or 1, small samples) correctly.

```python
import math

def wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for win rate using Wilson score.

    Args:
        wins: Number of winning trades.
        total: Total number of trades.
        z: Z-score (1.96 for 95%, 1.645 for 90%).

    Returns:
        (lower_bound, upper_bound) of win rate.
    """
    if total == 0:
        return (0.0, 1.0)
    p = wins / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    lower = (centre - spread) / denominator
    upper = (centre + spread) / denominator
    return (max(0.0, lower), min(1.0, upper))
```

### Conservative Kelly

Use the **lower bound** of the confidence interval for win rate when calculating Kelly. This automatically adjusts for sample size: smaller samples produce wider intervals, leading to more conservative sizing.

```python
def conservative_kelly(wins: int, total: int, payoff_ratio: float) -> float:
    """Kelly fraction using conservative win rate estimate."""
    lower, _ = wilson_interval(wins, total)
    edge = lower * payoff_ratio - (1 - lower)
    if edge <= 0:
        return 0.0
    return edge / payoff_ratio
```

---

## Common Edge Values in Crypto Trading

| Edge Range | Classification | Typical Sources |
|-----------|---------------|-----------------|
| < 0 | Negative edge | Poor strategy, overtransacting |
| 0 - 0.02 | No meaningful edge | Fees and slippage consume it |
| 0.02 - 0.05 | Weak edge | Marginal strategies, crowded signals |
| 0.05 - 0.10 | Moderate edge | Solid momentum or mean reversion |
| 0.10 - 0.20 | Good edge | Well-tuned niche strategies |
| 0.20 - 0.50 | Excellent edge | Rare; typically temporary or informational |
| > 0.50 | Suspicious | Almost certainly overfitting or survivorship bias |

If your calculated edge exceeds 0.30, scrutinize your methodology before trusting it. Common causes of inflated edge:
- Survivorship bias (only analyzing tokens that still exist)
- Lookahead bias (using future information in backtest)
- Small sample size with lucky streak
- Not accounting for slippage and fees

---

## Fractional Kelly Recommendations

| Fraction | Growth (% of optimal) | Drawdown (% of full Kelly) | When to Use |
|----------|----------------------|---------------------------|------------|
| 0.10x | ~19% | ~10% | Brand new strategy, < 30 trades, very uncertain |
| 0.15x | ~28% | ~15% | PumpFun/meme tokens, regime uncertainty |
| 0.25x | ~44% | ~25% | Standard for moderate confidence (50-100 trades) |
| 0.33x | ~55% | ~33% | Good track record, 100+ trades |
| 0.50x | ~75% | ~50% | High confidence, 200+ trades, consistent Sharpe |
| 0.75x | ~94% | ~75% | Rarely justified in practice |
| 1.00x | 100% | 100% | Never recommended |

---

## Worked Examples

### Example 1: Moderate Edge Strategy

**Data**: 120 trades, 66 wins, 54 losses. Average win: 0.45 SOL. Average loss: 0.30 SOL.

```
win_rate = 66 / 120 = 0.55
payoff_ratio = 0.45 / 0.30 = 1.50
edge = 0.55 * 1.50 - 0.45 = 0.825 - 0.45 = 0.375

kelly_full = 0.375 / 1.50 = 0.25 (25%)

# Conservative: Wilson lower bound
wilson_lower(66, 120) ≈ 0.460
conservative_kelly = (0.460 * 1.50 - 0.540) / 1.50 = 0.15 / 1.50 = 0.10

# Recommended fractions (of point-estimate Kelly)
kelly_quarter = 0.25 * 0.25 = 6.25%
kelly_half = 0.50 * 0.25 = 12.5%

# With 100 SOL account:
position_quarter = 6.25 SOL per trade
position_half = 12.5 SOL per trade
```

**Recommendation**: Use 6-12% per trade (0.25x-0.50x Kelly). The 120-trade sample gives moderate confidence.

### Example 2: High Win Rate, Low Payoff

**Data**: 200 trades, 120 wins, 80 losses. Average win: 0.20 SOL. Average loss: 0.25 SOL.

```
win_rate = 120 / 200 = 0.60
payoff_ratio = 0.20 / 0.25 = 0.80
edge = 0.60 * 0.80 - 0.40 = 0.48 - 0.40 = 0.08

kelly_full = 0.08 / 0.80 = 0.10 (10%)

kelly_quarter = 2.5%
kelly_half = 5.0%
```

**Recommendation**: Use 2.5-5% per trade. The edge is real but small; larger sizing risks ruin from inevitable losing streaks.

### Example 3: Low Win Rate, High Payoff (Trend Following)

**Data**: 80 trades, 32 wins, 48 losses. Average win: 1.50 SOL. Average loss: 0.50 SOL.

```
win_rate = 32 / 80 = 0.40
payoff_ratio = 1.50 / 0.50 = 3.00
edge = 0.40 * 3.00 - 0.60 = 1.20 - 0.60 = 0.60

kelly_full = 0.60 / 3.00 = 0.20 (20%)

# Conservative with Wilson lower bound
wilson_lower(32, 80) ≈ 0.298
conservative_edge = 0.298 * 3.0 - 0.702 = 0.192
conservative_kelly = 0.192 / 3.0 = 0.064

kelly_quarter = 0.25 * 0.20 = 5.0%
kelly_half = 0.50 * 0.20 = 10.0%
```

**Recommendation**: Use 5-6% per trade. Despite the apparently high edge, the 80-trade sample with 40% win rate has wide confidence intervals. Conservative Kelly (6.4%) aligns with quarter Kelly (5.0%).

---

## Kelly Danger Zones

### Kelly > 50%

If your calculation produces a Kelly fraction above 50%, something is almost certainly wrong:
- Your win rate estimate is inflated (survivorship bias, small sample)
- Your payoff ratio is inflated (outlier winners dominating)
- You are not accounting for transaction costs

**Action**: Cap at 25% before applying fraction. Investigate your data.

### Negative Kelly

A negative Kelly fraction means your strategy has negative expected value. You lose money on average.

**Action**: Stop trading this strategy. Investigate why. Common causes:
- Transaction costs exceed gross edge
- Strategy no longer works (regime change)
- Implementation differs from backtest

### Monotonically Increasing Kelly

If your rolling Kelly fraction keeps growing over time, be suspicious:
- Your recent trades may be in an unusually favorable regime
- You may be experiencing a lucky streak
- The market may be about to revert

**Action**: Use the minimum of recent and long-term Kelly, not the maximum.

### Kelly Oscillating Wildly

If Kelly swings dramatically between recalculations (e.g., 5% one month, 20% the next):
- Your sample size is too small for stable estimates
- The underlying edge is not stationary

**Action**: Use longer lookback windows, apply heavier fractional Kelly (0.1x-0.25x), or average multiple estimates.

---

## Recalculation Frequency

| Trading Frequency | Kelly Recalculation | Rationale |
|------------------|-------------------|-----------|
| Many trades/day | Weekly | Fast data accumulation |
| Few trades/day | Bi-weekly to monthly | Need time to accumulate samples |
| Few trades/week | Monthly to quarterly | Very slow data accumulation |

When recalculating:
1. Use a rolling window (last 100-200 trades), not all-time
2. Compare new Kelly to previous — large jumps warrant investigation
3. Phase in changes gradually (blend old and new over 1-2 weeks)

---

## Transaction Cost Adjustment

Always subtract estimated round-trip costs from your edge before computing Kelly:

```python
def kelly_with_costs(win_rate: float, payoff_ratio: float,
                     cost_per_trade: float) -> float:
    """Kelly fraction adjusted for transaction costs.

    Args:
        win_rate: Probability of winning.
        payoff_ratio: Average win / average loss.
        cost_per_trade: Round-trip cost as fraction of position
                        (e.g., 0.005 for 0.5%).
    """
    # Adjust payoff ratio and win rate for costs
    # Costs reduce wins and increase losses
    adj_payoff = (payoff_ratio - cost_per_trade) / (1 + cost_per_trade)
    edge = win_rate * adj_payoff - (1 - win_rate)
    if edge <= 0:
        return 0.0
    return edge / adj_payoff
```

Typical round-trip costs in Solana DeFi:
- DEX swap fees: 0.25-0.30%
- Slippage (small trades): 0.10-0.50%
- Slippage (larger trades): 0.50-2.00%
- Priority fees: negligible for non-HFT
- **Total**: 0.40-2.50% round-trip

A strategy needs at least this much gross edge per trade to be worth trading.
