---
name: vectorbt
description: High-performance vectorized backtesting with parameter optimization, portfolio simulation, and rich performance metrics
---

# Vectorized Backtesting with vectorbt

## Overview

vectorbt is a Python library for **vectorized backtesting** — running strategy simulations using NumPy/pandas array operations instead of bar-by-bar loops. This makes it 100–1000x faster than event-driven frameworks (backtrader, zipline), enabling parameter optimization across thousands of combinations in seconds.

**Key strengths:**
- Blazing speed via NumPy vectorization
- Built-in parameter grid search and optimization
- 50+ built-in performance metrics (Sharpe, Sortino, Calmar, max drawdown, profit factor)
- Rich plotting (equity curves, drawdowns, trade markers, heatmaps)
- Native pandas integration — your data stays in DataFrames throughout

## Installation

```bash
uv pip install vectorbt pandas numpy
```

vectorbt pulls in pandas, NumPy, and Plotly automatically. For technical indicators, also install pandas-ta:

```bash
uv pip install vectorbt pandas-ta
```

## Core Concepts

### 1. Signals — Boolean Entry/Exit Arrays

Strategies in vectorbt are expressed as boolean pandas Series (or arrays) indicating where to enter and exit positions:

```python
import vectorbt as vbt
import pandas as pd

# Entry: buy when fast EMA crosses above slow EMA
entries = fast_ema > slow_ema
# Exit: sell when fast EMA crosses below slow EMA
exits = fast_ema < slow_ema
```

