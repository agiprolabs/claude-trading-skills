# vectorbt API Guide

## Portfolio.from_signals()

The primary backtesting entry point. Takes price data and boolean entry/exit signals, simulates trades, returns a Portfolio object.

```python
pf = vbt.Portfolio.from_signals(
    close,              # pd.Series or DataFrame of close prices
    entries,            # boolean Series/DataFrame — True = enter long
    exits,              # boolean Series/DataFrame — True = exit long
    short_entries=None, # boolean — True = enter short
    short_exits=None,   # boolean — True = exit short
    init_cash=100.0,    # starting capital (float or array)
    fees=0.0,           # fee fraction per trade (0.001 = 0.1%)
    slippage=0.0,       # slippage fraction (0.005 = 0.5%)
    size=np.inf,        # position size (inf = use all available cash)
    size_type="amount", # "amount", "value", "percent"
    direction="longonly",  # "longonly", "shortonly", "both"
    accumulate=False,   # allow adding to existing position
    sl_stop=None,       # stop-loss fraction (0.05 = 5%)
    tp_stop=None,       # take-profit fraction (0.10 = 10%)
    freq=None,          # data frequency ("1h", "1d", etc.)
    upon_opposite_entry="reversereduce",  # action on conflicting signals
)
```

### Size Type Options
| Value | Meaning | Example |
|-------|---------|---------|
| `"amount"` | Number of units (shares/tokens) | `size=100` → buy 100 tokens |
| `"value"` | Dollar/SOL value | `size=1000` → buy $1000 worth |
| `"percent"` | Fraction of available cash | `size=0.95` → use 95% of cash |

### Direction Options
| Value | Meaning |
|-------|---------|
| `"longonly"` | Only long positions (default) |
| `"shortonly"` | Only short positions |
| `"both"` | Allow both long and short |

## Portfolio.from_orders()

For complex order logic beyond simple signals:

```python
pf = vbt.Portfolio.from_orders(
    close=close,
    size=order_sizes,       # Series of order sizes (+buy, -sell)
    size_type="amount",
    init_cash=10_000,
    fees=0.003,
    freq="1h",
)
```

Use `from_orders()` when you need variable position sizes, partial exits, or order-level logic that signals can't express.

## Portfolio Object — Key Methods

### Summary Statistics
```python
pf.stats()                    # Full stats dictionary
pf.stats(agg_func=None)      # Stats for each column (multi-param)
```

### Return Metrics
```python
pf.total_return()             # Cumulative return (float)
pf.annualized_return()        # CAGR
pf.returns()                  # pd.Series of period returns
pf.cumulative_returns()       # pd.Series of cumulative returns
pf.daily_returns()            # Daily return series
```

### Risk Metrics
```python
pf.max_drawdown()             # Maximum peak-to-trough decline
pf.max_drawdown_duration()    # Longest drawdown in time
pf.annualized_volatility()    # Annualized std dev of returns
pf.value_at_risk()            # Value at Risk
pf.conditional_value_at_risk()  # CVaR / Expected Shortfall
```

### Risk-Adjusted Metrics
```python
pf.sharpe_ratio()             # Sharpe ratio (default rf=0)
pf.sortino_ratio()            # Sortino ratio
pf.calmar_ratio()             # Calmar ratio
pf.omega_ratio()              # Omega ratio
pf.information_ratio()        # Information ratio (vs benchmark)
```

### Trade Analysis
```python
pf.trades.count()             # Number of completed trades
pf.trades.win_rate()          # Fraction of winners
pf.trades.profit_factor()     # Gross profit / gross loss
pf.trades.expectancy()        # Average P&L per trade
pf.trades.avg_winning_trade() # Mean winner P&L
pf.trades.avg_losing_trade()  # Mean loser P&L
pf.trades.records_readable    # DataFrame of all trades
```

### Portfolio Value
```python
pf.value()                    # Portfolio value over time
pf.cash()                     # Cash balance over time
pf.asset_value()              # Asset value over time
```

## Plotting

