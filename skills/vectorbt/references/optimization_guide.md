# vectorbt Optimization Guide

## Grid Search Methodology

Grid search tests every combination of parameter values. vectorbt makes this fast by vectorizing all combinations in a single pass.

### Step-by-Step Grid Search

```python
import numpy as np
import vectorbt as vbt

# 1. Define parameter ranges
fast_windows = np.arange(5, 25, 2)    # [5, 7, 9, ..., 23] → 10 values
slow_windows = np.arange(20, 60, 5)   # [20, 25, 30, ..., 55] → 8 values
# Total combinations: 10 × 8 = 80

# 2. Run indicators with array parameters
fast_ma = vbt.MA.run(close, fast_windows, short_name="fast")
slow_ma = vbt.MA.run(close, slow_windows, short_name="slow")

# 3. Generate signals (broadcasted across all combos)
entries = fast_ma.ma_crossed_above(slow_ma)
exits = fast_ma.ma_crossed_below(slow_ma)

# 4. Run portfolio for all combos simultaneously
pf = vbt.Portfolio.from_signals(
    close, entries, exits,
    init_cash=10_000,
    fees=0.003,
    slippage=0.005,
    freq="1h",
)

# 5. Extract metrics
sharpe = pf.sharpe_ratio()
total_return = pf.total_return()
max_dd = pf.max_drawdown()
trade_count = pf.trades.count()

# 6. Find best parameters
best_sharpe_idx = sharpe.idxmax()
print(f"Best Sharpe: {sharpe[best_sharpe_idx]:.3f} at {best_sharpe_idx}")
```

### Filtering Results

```python
# Only consider combos with enough trades
valid = trade_count >= 20
filtered_sharpe = sharpe[valid]
best = filtered_sharpe.idxmax()

# Only consider combos where fast < slow (sensible constraint)
# This is handled automatically if your parameter ranges don't overlap
```

### Heatmap Visualization

```python
# Reshape to 2D for heatmap
sharpe_2d = sharpe.unstack(level="slow_window")
sharpe_2d.vbt.heatmap(
    title="Sharpe Ratio: Fast vs Slow EMA",
).show()
```

## Walk-Forward Optimization

In-sample optimization always overfits. Walk-forward validation is the minimum standard for credible results.

### Concept

1. Split data into sequential windows
2. Optimize parameters on each training window
3. Test optimized parameters on the next (unseen) window
4. Aggregate out-of-sample results

### Implementation

```python
import pandas as pd
import numpy as np
import vectorbt as vbt

def walk_forward_backtest(
    close: pd.Series,
    fast_windows: list[int],
    slow_windows: list[int],
    train_frac: float = 0.7,
    n_splits: int = 3,
    fees: float = 0.003,
    slippage: float = 0.005,
) -> dict:
    """Run walk-forward optimization on EMA crossover strategy.

    Args:
        close: Price series.
        fast_windows: Fast EMA periods to test.
        slow_windows: Slow EMA periods to test.
        train_frac: Fraction of each window used for training.
        n_splits: Number of walk-forward windows.
        fees: Trading fee fraction.
        slippage: Slippage fraction.

    Returns:
        Dictionary with in-sample and out-of-sample results.
    """
    total_len = len(close)
    window_size = total_len // n_splits
    results = []

    for i in range(n_splits):
        start = i * window_size
        end = min(start + window_size, total_len)
        window = close.iloc[start:end]

        split = int(len(window) * train_frac)
        train = window.iloc[:split]
        test = window.iloc[split:]

        # Optimize on training data
        fast_ma = vbt.MA.run(train, fast_windows, short_name="fast")
        slow_ma = vbt.MA.run(train, slow_windows, short_name="slow")
        entries = fast_ma.ma_crossed_above(slow_ma)
        exits = fast_ma.ma_crossed_below(slow_ma)

        pf_train = vbt.Portfolio.from_signals(
            train, entries, exits,
            fees=fees, slippage=slippage, freq="1h",
        )
        best_params = pf_train.sharpe_ratio().idxmax()

        # Validate on test data with best params
        best_fast, best_slow = best_params
        fast_test = vbt.MA.run(test, best_fast, short_name="fast")
        slow_test = vbt.MA.run(test, best_slow, short_name="slow")
        ent_test = fast_test.ma_crossed_above(slow_test)
        ext_test = fast_test.ma_crossed_below(slow_test)

        pf_test = vbt.Portfolio.from_signals(
            test, ent_test, ext_test,
            fees=fees, slippage=slippage, freq="1h",
        )

        results.append({
            "window": i,
            "best_fast": best_fast,
            "best_slow": best_slow,
            "is_sharpe": pf_train.sharpe_ratio()[best_params],
            "oos_sharpe": pf_test.sharpe_ratio(),
            "is_return": pf_train.total_return()[best_params],
            "oos_return": pf_test.total_return(),
        })

    return results
```

