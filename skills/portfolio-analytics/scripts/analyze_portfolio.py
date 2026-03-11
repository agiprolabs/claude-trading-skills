#!/usr/bin/env python3
"""Comprehensive single-portfolio performance analysis.

Computes all major metrics from an equity curve: return metrics, risk metrics,
risk-adjusted ratios, drawdown analysis, rolling Sharpe, and monthly returns
table. Includes a --demo mode that generates a 1-year synthetic equity curve.

Usage:
    python scripts/analyze_portfolio.py --demo
    python scripts/analyze_portfolio.py --csv equity.csv --value-col portfolio_value

Dependencies:
    uv pip install pandas numpy

Environment Variables:
    None required.
"""

import argparse
import sys
from typing import Optional

import numpy as np
import pandas as pd


# ── Return Metrics ──────────────────────────────────────────────────


def total_return(equity: pd.Series) -> float:
    """Total return from start to end.

    Args:
        equity: Time-indexed portfolio value series.

    Returns:
        Total return as a decimal (e.g., 0.25 for 25%).
    """
    return (equity.iloc[-1] / equity.iloc[0]) - 1


def cagr(equity: pd.Series) -> float:
    """Compound Annual Growth Rate.

    Args:
        equity: Time-indexed portfolio value series.

    Returns:
        Annualized compound growth rate.
    """
    days = (equity.index[-1] - equity.index[0]).days
    if days <= 0:
        return 0.0
    return (equity.iloc[-1] / equity.iloc[0]) ** (365.25 / days) - 1


def daily_mean_return(returns: pd.Series) -> float:
    """Average daily return.

    Args:
        returns: Daily return series.

    Returns:
        Mean daily return.
    """
    return float(returns.mean())


def annualized_mean_return(
    returns: pd.Series, periods_per_year: int = 252
) -> float:
    """Annualized arithmetic mean return.

    Args:
        returns: Period return series.
        periods_per_year: Annualization factor.

    Returns:
        Annualized mean return.
    """
    return float(returns.mean() * periods_per_year)


# ── Risk Metrics ────────────────────────────────────────────────────


def annualized_volatility(
    returns: pd.Series, periods_per_year: int = 252
) -> float:
    """Annualized standard deviation of returns.

    Args:
        returns: Period return series.
        periods_per_year: Annualization factor.

    Returns:
        Annualized volatility.
    """
    return float(returns.std() * np.sqrt(periods_per_year))


def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical Value at Risk.

    Args:
        returns: Period return series.
        confidence: Confidence level (e.g., 0.95).

    Returns:
        VaR as a positive number representing potential loss.
    """
    return float(-np.percentile(returns.dropna(), (1 - confidence) * 100))


def historical_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Conditional VaR (Expected Shortfall).

    Args:
        returns: Period return series.
        confidence: Confidence level.

    Returns:
        CVaR as a positive number.
    """
    var = historical_var(returns, confidence)
    tail = returns[returns <= -var]
    if len(tail) == 0:
        return var
    return float(-tail.mean())


def max_drawdown(equity: pd.Series) -> float:
    """Maximum peak-to-trough decline.

    Args:
        equity: Time-indexed portfolio value series.

    Returns:
        Max drawdown as a negative decimal (e.g., -0.15 for 15% decline).
    """
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return float(dd.min())


def drawdown_series(equity: pd.Series) -> pd.Series:
    """Full drawdown time series.

    Args:
        equity: Time-indexed portfolio value series.

    Returns:
        Series of drawdown values (negative or zero).
    """
    peak = equity.cummax()
    return (equity - peak) / peak


def max_time_underwater(equity: pd.Series) -> int:
    """Longest consecutive period below previous peak.

    Args:
        equity: Time-indexed portfolio value series.

    Returns:
        Number of periods spent in the longest drawdown.
    """
    dd = drawdown_series(equity)
    is_underwater = dd < 0
    if not is_underwater.any():
        return 0
    groups = (~is_underwater).cumsum()
    underwater_lengths = is_underwater.groupby(groups).sum()
    return int(underwater_lengths.max())


# ── Risk-Adjusted Ratios ───────────────────────────────────────────