```python
# Equity curve
pf.plot().show()

# Drawdowns
pf.drawdowns.plot().show()

# Trade markers on price chart
pf.trades.plot().show()

# Cumulative returns
pf.cumulative_returns().vbt.plot().show()
```

### Heatmaps for Parameter Sweeps
```python
# 2D heatmap of metric across parameter grid
sharpe = pf.sharpe_ratio()
sharpe_2d = sharpe.unstack()  # reshape to 2D
sharpe_2d.vbt.heatmap(
    x_level="fast_window",
    y_level="slow_window",
    title="Sharpe Ratio by EMA Parameters"
).show()
```

## Built-in Indicators

### Moving Average — vbt.MA
```python
ma = vbt.MA.run(close, window=[10, 20, 50], short_name="ma")
ma.ma                          # MA values (multi-column if array window)
ma.ma_above(close)             # Boolean: MA > close
ma.ma_below(close)             # Boolean: MA < close
ma.ma_crossed_above(close)     # Boolean: MA crossed above close
ma.ma_crossed_below(close)     # Boolean: MA crossed below close
```

### RSI — vbt.RSI
```python
rsi = vbt.RSI.run(close, window=14)
rsi.rsi                        # RSI values
rsi.rsi_above(70)              # Boolean: RSI > 70
rsi.rsi_below(30)              # Boolean: RSI < 30
rsi.rsi_crossed_above(70)      # Boolean: RSI crossed above 70
rsi.rsi_crossed_below(30)      # Boolean: RSI crossed below 30
```

### Bollinger Bands — vbt.BBANDS
```python
bb = vbt.BBANDS.run(close, window=20, alpha=2)
bb.upper                       # Upper band
bb.middle                      # Middle band (SMA)
bb.lower                       # Lower band
bb.bandwidth                   # Band width
bb.percent_b                   # %B indicator
```

### ATR — vbt.ATR
```python
atr = vbt.ATR.run(high, low, close, window=14)
atr.atr                        # ATR values
```

## Parameter Arrays and Grid Search

When you pass an array for an indicator parameter, vectorbt computes all values simultaneously and returns a multi-column DataFrame:

```python
# Single window → single-column output
ma_20 = vbt.MA.run(close, window=20)

# Array of windows → multi-column output
ma_multi = vbt.MA.run(close, window=[10, 20, 50])
# Result has columns: (10,), (20,), (50,)
```

For 2D grid search, use two indicators with different parameters:

```python
fast_ma = vbt.MA.run(close, [5, 10, 15], short_name="fast")
slow_ma = vbt.MA.run(close, [20, 30, 40], short_name="slow")

# Broadcasting creates 3x3=9 combinations
entries = fast_ma.ma_crossed_above(slow_ma)
exits = fast_ma.ma_crossed_below(slow_ma)
# entries/exits have MultiIndex columns: (fast, slow) pairs
```

## Data Loading

### Yahoo Finance (Traditional Assets)
```python
data = vbt.YFData.download(
    "BTC-USD",
    start="2023-01-01",
    end="2025-01-01",
    interval="1d",
)
close = data.get("Close")
```

### Custom Data (Crypto / Solana)
```python
import pandas as pd

# Load from CSV or API response
df = pd.DataFrame({
    "timestamp": timestamps,
    "open": opens,
    "high": highs,
    "low": lows,
    "close": closes,
    "volume": volumes,
})
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.set_index("timestamp").sort_index()

# Use close prices for backtesting
close = df["close"]
```

For Solana token data, see the `birdeye-api` skill for fetching OHLCV data via the Birdeye API.

## Tips

- **Multi-column operations**: When entries/exits have multiple columns (from parameter arrays), `Portfolio.from_signals()` automatically runs all combinations.
- **Memory**: Large parameter sweeps with long time series can use significant RAM. Start with coarse grids and narrow down.
- **Frequency**: Always set `freq` correctly — it affects annualization of Sharpe, volatility, and other time-scaled metrics.
- **NaN handling**: vectorbt treats NaN signals as "no action". Indicator warm-up periods produce NaN automatically.
