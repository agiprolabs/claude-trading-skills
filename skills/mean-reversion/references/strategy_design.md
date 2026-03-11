# Mean-Reversion Strategy Design

This reference covers the practical aspects of building, sizing, and risk-managing a mean-reversion strategy. It assumes you have already confirmed mean-reversion behavior using the tests in `statistical_tests.md`.

---

## Z-Score Entry/Exit Framework

### Computing the Z-Score

```python
import numpy as np, pandas as pd

def compute_z_score(series: np.ndarray, lookback: int) -> np.ndarray:
    """Compute rolling z-score. NaN for first lookback-1 values."""
    s = pd.Series(series)
    return ((s - s.rolling(lookback).mean()) / s.rolling(lookback).std()).values
```

### Lookback Window Selection

The lookback window controls how "normal" is defined. Too short and you chase noise; too long and you miss regime changes.

| Method | Formula | When to Use |
|--------|---------|-------------|
| Half-life based | lookback = 2 * half_life | Default choice |
| Optimize | Walk-forward test 10..100 | When half-life is unreliable |
| Fixed | 20 (daily), 48 (hourly) | Quick-and-dirty baseline |

### Entry and Exit Thresholds

| Parameter | Conservative | Moderate | Aggressive |
|-----------|-------------|----------|------------|
| Entry z   | +/- 2.5     | +/- 2.0  | +/- 1.5    |
| Exit z    | +/- 0.25    | 0        | -/+ 0.5 (overshoot) |
| Stop z    | +/- 3.5     | +/- 3.0  | +/- 4.0    |
| Time stop | 3x half-life | 2x half-life | 4x half-life |

**Conservative**: Fewer trades, higher win rate, lower total return.
**Aggressive**: More trades, lower win rate, potentially higher return but more risk.

### Signal Generation Logic

```python
def generate_signals(z_scores: np.ndarray, entry_z: float = 2.0,
                     exit_z: float = 0.0, stop_z: float = 3.0) -> np.ndarray:
    """Generate signals: 1 (long), -1 (short), 0 (flat)."""
    positions = np.zeros(len(z_scores))
    pos = 0
    for i, z in enumerate(z_scores):
        if np.isnan(z): continue
        if pos == 0:
            if z < -entry_z: pos = 1
            elif z > entry_z: pos = -1
        elif pos == 1:
            if z > -exit_z or z < -stop_z: pos = 0
        elif pos == -1:
            if z < exit_z or z > stop_z: pos = 0
        positions[i] = pos
    return positions
```

---

## Position Sizing for Mean Reversion

### Linear Z-Score Scaling

Scale position size proportionally to z-score magnitude. More extreme deviations get larger positions because the expected reversion is larger.

```python
def mean_reversion_size(z: float, base_size: float,
                        entry_z: float = 2.0, max_scale: float = 2.0) -> float:
    """Position size scaled by z-score magnitude."""
    return base_size * min(abs(z) / entry_z, max_scale)
```

### Layered Entry

Instead of entering the full position at one z-score level, layer in:

| Layer | Z-Score | Size   | Cumulative |
|-------|---------|--------|------------|
| 1     | +/- 1.5 | 25%    | 25%        |
| 2     | +/- 2.0 | 25%    | 50%        |
| 3     | +/- 2.5 | 25%    | 75%        |
| 4     | +/- 3.0 | 25%    | 100%       |

This approach lowers average entry price but requires more capital allocation.

### Kelly Criterion for Mean Reversion

For a mean-reversion strategy with known win rate and payoff ratio:

```
kelly_fraction = win_rate - (1 - win_rate) / payoff_ratio
```

Typical mean-reversion strategies: win rate 60-70%, payoff ratio 0.8-1.2, Kelly fraction 0.15-0.35. Use half-Kelly in practice. See the `kelly-criterion` skill for detailed implementation.

---

## Pairs Trading Setup

### Step 1: Find Cointegrated Pairs

Use the `cointegration-analysis` skill or this quick test:

```python
def engle_granger_test(y: np.ndarray, x: np.ndarray) -> dict:
    """Engle-Granger cointegration: regress Y on X, ADF test residuals."""
    X = np.column_stack([np.ones(len(x)), x])
    coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
    spread = y - (coeffs[0] + coeffs[1] * x)
    adf_result = adf_test_manual(spread)  # from statistical_tests
    return {"hedge_ratio": coeffs[1], "spread": spread, "adf": adf_result}
```

