---
name: kelly-criterion
description: Kelly criterion optimal sizing with fractional variants, edge estimation, and practical application for crypto trading
---

# Kelly Criterion — Optimal Bet Sizing

The Kelly criterion is the mathematically optimal bet size that maximizes long-term geometric growth of capital. Developed by John Kelly at Bell Labs in 1956, it answers a precise question: given a known edge, what fraction of your bankroll should you risk to maximize the compounding rate?

**Core insight**: Betting too small leaves growth on the table. Betting too large increases ruin risk and actually *reduces* long-term growth. Kelly finds the exact optimum between these extremes.

**Practical insight**: You should almost never use full Kelly. Estimation error in your edge means full Kelly will overbets in practice. Use fractional Kelly (0.25x to 0.5x) for real trading.

---

## The Kelly Formula

For a binary outcome (win or lose):

```
f* = (p * b - q) / b
```

Where:
- `f*` = optimal fraction of bankroll to bet
- `p` = probability of winning
- `q` = probability of losing (1 - p)
- `b` = payoff ratio (average win / average loss)

**Equivalent forms**:

```
f* = p - q / b
f* = p - (1 - p) / b
f* = (p * b - (1 - p)) / b
```

**Edge** = `p * b - q` = expected value per unit risked. Kelly only makes sense when edge > 0. If edge is zero or negative, the optimal bet is zero — do not trade.

### Quick Reference

| Win Rate | Payoff 1:1 | Payoff 1.5:1 | Payoff 2:1 | Payoff 3:1 |
|----------|-----------|-------------|-----------|-----------|
| 40%      | -20%      | -6.7%       | 10%       | 20%       |
| 45%      | -10%      | 3.3%        | 15%       | 25%       |
| 50%      | 0%        | 16.7%       | 25%       | 33.3%     |
| 55%      | 10%       | 18.3%       | 27.5%     | 35%       |
| 60%      | 20%       | 26.7%       | 35%       | 40%       |

*Values are full Kelly fraction. In practice, use 0.25x to 0.5x of these numbers.*

---

## Why Use Fractional Kelly

Full Kelly assumes you know `p` and `b` exactly. You never do. Here is why fractional Kelly is essential:

### 1. Estimation Error

Your win rate estimate from 100 trades has a standard error of roughly ±5%. If your true win rate is 55% but you estimate 60%, full Kelly will overbets by ~50%, which *reduces* long-term growth below what half Kelly would achieve.

### 2. Variance and Drawdowns

Full Kelly has extremely high variance. Expected maximum drawdown for full Kelly is roughly 50-80% of account. This is psychologically devastating and practically dangerous (margin calls, inability to continue trading).

| Kelly Fraction | Relative Growth Rate | Approximate Max Drawdown |
|---------------|---------------------|-------------------------|
| 1.0x (full)   | 100%                | 50-80%                  |
| 0.5x (half)   | ~75%                | 25-40%                  |
| 0.25x (quarter)| ~50%               | 12-20%                  |
| 0.1x (tenth)  | ~25%                | 5-10%                   |

### 3. Asymmetry of Over vs. Under Betting

Overbetting by 2x (betting at 2*f*) produces **zero** long-term growth — the same as not trading at all. Underbetting by 2x (betting at 0.5*f*) still captures ~75% of the optimal growth rate. The penalty for overbetting is catastrophically worse than for underbetting.

### Recommended Fractions

| Fraction | When to Use |
|----------|------------|
| 0.10x Kelly | Very uncertain edge, new strategy, < 30 trades in sample |
| 0.25x Kelly | Moderate confidence, 30-100 trades, reasonable Sharpe |
| 0.50x Kelly | High confidence, 100+ trades, consistent performance |
| 1.00x Kelly | Never recommended in practice |

---

## Estimating Your Edge

Kelly requires two inputs: win rate (`p`) and payoff ratio (`b`). Both must be estimated from data.

### Minimum Data Requirements

- **50 trades minimum** for any Kelly calculation. Below this, estimation error dominates.
- **100+ trades preferred** for half Kelly sizing.
- **200+ trades** before considering aggressive fractions.

### Calculation from Trade History

```python
wins = [t for t in trades if t > 0]
losses = [t for t in trades if t < 0]

win_rate = len(wins) / len(trades)               # p
payoff_ratio = mean(wins) / abs(mean(losses))     # b
edge = win_rate * payoff_ratio - (1 - win_rate)   # should be > 0

kelly_full = (win_rate * payoff_ratio - (1 - win_rate)) / payoff_ratio
```

### Conservative Estimation

Use the **lower bound of a Wilson confidence interval** for win rate rather than the point estimate:

```python
import math

def wilson_lower(wins: int, total: int, z: float = 1.96) -> float:
    """Lower bound of Wilson score interval (95% confidence)."""
    p = wins / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (centre - spread) / denominator
```

Using the lower bound of the confidence interval for win rate automatically builds in conservatism, reducing the risk of overbetting due to sampling luck.

### Edge Strength Classification

| Edge Value | Classification | Notes |
|-----------|---------------|-------|
| < 0       | Negative edge | Do not trade this strategy |
| 0 - 0.02  | No meaningful edge | Transaction costs likely exceed edge |
| 0.02 - 0.10 | Marginal edge | Conservative fractions only |
| 0.10 - 0.20 | Good edge | Standard fractions appropriate |
| > 0.20    | Excellent edge | Rare; verify not overfitting or temporary |

---