def sharpe_ratio(
    returns: pd.Series, rf: float = 0.0, periods_per_year: int = 252
) -> float:
    """Annualized Sharpe ratio.

    Args:
        returns: Period return series.
        rf: Risk-free rate per period.
        periods_per_year: Annualization factor.

    Returns:
        Sharpe ratio.
    """
    excess = returns - rf
    if excess.std() == 0:
        return 0.0
    return float((excess.mean() / excess.std()) * np.sqrt(periods_per_year))


def sortino_ratio(
    returns: pd.Series, rf: float = 0.0, periods_per_year: int = 252
) -> float:
    """Annualized Sortino ratio (downside deviation only).

    Args:
        returns: Period return series.
        rf: Risk-free rate per period.
        periods_per_year: Annualization factor.

    Returns:
        Sortino ratio.
    """
    excess = returns - rf
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    return float((excess.mean() / downside.std()) * np.sqrt(periods_per_year))


def calmar_ratio(equity: pd.Series, periods_per_year: int = 252) -> float:
    """Calmar ratio: CAGR / |max drawdown|.

    Args:
        equity: Time-indexed portfolio value series.
        periods_per_year: Annualization factor (unused, CAGR uses calendar).

    Returns:
        Calmar ratio.
    """
    annual_return = cagr(equity)
    mdd = abs(max_drawdown(equity))
    if mdd == 0:
        return float("inf") if annual_return > 0 else 0.0
    return annual_return / mdd