### Interpreting Walk-Forward Results

| Metric | Good Sign | Warning Sign |
|--------|-----------|--------------|
| OOS Sharpe / IS Sharpe | > 0.5 | < 0.3 |
| OOS returns | Positive across most windows | Negative in most windows |
| Parameter stability | Same params chosen repeatedly | Different params every window |
| OOS drawdown | Smaller than IS drawdown | Much larger than IS |

## Overfitting Prevention

### 1. Minimum Trade Count
Never trust results with fewer than 30 trades per parameter combination. Ideally 100+.

```python
# Filter out low-trade-count results
valid_mask = pf.trades.count() >= 30
sharpe_filtered = pf.sharpe_ratio()[valid_mask]
```

### 2. Parameter Stability
If optimal parameters change dramatically across walk-forward windows, the strategy is likely overfit.

```python
# Check if best params are consistent
for r in wf_results:
    print(f"Window {r['window']}: fast={r['best_fast']}, slow={r['best_slow']}")
# Consistent: fast=12 in all windows
# Overfit: fast=5, 21, 9, 17 across windows
```

### 3. Simplicity Preference
Fewer parameters = less overfitting. Prefer 2-parameter strategies over 5-parameter ones.

| Parameters | Risk Level | Minimum Data |
|------------|------------|--------------|
| 1-2 | Low | 6 months hourly |
| 3-4 | Medium | 1+ year hourly |
| 5+ | High | 2+ years hourly |

### 4. Out-of-Sample Decay Budget
Expect 30–60% Sharpe decay from in-sample to out-of-sample. If your IS Sharpe is 1.5, expect OOS Sharpe of 0.6–1.0.

### 5. Deflated Sharpe Ratio
When testing many parameter combos, the best Sharpe is inflated by multiple testing. Apply a haircut:

```python
import numpy as np

def deflated_sharpe(sharpe_best: float, n_trials: int, n_obs: int) -> float:
    """Estimate probability that best Sharpe is genuine.

    Args:
        sharpe_best: Best observed Sharpe ratio.
        n_trials: Number of parameter combinations tested.
        n_obs: Number of return observations.

    Returns:
        Approximate deflated Sharpe (lower is more skeptical).
    """
    expected_max = np.sqrt(2 * np.log(n_trials))
    return sharpe_best - expected_max / np.sqrt(n_obs)
```

## Common Optimization Mistakes

### 1. Optimizing on Full Dataset
Using the entire dataset for optimization means there's no unseen data to validate on. Always hold out at least 30% for testing.

### 2. Cherry-Picking Time Periods
Testing only on bull markets (or bear markets) gives misleading results. Use the full available history.

### 3. Ignoring Transaction Costs
Strategies that look great with zero fees often break even or lose money with realistic fees. Always include fees and slippage.

### 4. Annualizing Short Samples
A 50% return over 2 weeks annualizes to ~130,000%. This is meaningless. Require at least 6 months of data before annualizing.

### 5. Ignoring Drawdown
A strategy with 200% return and 80% max drawdown is not tradeable. Always check max drawdown alongside returns.

### 6. Data Snooping
If you tried 50 strategy ideas before finding one that works, you've effectively run 50 optimizations. Apply the deflated Sharpe correction.

## Combinatorial Purged Cross-Validation (CPCV)

For advanced users, CPCV provides more robust validation than simple walk-forward:

1. Divide data into N groups
2. Select all combinations of N-k groups for training, k groups for testing
3. Purge overlapping data between train and test (remove a buffer)
4. Run optimization on each training set, validate on each test set
5. Aggregate all out-of-sample results

This produces more test paths and is harder to overfit than single walk-forward splits. Implementation requires significant code — see the `regime-detection` skill for related statistical validation techniques.

## Recommended Workflow

1. **Explore**: Run a coarse grid search (5-10 values per parameter) on 80% of data
2. **Narrow**: Identify the promising region, run a fine grid search
3. **Validate**: Walk-forward test with 3-5 splits
4. **Stress test**: Check OOS Sharpe decay, parameter stability, trade count
5. **Deploy cautiously**: Start with small size, monitor live performance vs backtest
6. **Re-optimize**: Re-run optimization monthly or quarterly with new data