### Step 2: Compute the Spread

```
spread_t = price_Y_t - beta * price_X_t
```

Where beta is the hedge ratio from cointegration regression. The spread should be stationary.

### Step 3: Trade the Spread

Apply the z-score framework to the spread:
- **Long spread** (buy Y, sell X) when spread z-score < -2
- **Short spread** (sell Y, buy X) when spread z-score > +2
- **Exit** when z-score returns to 0

### Step 4: Size Each Leg

For dollar-neutral pairs:
```python
notional_y = position_size
notional_x = position_size * beta  # Hedge ratio scaling
```

### Hedge Ratio Recalibration

- Recalculate the hedge ratio periodically (every half-life or 20-50 bars)
- Use rolling OLS or Kalman filter for dynamic hedge ratios
- A changing hedge ratio signals potential cointegration breakdown

---

## Risk Management

### Stop Loss Rules

| Stop Type | Trigger | Rationale |
|-----------|---------|-----------|
| Z-score stop | abs(z) > 3.0 | Mean reversion has failed |
| Time stop | Holding > 3x half-life | Taking too long to revert |
| Drawdown stop | Position loss > 2% of portfolio | Capital preservation |
| Regime stop | Regime changes to trending | Structural change |

### Maximum Holding Period

If a trade has not reverted within 3x the estimated half-life, the mean-reversion hypothesis may be wrong. Close the position regardless of P&L.

### Strategy-Level Circuit Breakers

| Metric | Threshold | Action |
|--------|-----------|--------|
| Consecutive losses | 5 in a row | Pause trading, retest stationarity |
| Daily drawdown | > 3% | Stop trading for the day |
| Weekly drawdown | > 5% | Reduce position sizes by 50% |
| Monthly drawdown | > 10% | Pause strategy, full review |

### Regime Filtering

Mean reversion only works in ranging markets. Use the `regime-detection` skill to:
1. Classify current regime (trending, ranging, volatile)
2. Only open new mean-reversion positions in ranging regime
3. Tighten stops when regime shifts toward trending
4. Close all positions immediately on regime change to volatile/crash

---

## Backtest Considerations

### Transaction Costs

Mean-reversion strategies trade frequently with small expected gains. Transaction costs can destroy profitability.

```python
# Example: factor in round-trip costs
cost_per_trade = 0.003  # 30 bps (DEX swap fee + slippage)
round_trip_cost = 2 * cost_per_trade  # 60 bps per round trip
min_expected_move = round_trip_cost * 2  # Need at least 120 bps expected reversion
```

### Required Trade Count

- Minimum 50 trades for any statistical significance
- 100+ trades for reliable Sharpe ratio estimation
- 200+ trades for confident drawdown estimation

### Walk-Forward Optimization

Never optimize parameters on the full sample. Use walk-forward:

1. **In-sample** (60%): Optimize lookback, entry z, exit z
2. **Out-of-sample** (40%): Test with fixed parameters
3. **Rolling window**: Slide the window forward and repeat
4. **Anchored**: Keep start fixed, extend end

### Common Backtest Mistakes

- **Lookahead bias**: Using future data to compute signals (e.g., full-sample mean)
- **Survivorship bias**: Only testing tokens that still exist
- **Parameter overfitting**: Optimizing too many parameters on too little data
- **Ignoring transaction costs**: Mean-reversion P&L is small; costs matter enormously
- **Not testing for regime changes**: A strategy that worked in 2024 ranging markets may fail in a 2025 bull run

---

## Crypto-Specific Adjustments

### Fee-Aware Thresholds

For DEX trading with 0.25-1% swap fees, adjust entry thresholds:

```python
# Only enter if expected reversion exceeds round-trip costs
min_entry_z = round_trip_cost_bps / rolling_std_bps
effective_entry_z = max(2.0, min_entry_z)
```

### 24/7 Markets

- No market close: overnight gaps do not exist, but weekend liquidity drops
- Use hourly or 4-hour bars for crypto mean reversion (not daily)
- Half-lives are typically measured in hours, not days

### Liquidity Constraints

- Check that sufficient liquidity exists for your position size
- Use the `liquidity-analysis` skill before entering
- Illiquid tokens have wider spreads that destroy mean-reversion profits
- Prefer tokens with > $100K daily volume for mean-reversion strategies
