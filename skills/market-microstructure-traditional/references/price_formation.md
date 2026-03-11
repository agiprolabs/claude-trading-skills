# Price Formation Models

How orders become prices. This reference covers the foundational models of
price formation in limit order book markets, adapted for crypto context.

---

## Glosten-Milgrom Model (1985)

### Setup

- An asset has true value V, known to informed traders but not the market maker
- Traders arrive sequentially: informed (probability π) or uninformed (1-π)
- The market maker posts bid and ask prices, updating after each trade

### Equilibrium Conditions

The market maker sets prices to break even in expectation:

```
ask = E[V | next trade is a buy]
bid = E[V | next trade is a sell]
```

Since buys are more likely from informed traders when V is high:

```
ask > E[V] > bid
```

The spread arises purely from adverse selection — the MM must be compensated
for the risk of trading against someone who knows more.

### Spread Determinants

The spread widens when:
- **π increases** — more informed traders in the population
- **Information asymmetry increases** — informed traders know more
- **Uninformed volume drops** — less "good" flow to offset losses

### Bayesian Updating

After observing a buy at the ask:

```
P(V=high | buy) = P(buy | V=high) * P(V=high) / P(buy)
```

The market maker updates beliefs and revises quotes. This creates the
*permanent price impact* of trades — prices move because trades convey
information.

### Crypto Application

On CEX order books, the Glosten-Milgrom intuition explains why:
- Spreads widen before major announcements (higher π expected)
- Illiquid altcoins have wider spreads (fewer uninformed traders)
- Spreads widen during volatility spikes (information asymmetry rises)

---

## Kyle Model (1985)

### Setup

Three types of participants:
1. **Informed trader** — knows true value V, trades optimally
2. **Noise traders** — trade randomly with volume u ~ N(0, σ_u²)
3. **Market maker** — observes total order flow, sets price

### Equilibrium

The market maker sets price as a linear function of net order flow:

```
P = μ + λ * (x + u)
```

Where:
- μ: prior expected value
- λ: Kyle's lambda (price impact coefficient)
- x: informed trader's order
- u: noise trader volume

### Kyle's Lambda

```
λ = σ_v / (2 * σ_u)
```

Where σ_v is the standard deviation of the asset's true value and σ_u is
the standard deviation of noise trading.

**Interpretation**: lambda is the price impact per unit of signed volume.
Higher lambda means less liquidity.

### Estimation from Data

Regress price changes on signed order flow in fixed intervals:

```python
import numpy as np

def estimate_kyle_lambda(
    midprice_changes: np.ndarray,
    signed_volumes: np.ndarray,
    interval_seconds: int = 60,
) -> dict:
    """Estimate Kyle's lambda from aggregated trade data.

    Args:
        midprice_changes: Change in midprice per interval.
        signed_volumes: Net signed volume per interval.
        interval_seconds: Aggregation interval.

    Returns:
        Dict with lambda estimate, R-squared, t-statistic.
    """
    X = np.column_stack([np.ones(len(signed_volumes)), signed_volumes])
    beta, residuals, _, _ = np.linalg.lstsq(X, midprice_changes, rcond=None)

    y_hat = X @ beta
    ss_res = np.sum((midprice_changes - y_hat) ** 2)
    ss_tot = np.sum((midprice_changes - midprice_changes.mean()) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    n = len(signed_volumes)
    se = np.sqrt(ss_res / (n - 2) / np.sum((signed_volumes - signed_volumes.mean()) ** 2))
    t_stat = beta[1] / se if se > 0 else 0.0

    return {
        "lambda": float(beta[1]),
        "intercept": float(beta[0]),
        "r_squared": float(r_squared),
        "t_statistic": float(t_stat),
        "n_observations": n,
    }
```

### Typical Values

| Market | Lambda (bps per $1M flow) | Notes |
|---|---|---|
| BTC/USDT (Binance) | 0.5-2 | Deep liquidity |
| ETH/USDT (Binance) | 1-4 | Moderate |
| Mid-cap altcoins | 10-50 | Thin books |
| Small-cap altcoins | 50-500 | Very illiquid |

---

## PIN Model — Probability of Informed Trading

The PIN model (Easley, Kiefer, O'Hara, 1996) estimates the probability
that any given trade is from an informed trader.

### Parameters

- **α**: probability of an information event on a given day
- **δ**: probability the event is bad news (given an event occurs)
- **μ**: arrival rate of informed traders (when event occurs)
- **ε_b**: arrival rate of uninformed buy orders
- **ε_s**: arrival rate of uninformed sell orders

### PIN Formula

```
PIN = (α * μ) / (α * μ + ε_b + ε_s)
```

### Estimation

PIN is estimated via maximum likelihood on daily buy/sell counts.
The likelihood for a single day with B buys and S sells:

```
L(B,S) = (1-α) * f(B|ε_b) * f(S|ε_s)
       + α*δ * f(B|ε_b) * f(S|ε_s + μ)       # bad news day
       + α*(1-δ) * f(B|ε_b + μ) * f(S|ε_s)   # good news day
```

Where f(k|λ) is the Poisson PMF.

### Crypto Application

- High PIN tokens have wider spreads and more adverse selection
- PIN tends to spike before token unlocks, exchange listings, governance votes
- Can be computed from CEX trade data by classifying trades via tick rule

```python
def classify_trades_tick_rule(
    prices: list[float],
) -> list[int]:
    """Classify trades as buys (+1) or sells (-1) via tick rule.

    Args:
        prices: Sequence of trade prices.

    Returns:
        List of trade signs.
    """
    signs = [1]  # first trade is ambiguous, default to buy
    for i in range(1, len(prices)):
        if prices[i] > prices[i - 1]:
            signs.append(1)
        elif prices[i] < prices[i - 1]:
            signs.append(-1)
        else:
            signs.append(signs[-1])  # repeat last sign
    return signs
```

---

## Spread Decomposition

### Three-Component Model (Stoll, 1989)

```
quoted_spread = adverse_selection + inventory_cost + order_processing
```

### Empirical Decomposition (Huang-Stoll, 1997)

Estimate from the covariance of trade signs and quote revisions:

```
quote_revision = α * S/2 * q_t + noise
```

Where α is the adverse selection fraction of the half-spread and q_t is
the trade sign. The inventory component β is estimated from:

```
E[q_{t+1} | q_t] = 1 - 2*(β + α)
```

### Practical Shortcut: Effective vs Realized Spread

```
adverse_selection = effective_spread - realized_spread
```

The effective spread is what the trader pays; the realized spread (measured
with a delay) is what the market maker keeps. The difference is adverse
selection — profits lost to informed traders.

Typical delay: 5-30 seconds for crypto (one to several blocks on DEX).
