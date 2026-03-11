# RL Framework for Execution Optimization

## MDP Formulation

Execution optimization is modeled as a finite-horizon Markov Decision Process
(MDP) where the agent must fully execute an order within a fixed time window.

### State Space

```python
state = {
    "remaining_qty": float,   # Normalized: 1.0 at start, 0.0 when done
    "time_remaining": float,  # Normalized: 1.0 at start, 0.0 at deadline
    "price_relative": float,  # Current price / arrival price
    "spread": float,          # Current bid-ask spread (normalized)
    "volatility": float,      # Recent realized volatility (rolling window)
    "volume": float,          # Recent volume / average volume
}
```

**Normalization**: All state features are scaled to roughly [0, 1] or [-1, 1]
for stable neural network training.

**Optional extensions**:
- Orderbook imbalance (bid_volume - ask_volume) / total
- Momentum indicator (short-term price change)
- Time-of-day encoding (captures intraday patterns)

### Action Space

Discrete actions keep the problem tractable:

| Action | Meaning | When Useful |
|---|---|---|
| 0 | Trade 0% of remaining | Wait for better conditions |
| 1 | Trade 10% of remaining | Conservative participation |
| 2 | Trade 25% of remaining | Moderate participation |
| 3 | Trade 50% of remaining | Aggressive participation |
| 4 | Trade 100% of remaining | Immediate completion |

**Continuous alternative**: Output a single float in [0, 1] representing
fraction of remaining to trade. Requires actor-critic methods (PPO, SAC).

### Reward Function

**Per-step reward** (implementation shortfall):

```python
reward_t = -(exec_price_t - arrival_price) * qty_traded_t
```

**Terminal penalty** (if order not completed by deadline):

```python
if remaining_qty > 0 at deadline:
    penalty = -remaining_qty * slippage_estimate * penalty_multiplier
```

**Alternative rewards**:
- TWAP-relative: `-(exec_price_t - twap_price_t) * qty_traded_t`
- Risk-adjusted: add variance penalty term
- Shaped: small bonus for maintaining smooth trade rate

### Episode Structure

```
t=0: Order arrives. State = (1.0, 1.0, 1.0, spread, vol, volume)
t=1..N-1: Agent selects actions, environment simulates trades
t=N: Deadline. Force-execute any remaining quantity.
Total reward = sum of per-step rewards + terminal penalty
```

Typical episode: 20-50 time steps representing a 10-minute to 1-hour window.

## Environment Design

### Price Dynamics

Geometric Brownian Motion with impact:

```python
# Per time step
dW = np.random.normal(0, 1)
price_change = mu * dt + sigma * sqrt(dt) * dW
permanent_shift = gamma * trade_rate
temporary_cost = eta * trade_rate

# Update mid-price (permanent impact persists)
mid_price *= (1 + price_change + permanent_shift)

# Execution price (temporary impact is per-trade only)
exec_price = mid_price * (1 + temporary_cost)
```

### Impact Model Parameters

```python
# Calibration from market data
eta = 0.001      # Temporary impact coefficient
gamma = 0.0005   # Permanent impact coefficient
sigma = 0.02     # Volatility (per step)
mu = 0.0         # Drift (typically zero for short horizons)
```

**Square-root impact** (more realistic for large orders):

```python
temporary_impact = eta * sign(v) * sqrt(abs(v) / avg_volume)
permanent_impact = gamma * sign(v) * sqrt(abs(v) / avg_volume)
```

### Volume Dynamics

Simulate realistic intraday volume patterns:

```python
def volume_profile(t: float) -> float:
    """U-shaped intraday volume (higher at open/close)."""
    return 1.0 + 0.5 * (4 * (t - 0.5)**2)
```

### Spread Dynamics

Spread widens with volatility and narrows with volume:

```python
spread = base_spread * (1 + vol_sensitivity * volatility) / (1 + vol_factor * volume)
```

## Training Methodology

### DQN Training