def omega_ratio(returns: pd.Series, threshold: float = 0.0) -> float:
    """Omega ratio: probability-weighted gains / losses.

    Args:
        returns: Period return series.
        threshold: Threshold return (default 0).

    Returns:
        Omega ratio.
    """
    excess = returns - threshold
    gains = excess[excess > 0].sum()
    losses = abs(excess[excess <= 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 1.0
    return float(gains / losses)


def information_ratio(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int = 252,
) -> float:
    """Information ratio: active return / tracking error.

    Args:
        returns: Strategy return series.
        benchmark_returns: Benchmark return series (aligned).
        periods_per_year: Annualization factor.

    Returns:
        Information ratio.
    """
    active = returns - benchmark_returns
    if active.std() == 0:
        return 0.0
    return float((active.mean() / active.std()) * np.sqrt(periods_per_year))


# ── Rolling Analysis ───────────────────────────────────────────────


def rolling_sharpe(
    returns: pd.Series,
    window: int = 63,
    rf: float = 0.0,
    periods_per_year: int = 252,
) -> pd.Series:
    """Rolling annualized Sharpe ratio.

    Args:
        returns: Period return series.
        window: Rolling window size in periods.
        rf: Risk-free rate per period.
        periods_per_year: Annualization factor.

    Returns:
        Series of rolling Sharpe values.
    """
    excess = returns - rf
    roll_mean = excess.rolling(window).mean()
    roll_std = excess.rolling(window).std()
    return (roll_mean / roll_std) * np.sqrt(periods_per_year)


# ── Trade-Level Analysis ───────────────────────────────────────────


def trade_statistics(pnl: pd.Series) -> dict:
    """Compute trade-level statistics from PnL values.

    Args:
        pnl: Series where each element is a trade's PnL.

    Returns:
        Dictionary of trade-level metrics.
    """
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    total = len(pnl)

    win_rate = len(wins) / total if total > 0 else 0.0
    avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
    avg_loss = float(losses.mean()) if len(losses) > 0 else 0.0
    largest_win = float(wins.max()) if len(wins) > 0 else 0.0
    largest_loss = float(losses.min()) if len(losses) > 0 else 0.0
    gross_profit = float(wins.sum()) if len(wins) > 0 else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) > 0 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    expectancy = float(pnl.mean()) if total > 0 else 0.0

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


# ── Monthly Returns Table ──────────────────────────────────────────


def monthly_returns_table(returns: pd.Series) -> pd.DataFrame:
    """Create a month-by-year returns table.

    Args:
        returns: Daily return series with DatetimeIndex.

    Returns:
        DataFrame with years as rows, months as columns, plus Annual.
    """
    monthly = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    table_data: dict[int, dict[str, float]] = {}
    month_names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    for dt, val in monthly.items():
        year = dt.year
        month = dt.month
        if year not in table_data:
            table_data[year] = {}
        table_data[year][month_names[month - 1]] = val

    table = pd.DataFrame.from_dict(table_data, orient="index")
    table = table.reindex(columns=month_names)

    # Annual column
    annual = returns.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    for dt, val in annual.items():
        if dt.year in table.index:
            table.loc[dt.year, "Annual"] = val

    return table


# ── Demo Data Generation ───────────────────────────────────────────


def generate_demo_equity(
    start_date: str = "2025-01-01",
    periods: int = 252,
    initial_capital: float = 10000.0,
    annual_return: float = 0.25,
    annual_vol: float = 0.30,
    seed: int = 42,
) -> pd.Series:
    """Generate a synthetic equity curve for demonstration.

    Args:
        start_date: Start date string.
        periods: Number of trading days.
        initial_capital: Starting portfolio value.
        annual_return: Target annualized return.
        annual_vol: Target annualized volatility.
        seed: Random seed for reproducibility.

    Returns:
        Time-indexed equity curve Series.
    """
    rng = np.random.default_rng(seed)
    daily_mu = annual_return / 252
    daily_sigma = annual_vol / np.sqrt(252)

    daily_returns = rng.normal(daily_mu, daily_sigma, periods)
    prices = initial_capital * np.cumprod(1 + daily_returns)
    prices = np.insert(prices, 0, initial_capital)

    dates = pd.bdate_range(start=start_date, periods=len(prices))
    return pd.Series(prices, index=dates, name="equity")


def generate_demo_trades(
    n_trades: int = 100,
    win_rate: float = 0.55,
    avg_win_size: float = 150.0,
    avg_loss_size: float = 100.0,
    seed: int = 42,
) -> pd.Series:
    """Generate synthetic trade PnL data.

    Args:
        n_trades: Number of trades to generate.
        win_rate: Fraction of winning trades.
        avg_win_size: Average winning trade PnL.
        avg_loss_size: Average losing trade PnL (as positive number).
        seed: Random seed.

    Returns:
        Series of trade PnL values.
    """
    rng = np.random.default_rng(seed)
    pnl = []
    for _ in range(n_trades):
        if rng.random() < win_rate:
            pnl.append(rng.exponential(avg_win_size))
        else:
            pnl.append(-rng.exponential(avg_loss_size))
    return pd.Series(pnl, name="trade_pnl")


# ── Report Formatting ──────────────────────────────────────────────


def print_separator(title: str, width: int = 60) -> None:
    """Print a section separator."""
    print(f"\n{'─' * width}")
    print(f"  {title}")
    print(f"{'─' * width}")


def format_pct(value: float, decimals: int = 2) -> str:
    """Format a decimal as percentage string."""
    return f"{value * 100:.{decimals}f}%"


def format_ratio(value: float, decimals: int = 2) -> str:
    """Format a ratio value."""
    if value == float("inf"):
        return "inf"
    if value == float("-inf"):
        return "-inf"
    return f"{value:.{decimals}f}"


def print_full_report(equity: pd.Series, trade_pnl: Optional[pd.Series] = None) -> None:
    """Print a comprehensive portfolio performance report.

    Args:
        equity: Time-indexed portfolio value series.
        trade_pnl: Optional series of individual trade PnL values.
    """
    returns = equity.pct_change().dropna()
    start = equity.index[0].strftime("%Y-%m-%d")
    end = equity.index[-1].strftime("%Y-%m-%d")
    days = (equity.index[-1] - equity.index[0]).days

    print("=" * 60)
    print("  PORTFOLIO PERFORMANCE REPORT")
    print(f"  Period: {start} to {end} ({days} calendar days)")
    print(f"  Data points: {len(equity)}")
    print("=" * 60)

    # ── Return Metrics
    print_separator("RETURN METRICS")
    print(f"  Initial Capital:       ${equity.iloc[0]:>12,.2f}")
    print(f"  Final Value:           ${equity.iloc[-1]:>12,.2f}")
    print(f"  Total Return:          {format_pct(total_return(equity)):>12}")
    print(f"  CAGR:                  {format_pct(cagr(equity)):>12}")
    print(f"  Daily Mean Return:     {format_pct(daily_mean_return(returns), 4):>12}")
    print(f"  Ann. Mean Return:      {format_pct(annualized_mean_return(returns)):>12}")
    print(f"  Best Day:              {format_pct(float(returns.max())):>12}")
    print(f"  Worst Day:             {format_pct(float(returns.min())):>12}")

    # ── Risk Metrics
    print_separator("RISK METRICS")
    print(f"  Ann. Volatility:       {format_pct(annualized_volatility(returns)):>12}")
    print(f"  Daily VaR (95%):       {format_pct(historical_var(returns, 0.95)):>12}")
    print(f"  Daily CVaR (95%):      {format_pct(historical_cvar(returns, 0.95)):>12}")
    print(f"  Daily VaR (99%):       {format_pct(historical_var(returns, 0.99)):>12}")
    print(f"  Daily CVaR (99%):      {format_pct(historical_cvar(returns, 0.99)):>12}")
    print(f"  Max Drawdown:          {format_pct(max_drawdown(equity)):>12}")
    print(f"  Max Time Underwater:   {max_time_underwater(equity):>9} days")

    # ── Drawdown Details
    dd = drawdown_series(equity)
    worst_dd_date = dd.idxmin()
    # Find the peak before worst drawdown
    peak_before = equity.loc[:worst_dd_date].idxmax()
    print(f"  Worst DD Peak Date:    {peak_before.strftime('%Y-%m-%d'):>12}")
    print(f"  Worst DD Trough Date:  {worst_dd_date.strftime('%Y-%m-%d'):>12}")

    # ── Risk-Adjusted Ratios
    print_separator("RISK-ADJUSTED RATIOS")
    sr = sharpe_ratio(returns)
    so = sortino_ratio(returns)
    cr = calmar_ratio(equity)
    om = omega_ratio(returns)

    print(f"  Sharpe Ratio:          {format_ratio(sr):>12}")
    print(f"  Sortino Ratio:         {format_ratio(so):>12}")
    print(f"  Calmar Ratio:          {format_ratio(cr):>12}")
    print(f"  Omega Ratio:           {format_ratio(om):>12}")

    # Sharpe interpretation
    if sr > 2.0:
        interp = "Excellent"
    elif sr > 1.0:
        interp = "Good"
    elif sr > 0.5:
        interp = "Acceptable"
    elif sr > 0:
        interp = "Poor"
    else:
        interp = "Negative"
    print(f"  Sharpe Interpretation: {interp:>12}")

    # ── Rolling Sharpe Summary
    print_separator("ROLLING SHARPE (63-DAY)")
    rs = rolling_sharpe(returns, window=63)
    rs_clean = rs.dropna()
    if len(rs_clean) > 0:
        print(f"  Current:               {format_ratio(float(rs_clean.iloc[-1])):>12}")
        print(f"  Mean:                  {format_ratio(float(rs_clean.mean())):>12}")
        print(f"  Min:                   {format_ratio(float(rs_clean.min())):>12}")
        print(f"  Max:                   {format_ratio(float(rs_clean.max())):>12}")
        print(f"  Std Dev:               {format_ratio(float(rs_clean.std())):>12}")
        pct_positive = (rs_clean > 0).mean()
        print(f"  % Positive:            {format_pct(float(pct_positive)):>12}")
    else:
        print("  Insufficient data for 63-day rolling window.")

    # ── Return Distribution
    print_separator("RETURN DISTRIBUTION")
    print(f"  Skewness:              {float(returns.skew()):>12.3f}")
    print(f"  Kurtosis (excess):     {float(returns.kurtosis()):>12.3f}")
    pos_days = (returns > 0).sum()
    neg_days = (returns < 0).sum()
    zero_days = (returns == 0).sum()
    print(f"  Positive Days:         {pos_days:>9} ({format_pct(pos_days / len(returns))})")
    print(f"  Negative Days:         {neg_days:>9} ({format_pct(neg_days / len(returns))})")
    print(f"  Zero Days:             {zero_days:>9}")

    # ── Monthly Returns Table
    print_separator("MONTHLY RETURNS")
    mt = monthly_returns_table(returns)
    if len(mt) > 0:
        formatted = mt.map(
            lambda x: f"{x * 100:6.2f}%" if pd.notna(x) else "    N/A"
        )
        print(formatted.to_string())

    # ── Trade-Level Statistics
    if trade_pnl is not None:
        print_separator("TRADE-LEVEL STATISTICS")
        stats = trade_statistics(trade_pnl)
        print(f"  Total Trades:          {stats['total_trades']:>12}")
        print(f"  Win Rate:              {format_pct(stats['win_rate']):>12}")
        print(f"  Avg Win:               ${stats['avg_win']:>11,.2f}")
        print(f"  Avg Loss:              ${stats['avg_loss']:>11,.2f}")
        print(f"  Largest Win:           ${stats['largest_win']:>11,.2f}")
        print(f"  Largest Loss:          ${stats['largest_loss']:>11,.2f}")
        print(f"  Profit Factor:         {format_ratio(stats['profit_factor']):>12}")
        print(f"  Expectancy:            ${stats['expectancy']:>11,.2f}")
        print(f"  Gross Profit:          ${stats['gross_profit']:>11,.2f}")
        print(f"  Gross Loss:            ${stats['gross_loss']:>11,.2f}")
        print(f"  Net Profit:            ${stats['gross_profit'] - stats['gross_loss']:>11,.2f}")

    print(f"\n{'=' * 60}")
    print("  Note: This is analytical output for informational purposes.")
    print("  It does not constitute financial advice.")
    print(f"{'=' * 60}\n")


# ── CSV Loading ─────────────────────────────────────────────────────


def load_equity_from_csv(
    filepath: str,
    value_col: str = "portfolio_value",
    date_col: Optional[str] = None,
) -> pd.Series:
    """Load equity curve from CSV file.

    Args:
        filepath: Path to CSV file.
        value_col: Column name for portfolio values.
        date_col: Column name for dates (None = use index).

    Returns:
        Time-indexed equity Series.

    Raises:
        FileNotFoundError: If CSV file does not exist.
        KeyError: If specified columns are not found.
    """
    df = pd.read_csv(filepath)

    if date_col and date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.set_index(date_col)
    elif df.columns[0].lower() in ("date", "datetime", "timestamp", "time"):
        date_name = df.columns[0]
        df[date_name] = pd.to_datetime(df[date_name])
        df = df.set_index(date_name)
    else:
        df.index = pd.to_datetime(df.index)

    if value_col not in df.columns:
        available = ", ".join(df.columns.tolist())
        raise KeyError(
            f"Column '{value_col}' not found. Available columns: {available}"
        )

    return df[value_col].sort_index()


# ── Main ────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Portfolio performance analysis tool."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with synthetic demo data (1-year equity curve).",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Path to CSV file with equity curve data.",
    )
    parser.add_argument(
        "--value-col",
        type=str,
        default="portfolio_value",
        help="Column name for portfolio values in CSV (default: portfolio_value).",
    )
    parser.add_argument(
        "--date-col",
        type=str,
        default=None,
        help="Column name for dates in CSV (default: auto-detect).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()

    if args.demo:
        print("Generating 1-year synthetic equity curve (seed=42)...")
        print("  Annual return target: 25%, Annual vol target: 30%\n")
        equity = generate_demo_equity(
            start_date="2025-01-01",
            periods=252,
            initial_capital=10000.0,
            annual_return=0.25,
            annual_vol=0.30,
            seed=42,
        )
        trade_pnl = generate_demo_trades(n_trades=100, seed=42)
        print_full_report(equity, trade_pnl=trade_pnl)

    elif args.csv:
        try:
            equity = load_equity_from_csv(
                args.csv,
                value_col=args.value_col,
                date_col=args.date_col,
            )
        except FileNotFoundError:
            print(f"Error: File not found: {args.csv}")
            sys.exit(1)
        except KeyError as e:
            print(f"Error: {e}")
            sys.exit(1)

        print(f"Loaded {len(equity)} data points from {args.csv}\n")
        print_full_report(equity)

    else:
        print("Usage:")
        print("  python scripts/analyze_portfolio.py --demo")
        print("  python scripts/analyze_portfolio.py --csv equity.csv --value-col portfolio_value")
        sys.exit(1)


if __name__ == "__main__":
    main()
