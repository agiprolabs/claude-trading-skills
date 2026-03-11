---
name: portfolio-analytics
description: Portfolio-level performance measurement including return metrics, risk metrics, risk-adjusted ratios, rolling analysis, and HTML reports
---

# Portfolio Analytics

Compute portfolio-level performance metrics from equity curves and trade logs. Covers return metrics, risk metrics, risk-adjusted ratios, drawdown analysis, rolling windows, benchmark comparison, trade-level statistics, and automated HTML report generation via quantstats.

## When to Use This Skill

- After backtesting a strategy (e.g., from `vectorbt` or `strategy-framework`)
- Comparing multiple strategies or parameter sets side-by-side
- Generating investor-ready performance reports
- Evaluating live trading performance against benchmarks
- Assessing risk-adjusted returns for portfolio allocation decisions

## Prerequisites

```bash
uv pip install pandas numpy quantstats
```

## Input Format

All analytics start from an **equity curve** — a time-indexed Series of portfolio values:

```python
import pandas as pd
import numpy as np

# From a backtest
equity = pd.Series(
    [10000, 10150, 10080, 10320, 10510, 10440, 10680],
    index=pd.date_range("2025-01-01", periods=7, freq="D"),
    name="strategy_equity"
)

# Convert to returns
returns = equity.pct_change().dropna()
```

## Return Metrics

### Total Return

```python
total_return = (equity.iloc[-1] / equity.iloc[0]) - 1
```

### CAGR (Compound Annual Growth Rate)

```python
days = (equity.index[-1] - equity.index[0]).days
cagr = (equity.iloc[-1] / equity.iloc[0]) ** (365.25 / days) - 1
```

### Daily Mean Return

```python
daily_mean = returns.mean()
annualized_mean = daily_mean * 252  # trading days
```

### Cumulative Returns

```python
cumulative = (1 + returns).cumprod() - 1
```

## Risk Metrics

### Annualized Volatility

```python
daily_vol = returns.std()
annual_vol = daily_vol * np.sqrt(252)
```

### Value at Risk (VaR)

Historical VaR at a given confidence level:

```python
def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Compute historical VaR.

    Args:
        returns: Daily return series.
        confidence: Confidence level (e.g., 0.95 for 95%).

    Returns:
        VaR as a positive number representing potential loss.
    """
    return -np.percentile(returns, (1 - confidence) * 100)
```

### Conditional VaR (CVaR / Expected Shortfall)

```python
def historical_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Mean of returns below the VaR threshold."""
    var = historical_var(returns, confidence)
    return -returns[returns <= -var].mean()
```

### Maximum Drawdown

```python
def max_drawdown(equity: pd.Series) -> float:
    """Maximum peak-to-trough decline."""
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    return drawdown.min()  # negative number

def drawdown_series(equity: pd.Series) -> pd.Series:
    """Full drawdown time series."""
    peak = equity.cummax()
    return (equity - peak) / peak
```

### Time Underwater

```python
def time_underwater(equity: pd.Series) -> int:
    """Longest consecutive period below previous peak (in days)."""
    dd = drawdown_series(equity)
    is_underwater = dd < 0
    groups = (~is_underwater).cumsum()
    underwater_periods = is_underwater.groupby(groups).sum()
    return int(underwater_periods.max()) if len(underwater_periods) > 0 else 0
```

## Risk-Adjusted Ratios

### Sharpe Ratio

```python
def sharpe_ratio(
    returns: pd.Series,
    rf: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """Annualized Sharpe ratio.

    Args:
        returns: Period returns.
        rf: Risk-free rate per period.
        periods_per_year: Annualization factor.

    Returns:
        Annualized Sharpe ratio.
    """
    excess = returns - rf
    if excess.std() == 0:
        return 0.0
    return (excess.mean() / excess.std()) * np.sqrt(periods_per_year)
```

### Sortino Ratio

```python
def sortino_ratio(
    returns: pd.Series,
    rf: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """Annualized Sortino ratio (penalizes only downside vol)."""
    excess = returns - rf
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    return (excess.mean() / downside.std()) * np.sqrt(periods_per_year)
```

### Calmar Ratio

```python
def calmar_ratio(equity: pd.Series, periods_per_year: int = 252) -> float:
    """CAGR divided by max drawdown (absolute value)."""
    returns = equity.pct_change().dropna()
    days = (equity.index[-1] - equity.index[0]).days
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (365.25 / days) - 1
    mdd = abs(max_drawdown(equity))
    if mdd == 0:
        return float("inf") if cagr > 0 else 0.0
    return cagr / mdd
```

### Omega Ratio

```python
def omega_ratio(
    returns: pd.Series,
    threshold: float = 0.0
) -> float:
    """Ratio of probability-weighted gains to losses."""
    excess = returns - threshold
    gains = excess[excess > 0].sum()
    losses = abs(excess[excess <= 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 1.0
    return gains / losses
```

### Information Ratio

```python
def information_ratio(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int = 252
) -> float:
    """Excess return per unit of tracking error."""
    active = returns - benchmark_returns
    if active.std() == 0:
        return 0.0
    return (active.mean() / active.std()) * np.sqrt(periods_per_year)
```

## Rolling Analysis

### Rolling Sharpe