vectorbt resolves conflicting signals automatically (you can't enter while already in a position).

### 2. Portfolio — The Backtesting Engine

`vbt.Portfolio.from_signals()` is the primary backtesting function. It takes price data and entry/exit signals, simulates trades, and computes performance:

```python
pf = vbt.Portfolio.from_signals(
    close=close_prices,
    entries=entries,
    exits=exits,
    init_cash=10_000,
    fees=0.003,       # 0.3% per trade
    slippage=0.005,   # 0.5% slippage
    freq="1h",        # hourly data
)
```

### 3. Metrics — Built-in Performance Analysis

```python
# Full stats summary
print(pf.stats())

# Individual metrics
print(f"Total Return: {pf.total_return():.2%}")
print(f"Sharpe Ratio: {pf.sharpe_ratio():.3f}")
print(f"Max Drawdown: {pf.max_drawdown():.2%}")
print(f"Win Rate:     {pf.trades.win_rate():.2%}")
```

### 4. Parameter Optimization — Grid Search in Seconds

Pass arrays instead of scalars to test many parameter combos simultaneously:

```python
import numpy as np

fast_periods = np.arange(5, 25, 2)   # 10 values
slow_periods = np.arange(20, 60, 5)  # 8 values

fast_ma = vbt.MA.run(close, fast_periods, short_name="fast")
slow_ma = vbt.MA.run(close, slow_periods, short_name="slow")

# This creates 80 parameter combinations automatically
entries = fast_ma.ma_crossed_above(slow_ma)
exits = fast_ma.ma_crossed_below(slow_ma)
```

## Basic Workflow

### Step 1: Load OHLCV Data

```python
import pandas as pd

# From CSV
df = pd.read_csv("ohlcv.csv", parse_dates=["timestamp"], index_col="timestamp")
close = df["close"]

# From Yahoo Finance (traditional markets)
btc = vbt.YFData.download("BTC-USD", start="2023-01-01", end="2025-01-01")
close = btc.get("Close")
```

For Solana tokens, fetch data via the `birdeye-api` skill and load into a DataFrame.

### Step 2: Compute Indicators

```python
import pandas_ta as ta

# Using pandas-ta (see pandas-ta skill)
df.ta.ema(length=12, append=True)
df.ta.ema(length=26, append=True)
df.ta.rsi(length=14, append=True)
df.ta.bbands(length=20, std=2, append=True)

# Or using vectorbt built-ins
rsi = vbt.RSI.run(close, window=14)
bbands = vbt.BBANDS.run(close, window=20, alpha=2)
```

### Step 3: Generate Entry/Exit Signals

```python
# EMA crossover
entries = df["EMA_12"] > df["EMA_26"]
exits = df["EMA_12"] < df["EMA_26"]

# RSI mean reversion
entries = rsi.rsi_below(30)
exits = rsi.rsi_above(70)
```

### Step 4: Run Backtest

```python
pf = vbt.Portfolio.from_signals(
    close=close,
    entries=entries,
    exits=exits,
    init_cash=10_000,
    fees=0.003,
    slippage=0.005,
    size=0.95,               # use 95% of available cash
    size_type="percent",
    freq="1h",
)
```

### Step 5: Analyze Results

```python
# Summary statistics
print(pf.stats())

# Trade-level analysis
trades = pf.trades.records_readable
print(f"\nTrade count: {len(trades)}")
print(f"Avg holding period: {trades['Duration'].mean()}")

# Equity curve
pf.plot().show()

# Drawdown chart
pf.drawdowns.plot().show()
```

## Key Portfolio Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `close` | Price series (pd.Series or DataFrame) | `df["close"]` |
| `entries` | Boolean entry signals | `fast > slow` |
| `exits` | Boolean exit signals | `fast < slow` |
| `init_cash` | Starting capital | `10_000` |
| `fees` | Fee per trade (fraction) | `0.003` (0.3%) |
| `slippage` | Slippage per trade (fraction) | `0.005` (0.5%) |
| `size` | Position size | `0.95` |
| `size_type` | How to interpret size | `"percent"`, `"amount"`, `"value"` |
| `freq` | Data frequency | `"1h"`, `"4h"`, `"1d"` |
| `direction` | Trade direction | `"both"`, `"longonly"`, `"shortonly"` |
| `accumulate` | Allow adding to positions | `False` |
| `sl_stop` | Stop-loss level (fraction) | `0.05` (5%) |
| `tp_stop` | Take-profit level (fraction) | `0.10` (10%) |

## Performance Metrics

### Returns
- `total_return()` — cumulative return over the period
- `annualized_return()` — annualized compound return
- `daily_returns()` — Series of daily returns

### Risk
- `max_drawdown()` — maximum peak-to-trough decline
- `annualized_volatility()` — annualized standard deviation of returns
- `value_at_risk()` — VaR at specified confidence level

### Risk-Adjusted
- `sharpe_ratio()` — excess return per unit volatility
- `sortino_ratio()` — excess return per unit downside deviation
- `calmar_ratio()` — annualized return / max drawdown
- `omega_ratio()` — probability-weighted gain/loss ratio

### Trade Statistics
- `trades.win_rate()` — fraction of profitable trades
- `trades.profit_factor()` — gross profit / gross loss
- `trades.expectancy()` — average P&L per trade
- `trades.avg_winning_trade()` — mean profit on winners
- `trades.avg_losing_trade()` — mean loss on losers
- `trades.count()` — total number of completed trades

## Parameter Optimization

### Grid Search

```python
fast_windows = [5, 8, 12, 15, 20]
slow_windows = [20, 26, 30, 40, 50]

# Run all 25 combos at once
fast_ma = vbt.MA.run(close, fast_windows, short_name="fast")
slow_ma = vbt.MA.run(close, slow_windows, short_name="slow")

entries = fast_ma.ma_crossed_above(slow_ma)
exits = fast_ma.ma_crossed_below(slow_ma)

pf = vbt.Portfolio.from_signals(close, entries, exits, fees=0.003)

# Find best params by Sharpe
sharpe = pf.sharpe_ratio()
best_idx = sharpe.idxmax()
print(f"Best params: {best_idx}, Sharpe: {sharpe[best_idx]:.3f}")
```

### Walk-Forward Validation

Always validate optimized parameters on out-of-sample data:

```python
# Split: 70% train, 30% test
split_idx = int(len(close) * 0.7)
train_close = close.iloc[:split_idx]
test_close = close.iloc[split_idx:]

# Optimize on training data
# ... (run grid search on train_close)

# Validate best params on test data
# ... (run single backtest on test_close with best params)
```

See `references/optimization_guide.md` for detailed walk-forward methodology and overfitting prevention.

## Crypto-Specific Considerations

### 24/7 Markets
Crypto markets never close. Use hourly or minute-based frequencies, not business-day frequencies:
```python
# Correct for crypto
pf = vbt.Portfolio.from_signals(close, entries, exits, freq="1h")

# Wrong — business days assume market closures
# pf = vbt.Portfolio.from_signals(close, entries, exits, freq="1B")
```

### Realistic Fees
DEX swaps on Solana typically cost 0.25–1% including AMM fees. CEX spot fees are 0.05–0.1%.
```python
# Solana DEX (conservative)
pf = vbt.Portfolio.from_signals(close, entries, exits, fees=0.005)

# CEX spot
pf = vbt.Portfolio.from_signals(close, entries, exits, fees=0.001)
```

### Slippage
Low-liquidity tokens can have 1–5% slippage. Always model this:
```python
# High-liquidity (SOL, ETH): 0.1–0.5%
pf = vbt.Portfolio.from_signals(close, entries, exits, slippage=0.003)

# Low-liquidity memecoins: 1–3%
pf = vbt.Portfolio.from_signals(close, entries, exits, slippage=0.02)
```

### Short History
Many tokens have less than 1 year of data. Be cautious about annualizing metrics from short samples.

## Common Strategy Patterns

### EMA Crossover
```python
fast = vbt.MA.run(close, 12, short_name="fast")
slow = vbt.MA.run(close, 26, short_name="slow")
entries = fast.ma_crossed_above(slow)
exits = fast.ma_crossed_below(slow)
```

### RSI Mean Reversion
```python
rsi = vbt.RSI.run(close, 14)
entries = rsi.rsi_crossed_below(30)
exits = rsi.rsi_crossed_above(70)
```

### Bollinger Band Breakout
```python
bb = vbt.BBANDS.run(close, window=20, alpha=2)
entries = close > bb.upper
exits = close < bb.lower
```

### Stop-Loss and Take-Profit
```python
pf = vbt.Portfolio.from_signals(
    close, entries, exits,
    sl_stop=0.05,    # 5% stop-loss
    tp_stop=0.10,    # 10% take-profit
)
```

## Related Skills

- **pandas-ta** — Technical indicator computation (feeds vectorbt signals)
- **birdeye-api** — Fetch Solana token OHLCV data for backtesting
- **trading-visualization** — Advanced chart generation for backtest results
- **portfolio-analytics** — Deeper portfolio-level risk/return analysis
- **position-sizing** — Optimal position sizing methodology
- **risk-management** — Portfolio-level risk guardrails
- **regime-detection** — Market regime awareness for adaptive strategies

## Files

### References
- `references/api_guide.md` — Complete vectorbt API reference for Portfolio, indicators, plotting, and data loading
- `references/optimization_guide.md` — Grid search, walk-forward validation, overfitting prevention, and optimization best practices

### Scripts
- `scripts/backtest_example.py` — Three-strategy backtest comparison using synthetic data (EMA crossover, RSI mean reversion, Bollinger breakout)
- `scripts/parameter_sweep.py` — EMA crossover parameter grid search with walk-forward validation
