# Execution Algorithms Reference

## Overview

Execution algorithms determine how to split a large order across time to
minimize total trading cost. This reference covers the major approaches from
simplest to most sophisticated.

## TWAP — Time-Weighted Average Price

**Idea**: Trade equal amounts at equal time intervals.

**Formula**:

```
q_t = Q / N    for all t = 1, ..., N
```

Where `Q` = total quantity, `N` = number of time steps.

**Properties**:
- Zero information requirement — no forecasts needed
- Deterministic schedule — fully predictable
- Baseline benchmark for all other algorithms
- Suboptimal when volume or volatility varies over time

**Best for**: Orders where simplicity and predictability outweigh optimization.

## VWAP — Volume-Weighted Average Price

**Idea**: Trade proportional to expected volume in each period.

**Formula**:

```
q_t = Q * (V_t / sum(V_1..V_N))
```

Where `V_t` = expected volume at step `t`.

**Volume profile estimation**:
- Historical average volume by time-of-day (most common)
- Exponential moving average of recent volume patterns
- Intraday volume U-shape: higher at open/close, lower midday

**Properties**:
- Trades more when liquidity is naturally higher
- Reduces temporary impact vs TWAP
- Requires volume forecasting (forecast error adds risk)
- Does not adapt to real-time conditions

**Best for**: Medium-sized orders where volume patterns are stable.

## Almgren-Chriss Optimal Execution

**Idea**: Minimize expected cost + risk penalty with linear impact assumptions.

### Model Setup

- Total quantity to sell: `Q` shares
- Time horizon: `T`, divided into `N` steps of length `τ = T/N`
- Trading trajectory: `x_0 = Q, x_1, ..., x_N = 0`
- Trade at step `k`: `n_k = x_{k-1} - x_k` (units sold)
- Trade rate: `v_k = n_k / τ`

### Impact Model

**Temporary impact** (per-trade cost, decays immediately):

```
h(v) = ε * sign(v) + η * v
```

- `ε` = fixed cost per trade (half-spread)
- `η` = temporary impact coefficient

**Permanent impact** (shifts equilibrium price):

```
g(v) = γ * v
```

- `γ` = permanent impact coefficient

### Objective Function

```
minimize: E[cost(x)] + λ * Var[cost(x)]
```

Where `λ` is the risk-aversion parameter:
- `λ = 0`: minimize expected cost only (patient trader)
- `λ → ∞`: execute immediately (urgent trader)

### Expected Cost

```
E[cost] = 0.5 * γ * Q² + ε * Σ|n_k| + η * Σ(n_k² / τ)
```

Components:
1. Permanent impact cost: `0.5 * γ * Q²` (unavoidable)
2. Fixed transaction cost: `ε * Σ|n_k|`
3. Temporary impact cost: `η * Σ(n_k² / τ)` (minimized by spreading trades)

### Variance of Cost

```
Var[cost] = σ² * τ * Σ x_k²
```

Where `σ` = price volatility. Holding inventory exposes us to price risk.

### Optimal Solution

For the linear impact model, the optimal trajectory is:

```
x_k = Q * sinh(κ * (N - k)) / sinh(κ * N)
```

Where:

```
κ = arccosh((τ² * λ * σ² / (2 * η)) + 1)
```

The parameter `κ` controls the aggressiveness:
- Small `κ` (low risk aversion): trade slowly, close to TWAP
- Large `κ` (high risk aversion): front-load trades, execute quickly

### Cost Components

| Component | Formula | Nature |
|---|---|---|
| Permanent impact | `0.5 * γ * Q²` | Fixed, unavoidable |
| Temporary impact | `η * Σ(n_k²/τ)` | Decreases with more spreading |
| Timing risk | `λ * σ² * τ * Σ x_k²` | Increases with more spreading |

The optimal solution balances temporary impact (favors slow execution) against
timing risk (favors fast execution).

## IS — Implementation Shortfall

**Idea**: Minimize slippage from the decision price (price when order is placed).

**Formula**:

```
IS = (execution_price - decision_price) * quantity
```

**Implementation**:
- Set a benchmark at order arrival
- Dynamically adjust trade rate based on how far price has moved
- Trade faster if price is moving against you (adverse selection)
- Trade slower if price is favorable

**Properties**:
- Directly targets the metric traders care about
- Naturally adapts to price movements
- More complex than TWAP/VWAP to implement
- Sensitive to the benchmark price choice

## RL-Based Execution

**Idea**: Learn the optimal execution policy from simulated experience using
reinforcement learning (DQN, PPO, or actor-critic methods).

### Architecture

```
State → Neural Network → Action (trade size)
         ↑ trained via
    Experience Replay
```

### DQN Approach

- Q-network maps state → Q-values for each discrete action
- Actions: {0%, 10%, 25%, 50%, 100%} of remaining quantity
- Train with experience replay and target network
- Epsilon-greedy exploration during training

### PPO Approach

- Policy network outputs action probabilities
- Value network estimates expected return
- Train with clipped surrogate objective
- More stable than DQN for continuous-like problems

### Advantages Over Classical Methods

- Can learn non-linear impact relationships
- Adapts to current market conditions in real time
- Can incorporate rich state features (orderbook shape, etc.)
- No need for closed-form solutions

### Disadvantages

- Requires realistic market simulator for training
- Sim-to-real gap is a major challenge
- Training can be unstable and sample-inefficient
- Harder to explain/audit than analytical solutions

## Algorithm Comparison

| Algorithm | Adaptivity | Complexity | Data Needs | Best For |
|---|---|---|---|---|
| TWAP | None | Trivial | None | Benchmarking, small orders |
| VWAP | Volume | Low | Volume history | Medium orders, stable markets |
| Almgren-Chriss | None (offline) | Medium | σ, η, γ estimates | Large orders, known parameters |
| IS | Price-reactive | Medium | Real-time price | Urgent orders, adverse selection |
| RL | Full (learned) | High | Simulator + training | Research, institutional scale |

## Choosing an Algorithm

1. **Order < 0.1% daily volume**: Use market order or basic limit order
2. **Order 0.1-1% daily volume**: TWAP or VWAP is sufficient
3. **Order 1-5% daily volume**: Almgren-Chriss or IS recommended
4. **Order > 5% daily volume**: RL or sophisticated adaptive strategies
5. **DEX with thin liquidity**: Even small orders may need execution algorithms

## Parameter Calibration

### Estimating Temporary Impact (η)

```
η ≈ spread / (2 * avg_trade_size)
```

Or fit from historical data: regress realized impact on trade size.

### Estimating Permanent Impact (γ)

```
γ ≈ daily_volatility * sqrt(1 / daily_volume)
```

Typically `γ << η` for liquid assets; `γ ≈ η` for illiquid ones.

### Risk Aversion (λ)

- Conservative (institutional): `λ = 1e-6` to `1e-5`
- Moderate: `λ = 1e-5` to `1e-4`
- Aggressive (retail): `λ = 1e-4` to `1e-3`

Higher `λ` means faster execution and higher impact cost but lower timing risk.