```python
def rolling_sharpe(
    returns: pd.Series,
    window: int = 63,
    rf: float = 0.0,
    periods_per_year: int = 252
) -> pd.Series:
    """Rolling annualized Sharpe ratio."""
    excess = returns - rf
    roll_mean = excess.rolling(window).mean()
    roll_std = excess.rolling(window).std()
    return (roll_mean / roll_std) * np.sqrt(periods_per_year)
```

### Rolling Max Drawdown

```python
def rolling_max_drawdown(equity: pd.Series, window: int = 252) -> pd.Series:
    """Rolling max drawdown over a fixed window."""
    result = pd.Series(index=equity.index, dtype=float)
    for i in range(window, len(equity)):
        window_eq = equity.iloc[i - window:i + 1]
        peak = window_eq.cummax()
        dd = (window_eq - peak) / peak
        result.iloc[i] = dd.min()
    return result
```

## Trade-Level Analysis

When you have individual trade records:

```python
def trade_statistics(pnl: pd.Series) -> dict:
    """Compute trade-level statistics from a series of trade PnL values.

    Args:
        pnl: Series where each value is the PnL of one trade.

    Returns:
        Dictionary of trade statistics.
    """
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    total = len(pnl)

    win_rate = len(wins) / total if total > 0 else 0.0
    avg_win = wins.mean() if len(wins) > 0 else 0.0
    avg_loss = losses.mean() if len(losses) > 0 else 0.0
    largest_win = wins.max() if len(wins) > 0 else 0.0
    largest_loss = losses.min() if len(losses) > 0 else 0.0

    gross_profit = wins.sum() if len(wins) > 0 else 0.0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    expectancy = pnl.mean() if total > 0 else 0.0

    return {
        "total_trades": total,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
    }
```

## Monthly / Yearly Return Tables

```python
def monthly_returns_table(returns: pd.Series) -> pd.DataFrame:
    """Pivot returns into a month-by-year table.

    Returns:
        DataFrame with years as rows, months (1-12) as columns,
        and an Annual column.
    """
    monthly = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    table = monthly.groupby([monthly.index.year, monthly.index.month]).first()
    table = table.unstack(level=1)
    table.columns = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]
    # Annual column
    annual = returns.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    table["Annual"] = annual.values[:len(table)]
    return table
```

## Benchmark Comparison

```python
def benchmark_comparison(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    rf: float = 0.0
) -> dict:
    """Compare strategy to benchmark across key metrics."""
    strat_eq = (1 + strategy_returns).cumprod()
    bench_eq = (1 + benchmark_returns).cumprod()

    return {
        "strategy_total_return": strat_eq.iloc[-1] - 1,
        "benchmark_total_return": bench_eq.iloc[-1] - 1,
        "strategy_sharpe": sharpe_ratio(strategy_returns, rf),
        "benchmark_sharpe": sharpe_ratio(benchmark_returns, rf),
        "strategy_max_dd": max_drawdown(strat_eq),
        "benchmark_max_dd": max_drawdown(bench_eq),
        "information_ratio": information_ratio(strategy_returns, benchmark_returns),
        "correlation": strategy_returns.corr(benchmark_returns),
        "beta": (
            strategy_returns.cov(benchmark_returns)
            / benchmark_returns.var()
        ),
        "alpha": (
            strategy_returns.mean()
            - (strategy_returns.cov(benchmark_returns) / benchmark_returns.var())
            * benchmark_returns.mean()
        ) * 252,
    }
```

## Quantstats HTML Reports

Generate investor-ready HTML reports with one function call:

```python
import quantstats as qs

# From returns Series
qs.reports.html(
    returns,
    benchmark=benchmark_returns,  # optional
    output="report.html",
    title="My Strategy",
    rf=0.0,
    periods_per_year=252
)

# Individual metrics
print(f"Sharpe: {qs.stats.sharpe(returns):.2f}")
print(f"Sortino: {qs.stats.sortino(returns):.2f}")
print(f"Max DD: {qs.stats.max_drawdown(returns):.2%}")
print(f"Calmar: {qs.stats.calmar(returns):.2f}")

# Console tearsheet
qs.reports.full(returns)
```

See `references/quantstats_guide.md` for full API reference and customization.

## Integration with Vectorbt

```python
import vectorbt as vbt

# After running a vectorbt backtest
portfolio = vbt.Portfolio.from_signals(close, entries, exits, init_cash=10000)

# Extract equity curve
equity = portfolio.value()
returns = portfolio.returns()

# Use quantstats
qs.reports.html(returns, output="backtest_report.html")
```

## Files

| File | Description |
|------|-------------|
| `references/metrics_guide.md` | Formulas, derivations, annualization factors, interpretation benchmarks |
| `references/quantstats_guide.md` | Quantstats library API, customization, integration patterns |
| `scripts/analyze_portfolio.py` | Single portfolio analysis with all metrics, rolling stats, monthly table |
| `scripts/compare_strategies.py` | Multi-strategy comparison with ranking by risk-adjusted metrics |

## Related Skills

- `vectorbt` — Backtesting engine that produces equity curves for analysis
- `risk-management` — Portfolio-level risk guardrails and allocation
- `position-sizing` — Optimal position sizing using portfolio metrics
- `kelly-criterion` — Optimal growth rate sizing from win rate and payoff
- `trading-visualization` — Chart generation for equity curves and drawdowns