## Multi-Bet Kelly (Simultaneous Positions)

When holding multiple positions simultaneously:

### Independent Bets

If bets are uncorrelated, each can be sized at its individual Kelly fraction. However, the **sum of all Kelly fractions** should not exceed 1.0 (total portfolio). If it does, scale each proportionally:

```python
kelly_fractions = [0.15, 0.10, 0.12, 0.08]  # individual Kelly fractions
total = sum(kelly_fractions)  # 0.45
if total > 1.0:
    scale = 1.0 / total
    kelly_fractions = [f * scale for f in kelly_fractions]
```

### Correlated Bets

Correlated positions (e.g., multiple SOL memecoins) are effectively one larger bet. Reduce each position proportionally to the correlation:

```python
# Simple correlation adjustment
def adjust_for_correlation(kelly_fractions: list, avg_correlation: float) -> list:
    """Reduce Kelly fractions based on average inter-position correlation."""
    n = len(kelly_fractions)
    # Effective number of independent bets
    n_eff = n / (1 + (n - 1) * avg_correlation)
    scale = n_eff / n
    return [f * scale for f in kelly_fractions]
```

In crypto, meme token positions often have correlations of 0.5-0.8 with each other (they all dump together in risk-off). Treat them as partially one bet.

### Portfolio Kelly Cap

Regardless of individual calculations, enforce a hard cap: **total Kelly allocation should never exceed 1.0** (100% of portfolio). A practical maximum is 0.6-0.8 to leave cash buffer for drawdowns and new opportunities.

---

## PumpFun / Meme Token Kelly

Meme token trading presents specific challenges for Kelly:

1. **Edge is hard to estimate**: Win rates and payoff ratios shift rapidly with market regime.
2. **Fat tails dominate**: A few large winners and many small losers. Standard Kelly assumes thin tails.
3. **Correlation spikes in drawdowns**: All meme tokens can dump simultaneously.

### Practical Adjustments

- Use **0.1x to 0.25x Kelly** maximum for meme tokens.
- Cap absolute position size at **2-5% of portfolio** regardless of Kelly output.
- Recalculate edge weekly — stale estimates are dangerous.
- If Kelly suggests > 30%, your edge estimate is almost certainly wrong. Use 5% maximum.

```python
def meme_kelly(win_rate: float, payoff_ratio: float, account: float) -> float:
    """Conservative Kelly for high-uncertainty meme token trades."""
    kelly_full = (win_rate * payoff_ratio - (1 - win_rate)) / payoff_ratio
    kelly_conservative = kelly_full * 0.15  # 0.15x fractional
    max_fraction = 0.05                     # hard cap at 5%
    return min(max(kelly_conservative, 0), max_fraction) * account
```

---

## When Kelly Does Not Work

Kelly optimality relies on assumptions that are often violated:

| Assumption | Reality | Impact |
|-----------|---------|--------|
| Known edge (p, b) | Estimated from noisy data | Overbetting risk |
| Independent bets | Correlated positions | Ruin risk increases |
| Binary outcomes | Continuous P&L distribution | Formula approximation |
| Stationary edge | Edge changes over time | Stale sizing |
| No transaction costs | Slippage, fees, MEV | Effective edge lower |
| Unlimited divisibility | Minimum position sizes | Rounding needed |

### Mitigations

1. **Use fractional Kelly** (addresses estimation error)
2. **Adjust for correlation** (addresses dependence)
3. **Use continuous Kelly** for non-binary returns (see `references/kelly_derivation.md`)
4. **Recalculate regularly** (addresses non-stationarity)
5. **Subtract estimated costs** from edge before calculating Kelly

---

## Continuous Kelly (For Portfolio Returns)

When returns are continuous rather than binary win/lose:

```
f* = (μ - r) / σ²
```

Where:
- `μ` = expected return of the strategy
- `r` = risk-free rate (often 0 for crypto)
- `σ²` = variance of returns

This is equivalent to `Sharpe² / (2 * σ)` when the Sharpe ratio is computed as `(μ - r) / σ`.

Use this form when you have a return stream rather than discrete win/loss trades. See `references/kelly_derivation.md` for the full derivation.

---

## Integration with Other Skills

- **`position-sizing`**: Kelly provides the optimal fraction; position-sizing translates that into units. Use Kelly as one input, then apply liquidity and volatility constraints from position-sizing.
- **`risk-management`**: Kelly sizing must respect portfolio-level risk limits. If Kelly suggests 10% per trade but your risk policy caps at 5%, the cap wins.
- **`strategy-framework`**: Document your Kelly parameters (fraction used, sample size, recalculation frequency) as part of strategy specification.
- **`regime-detection`**: Recalculate Kelly when regime changes. Edge in a trending market differs from edge in a ranging market.

---

## Files

### References
- `references/kelly_derivation.md` — Full mathematical derivation of Kelly criterion, fractional Kelly growth rates, continuous Kelly, and multi-outcome Kelly
- `references/practical_kelly.md` — Edge estimation from trading data, confidence intervals, worked examples, common pitfalls, and danger zones

### Scripts
- `scripts/kelly_calculator.py` — Kelly calculator from win rate, payoff ratio, and account size. Prints fractional Kelly recommendations and sensitivity analysis. Dependencies: none.
- `scripts/kelly_from_trades.py` — Estimate Kelly from a list of trade P&L values. Computes confidence intervals, rolling stability analysis, and recommended fraction. Dependencies: numpy.
