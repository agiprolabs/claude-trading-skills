# Quantstats Library — Usage Guide

## Installation

```bash
uv pip install quantstats
```

Quantstats depends on pandas, numpy, scipy, matplotlib, and seaborn. These install automatically.

## Core Concepts

Quantstats operates on a pandas Series of **returns** (not prices). Index must be DatetimeIndex.

```python
import quantstats as qs
import pandas as pd

# From an equity curve
equity = pd.Series([10000, 10200, 10150, 10400], index=pd.date_range("2025-01-01", periods=4))
returns = equity.pct_change().dropna()
```

## Reports

### HTML Report

```python
qs.reports.html(
    returns,
    benchmark=None,          # Optional: benchmark returns Series
    output="report.html",    # File path for HTML output
    title="Strategy Report", # Report title
    rf=0.0,                  # Risk-free rate (annual)
    periods_per_year=252,    # Annualization factor
    compounded=True,         # Use geometric compounding
    download_filename=None,  # Custom download filename
)
```

The HTML report includes:
- Cumulative returns chart (with benchmark if provided)
- Drawdown chart
- Monthly returns heatmap
- Return distribution histogram
- Rolling Sharpe and rolling volatility
- Key statistics table
- Worst drawdowns table

### Console Full Report

```python
qs.reports.full(returns, benchmark=benchmark_returns)
```

Prints all metrics to stdout in a formatted table.

### Metrics-Only Report

```python
qs.reports.metrics(
    returns,
    benchmark=benchmark_returns,
    mode="full",  # "full", "basic", or a list of metric names
)
```

## Individual Statistics

All functions accept a returns Series and return a scalar.

### Return Metrics

```python
qs.stats.comp(returns)               # Total compounded return
qs.stats.cagr(returns)               # CAGR
qs.stats.expected_return(returns)     # Mean return (annualized)
qs.stats.best(returns)               # Best single period return
qs.stats.worst(returns)              # Worst single period return
qs.stats.avg_return(returns)         # Average period return
qs.stats.avg_win(returns)            # Average winning return
qs.stats.avg_loss(returns)           # Average losing return
qs.stats.win_rate(returns)           # Fraction of positive periods
```

### Risk Metrics

```python
qs.stats.volatility(returns)         # Annualized volatility
qs.stats.max_drawdown(returns)       # Maximum drawdown (negative)
qs.stats.value_at_risk(returns)      # Daily VaR at 95%
qs.stats.conditional_value_at_risk(returns)  # CVaR at 95%
qs.stats.tail_ratio(returns)         # Ratio of 95th to 5th percentile
qs.stats.common_sense_ratio(returns) # Profit factor * tail ratio
qs.stats.outlier_win_ratio(returns)  # Ratio of max win to average win
qs.stats.outlier_loss_ratio(returns) # Ratio of max loss to average loss
```

### Risk-Adjusted Ratios

```python
qs.stats.sharpe(returns, rf=0.0)     # Annualized Sharpe ratio
qs.stats.sortino(returns, rf=0.0)    # Annualized Sortino ratio
qs.stats.calmar(returns)             # Calmar ratio
qs.stats.omega(returns)              # Omega ratio (threshold=0)
qs.stats.information_ratio(returns, benchmark)  # Information ratio
qs.stats.treynor_ratio(returns, benchmark)      # Treynor ratio
qs.stats.gain_to_pain_ratio(returns) # Gain-to-pain ratio
qs.stats.risk_return_ratio(returns)  # Return / volatility
```

### Drawdown Analysis

```python
qs.stats.max_drawdown(returns)       # Worst drawdown
qs.stats.to_drawdown_series(returns) # Full drawdown time series
qs.stats.kelly_criterion(returns)    # Kelly optimal fraction
```

## Plotting Functions

Quantstats includes matplotlib-based plotting:

