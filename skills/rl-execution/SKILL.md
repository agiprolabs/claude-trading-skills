---
name: rl-execution
description: Reinforcement learning for trade execution optimization including order splitting, adaptive timing, and impact minimization
---

# RL Execution Optimization

Reinforcement learning (RL) for trade execution teaches an agent to split and
time large orders so that total market impact is minimized. Instead of following
a fixed schedule (TWAP, VWAP), an RL agent observes real-time market state and
adapts its trading rate on the fly.

## Why Execution Optimization Matters

Every trade has a cost beyond the quoted spread:

| Cost Component | Cause | Typical Magnitude |
|---|---|---|
| Spread cost | Crossing the bid-ask | 5-50 bps on DEXs |
| Temporary impact | Consuming liquidity | Scales with trade rate |
| Permanent impact | Information leakage | Scales with total size |
| Timing risk | Price drifts while waiting | Scales with volatility and time |

A 100 SOL market buy on a thin pool can move the price 2-5%. Splitting it into
ten 10 SOL slices over a few minutes can cut that cost by 30-60%. The question
is **how** to split optimally — and that is where execution algorithms and RL
come in.

## The RL Framework for Execution

### State Space

The agent observes at each decision step:

```
state = [
    remaining_qty,    # How much is left to trade (0-1 normalized)
    time_remaining,   # Fraction of allowed horizon remaining
    current_price,    # Current mid-price (normalized to arrival price)
    spread,           # Current bid-ask spread
    volatility,       # Recent realized volatility
    volume,           # Recent trading volume (normalized)
]
```

### Action Space

Discrete actions controlling how much to trade this step:

```
actions = [0%, 10%, 25%, 50%, 100%]  # of remaining quantity
```

A small action space keeps the problem tractable. Each action represents the
fraction of the remaining order to execute in the current time step.

### Reward Function

The reward penalizes execution cost relative to a benchmark:

```
reward = -(execution_price - arrival_price) * quantity_traded
```

Summed over all steps, the total reward equals the negative implementation
shortfall. The agent learns to minimize total cost.

### Episode Structure

One episode = one order from placement to completion:

1. Agent receives order: buy/sell Q units within T time steps
2. At each step, agent picks an action (trade amount)
3. Market simulator applies price impact and updates state
4. Episode ends when quantity is fully executed or time expires
5. Any remaining quantity at expiry is executed at market (penalty)

## Standard Execution Algorithms

### TWAP (Time-Weighted Average Price)

The simplest baseline — split the order equally across all time steps:

```python
trade_per_step = total_quantity / num_steps
```

**Pros**: Simple, deterministic, easy to implement.
**Cons**: Ignores market conditions entirely.

### VWAP (Volume-Weighted Average Price)

Split proportional to expected volume in each period:

```python
trade_at_step_t = total_quantity * (expected_volume[t] / total_expected_volume)
```

**Pros**: Trades more when liquidity is available.
**Cons**: Requires accurate volume forecasts; still non-adaptive.

### Almgren-Chriss Optimal Execution

The foundational analytical model. Minimizes a combination of execution cost
and timing risk:

```
minimize: E[cost] + λ * Var[cost]
```

With linear impact assumptions, this yields a closed-form optimal trajectory.
See `references/execution_algorithms.md` for the full derivation.

### RL-Based Adaptive Execution

An RL agent (DQN, PPO, or similar) that learns the execution policy from
simulated experience:

```python
# Pseudocode training loop
for episode in range(num_episodes):
    state = env.reset(order_qty=Q, horizon=T)
    done = False
    while not done:
        action = agent.select_action(state)
        next_state, reward, done, info = env.step(action)
        agent.store_transition(state, action, reward, next_state, done)
        agent.update()
        state = next_state
```

**Pros**: Adapts to current market conditions, can learn non-linear patterns.
**Cons**: Requires realistic simulator, sim-to-real gap, training instability.

## Price Impact Model

The simulator uses a standard two-component impact model:

```
temporary_impact = η * (trade_rate / avg_volume)
permanent_impact = γ * (trade_rate / avg_volume)
```

- **Temporary impact** decays after the trade (liquidity replenishes)
- **Permanent impact** shifts the equilibrium price (information effect)

The execution price for a trade of size `q` at time `t`:

```
exec_price = mid_price + permanent_impact + temporary_impact
mid_price_next = mid_price + permanent_impact + noise
```

## When to Use This Skill

This skill is most valuable when:

- **Order size is large relative to available liquidity** (>1% of daily volume)
- **Market impact is significant** (thin DEX pools, low-cap tokens)
- **Execution window is flexible** (minutes to hours, not milliseconds)
- **Cost savings justify complexity** (institutional-scale orders)

For small retail orders (<$1,000 on liquid pairs), simple market orders or
basic slippage limits are sufficient. See the `slippage-modeling` skill instead.

## Practical Limitations

1. **Sim-to-real gap**: Simulated markets do not capture all real dynamics
   (queue position, adversarial flow, MEV).
2. **Non-stationarity**: Market microstructure changes over time; models
   trained on one regime may fail in another.
3. **DEX specifics**: On-chain execution has block-level granularity (~400ms
   on Solana), not continuous-time. Gas/priority fees add cost.
4. **Data requirements**: Training requires historical orderbook or trade data
   for realistic simulation.

## Integration with Other Skills

| Skill | Integration |
|---|---|
| `slippage-modeling` | Provides impact estimates to calibrate the simulator |
| `position-sizing` | Determines the total order size to execute |
| `liquidity-analysis` | Assesses available liquidity for realistic simulation |
| `volatility-modeling` | Supplies volatility estimates for the state vector |
| `jupiter-swap` | Actual on-chain execution of the computed trade schedule |

## Quick Start

### Compare Execution Strategies (No API Needed)

```bash
python scripts/execution_simulator.py
```

Runs TWAP, VWAP, and adaptive strategies in a simulated market and compares
execution costs across many trials.

### Almgren-Chriss Optimal Trajectory

```bash
python scripts/almgren_chriss.py
```

Computes the analytically optimal execution trajectory and compares it to
TWAP for a given set of market parameters.

## Files

### References
- `references/execution_algorithms.md` — TWAP, VWAP, Almgren-Chriss, IS, and
  RL execution algorithms with formulas and comparison
- `references/rl_framework.md` — MDP formulation, environment design, training
  methodology, and practical considerations for RL execution

### Scripts
- `scripts/execution_simulator.py` — Simulated order execution comparing TWAP,
  VWAP, and adaptive strategies with price impact
- `scripts/almgren_chriss.py` — Almgren-Chriss optimal execution model with
  trajectory computation and cost analysis

## Dependencies

```bash
uv pip install numpy
```

No API keys required — all scripts run in simulation/demo mode.

## Further Reading

- Almgren, R. & Chriss, N. (2001). "Optimal execution of portfolio transactions."
  *Journal of Risk*, 3(2), 5-39.
- Bertsimas, D. & Lo, A. (1998). "Optimal control of execution costs."
  *Journal of Financial Markets*, 1(1), 1-50.
- Ning, B., Lin, F. H. T., & Jaimungal, S. (2021). "Double deep Q-learning
  for optimal execution." *Applied Mathematical Finance*, 28(4), 361-380.

## Disclaimer

This skill provides educational analysis tools for studying execution
algorithms. It does not constitute financial advice. Simulated results do
not guarantee real-world performance. Always test execution strategies
with small sizes before scaling up.