```python
# Hyperparameters
learning_rate = 1e-4
batch_size = 64
replay_buffer_size = 100_000
target_update_freq = 1000
gamma_discount = 0.99
epsilon_start = 1.0
epsilon_end = 0.01
epsilon_decay = 0.995

# Training loop
for episode in range(num_episodes):
    state = env.reset()
    total_reward = 0
    while not done:
        action = epsilon_greedy(q_network, state, epsilon)
        next_state, reward, done, info = env.step(action)
        replay_buffer.add(state, action, reward, next_state, done)
        if len(replay_buffer) >= batch_size:
            batch = replay_buffer.sample(batch_size)
            loss = update_q_network(batch)
        state = next_state
        total_reward += reward
    epsilon *= epsilon_decay
```

### PPO Training

```python
# Hyperparameters
learning_rate = 3e-4
clip_ratio = 0.2
epochs_per_update = 10
batch_size = 2048
gamma_discount = 0.99
gae_lambda = 0.95

# Collect trajectories, then update
trajectories = collect_rollouts(policy, env, num_steps=batch_size)
advantages = compute_gae(trajectories, value_network, gamma, gae_lambda)
for epoch in range(epochs_per_update):
    update_policy(policy, trajectories, advantages, clip_ratio)
    update_value(value_network, trajectories)
```

### Training Tips

1. **Curriculum learning**: Start with easy orders (small size, long horizon)
   and gradually increase difficulty.
2. **Domain randomization**: Vary impact parameters, volatility, and volume
   across episodes to improve generalization.
3. **Reward normalization**: Normalize rewards by order size for stable training.
4. **Multiple seeds**: Train 3-5 agents with different seeds; ensemble or pick
   the best on a validation set.

## Evaluation

### Metrics

| Metric | Formula | Target |
|---|---|---|
| Implementation Shortfall | `(VWAP_exec - arrival_price) * Q` | Minimize |
| TWAP Improvement | `(cost_TWAP - cost_RL) / cost_TWAP` | Positive |
| Cost Std Dev | `std(cost across episodes)` | Low |
| Completion Rate | `% of episodes fully executed on time` | >99% |

### Benchmark Comparison Protocol

1. Fix a set of 1,000+ test scenarios (same random seeds)
2. Run TWAP, VWAP, Almgren-Chriss, and RL agent on each
3. Compare mean cost, std, 95th percentile, worst case
4. Statistical significance: paired t-test or Wilcoxon signed-rank

### Walk-Forward Validation

- Train on simulated data from period 1
- Validate on simulated data from period 2 (different parameters)
- Test on held-out scenarios with unseen parameter combinations
- Monitor for overfitting to specific simulator dynamics

## Practical Considerations

### Sim-to-Real Gap

The biggest challenge in RL execution. Mitigations:

1. **Realistic simulation**: Calibrate impact model from real trade data
2. **Domain randomization**: Vary parameters widely during training
3. **Conservative deployment**: Start with small orders, blend RL with TWAP
4. **Online adaptation**: Fine-tune the agent on live execution data
5. **Safety constraints**: Hard limits on maximum trade rate per step

### DEX-Specific Considerations

- **Block-level granularity**: Solana blocks are ~400ms; cannot trade faster
- **AMM mechanics**: Impact follows the bonding curve, not a linear model
- **MEV risk**: Sandwich attacks can increase execution cost
- **Gas/priority fees**: Each transaction has a base cost
- **Slippage tolerance**: Must set per-transaction slippage limits

### When RL Execution Is Not Worth It

- Order size < 0.1% of available liquidity
- Execution window is very short (< 1 minute)
- Market is highly liquid with tight spreads
- Regulatory constraints require specific execution algorithms
- Team lacks ML infrastructure for training and monitoring

### Deployment Architecture

```
Market Data Feed → State Encoder → RL Agent → Trade Scheduler → DEX Router
                                      ↑                            ↓
                                  Model Store              Execution Monitor
                                      ↑                            ↓
                                Training Pipeline ← Performance Tracker
```

The agent runs inference at each decision point (every block or every N
seconds), outputting the next trade size. A trade scheduler converts this
to actual transactions via a DEX aggregator.