```python
# Cumulative returns
qs.plots.returns(returns, benchmark=benchmark_returns, savefig="returns.png")

# Drawdown periods
qs.plots.drawdown(returns, savefig="drawdown.png")

# Monthly returns heatmap
qs.plots.monthly_heatmap(returns, savefig="monthly.png")

# Distribution of returns
qs.plots.histogram(returns, savefig="histogram.png")

# Rolling Sharpe
qs.plots.rolling_sharpe(returns, savefig="rolling_sharpe.png")

# Rolling volatility
qs.plots.rolling_volatility(returns, savefig="rolling_vol.png")

# Yearly returns bar chart
qs.plots.yearly_returns(returns, savefig="yearly.png")

# All plots
qs.plots.snapshot(returns, savefig="snapshot.png")
```

All plotting functions accept `savefig` to save to file instead of displaying.

## Customization

### Risk-Free Rate

The `rf` parameter is an **annual** rate. Quantstats converts it per-period internally.

```python
# 5% annual risk-free rate
qs.stats.sharpe(returns, rf=0.05)
```

### Annualization

```python
# Hourly crypto data
qs.stats.sharpe(returns, rf=0.0, periods=8760)  # 24 * 365

# Weekly data
qs.stats.sharpe(returns, rf=0.0, periods=52)
```

### Compounding

```python
# Arithmetic vs geometric returns
qs.stats.cagr(returns, compounded=True)   # geometric (default)
qs.stats.cagr(returns, compounded=False)  # arithmetic
```

## Integration with Vectorbt

```python
import vectorbt as vbt
import quantstats as qs

# Run backtest
portfolio = vbt.Portfolio.from_signals(close, entries, exits, init_cash=10000)

# Extract returns
returns = portfolio.returns()

# Generate HTML report
qs.reports.html(returns, output="backtest_report.html", title="VBT Backtest")

# Or access individual metrics
sharpe = qs.stats.sharpe(returns)
sortino = qs.stats.sortino(returns)
max_dd = qs.stats.max_drawdown(returns)
```

## Common Patterns

### Strategy Comparison

```python
strategies = {
    "momentum": momentum_returns,
    "mean_rev": mean_reversion_returns,
    "hybrid": hybrid_returns,
}

for name, ret in strategies.items():
    print(f"\n{'='*40}")
    print(f"Strategy: {name}")
    print(f"  Sharpe:  {qs.stats.sharpe(ret):.2f}")
    print(f"  Sortino: {qs.stats.sortino(ret):.2f}")
    print(f"  Max DD:  {qs.stats.max_drawdown(ret):.2%}")
    print(f"  Calmar:  {qs.stats.calmar(ret):.2f}")
    print(f"  CAGR:    {qs.stats.cagr(ret):.2%}")
```

### Monthly Table from Quantstats

```python
# Get monthly returns as DataFrame
monthly = qs.stats.monthly_returns(returns)
print(monthly.to_string(float_format=lambda x: f"{x:.2%}"))
```

### Export All Metrics

```python
# Get all metrics as a DataFrame
all_metrics = qs.reports.metrics(returns, mode="full", display=False)
all_metrics.to_csv("strategy_metrics.csv")
```

## Limitations

- Quantstats assumes daily data by default. Always set `periods_per_year` for other frequencies.
- The HTML report renderer requires a graphical backend for matplotlib. On headless servers, set `matplotlib.use("Agg")` before importing quantstats.
- Benchmark data must be aligned (same dates) with strategy returns. Use `.reindex()` or `.align()` if needed.
- Large datasets (10+ years of daily data) may slow down the HTML report generation.
- Some metrics return `nan` or `inf` for very short return series (under 20 observations).

## Troubleshooting

**"No display" error on servers:**
```python
import matplotlib
matplotlib.use("Agg")
import quantstats as qs
```

**Benchmark alignment:**
```python
strategy, benchmark = strategy_returns.align(benchmark_returns, join="inner")
qs.reports.html(strategy, benchmark=benchmark, output="report.html")
```

**Missing dates:**
```python
# Fill missing dates with 0 returns
returns = returns.asfreq("D", fill_value=0.0)
```
