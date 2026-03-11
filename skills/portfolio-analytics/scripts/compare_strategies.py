#!/usr/bin/env python3
"""Multi-strategy performance comparison tool.

Computes metrics for multiple equity curves side-by-side, ranks strategies
by risk-adjusted metrics, and identifies the best performer. Includes a
--demo mode that generates three synthetic strategies with different profiles.

Usage:
    python scripts/compare_strategies.py --demo
    python scripts/compare_strategies.py --csv strat1.csv strat2.csv strat3.csv

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


# ── Metric Functions ────────────────────────────────────────────────


def total_return(equity: pd.Series) -> float:
    """Total return from start to end."""
    return float((equity.iloc[-1] / equity.iloc[0]) - 1)


def cagr(equity: pd.Series) -> float:
    """Compound Annual Growth Rate."""
    days = (equity.index[-1] - equity.index[0]).days
    if days <= 0:
        return 0.0
    return float((equity.iloc[-1] / equity.iloc[0]) ** (365.25 / days) - 1)


def annualized_volatility(
    returns: pd.Series, periods_per_year: int = 252
) -> float:
    """Annualized standard deviation."""
    return float(returns.std() * np.sqrt(periods_per_year))


def max_drawdown(equity: pd.Series) -> float:
    """Maximum peak-to-trough decline (negative)."""
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return float(dd.min())


def sharpe_ratio(
    returns: pd.Series, rf: float = 0.0, periods_per_year: int = 252
) -> float:
    """Annualized Sharpe ratio."""
    excess = returns - rf
    if excess.std() == 0:
        return 0.0
    return float((excess.mean() / excess.std()) * np.sqrt(periods_per_year))


def sortino_ratio(
    returns: pd.Series, rf: float = 0.0, periods_per_year: int = 252
) -> float:
    """Annualized Sortino ratio."""
    excess = returns - rf
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    return float((excess.mean() / downside.std()) * np.sqrt(periods_per_year))


def calmar_ratio(equity: pd.Series) -> float:
    """CAGR / |max drawdown|."""
    annual_return = cagr(equity)
    mdd = abs(max_drawdown(equity))
    if mdd == 0:
        return float("inf") if annual_return > 0 else 0.0
    return annual_return / mdd


def omega_ratio(returns: pd.Series, threshold: float = 0.0) -> float:
    """Probability-weighted gains / losses."""
    excess = returns - threshold
    gains = excess[excess > 0].sum()
    losses = abs(excess[excess <= 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 1.0
    return float(gains / losses)


def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical VaR as positive number."""
    return float(-np.percentile(returns.dropna(), (1 - confidence) * 100))


def win_rate(returns: pd.Series) -> float:
    """Fraction of positive-return periods."""
    if len(returns) == 0:
        return 0.0
    return float((returns > 0).sum() / len(returns))


# ── Strategy Metrics Computation ────────────────────────────────────


def compute_all_metrics(
    name: str, equity: pd.Series, rf: float = 0.0
) -> dict:
    """Compute all metrics for a single strategy.

    Args:
        name: Strategy name for labeling.
        equity: Time-indexed portfolio value series.
        rf: Risk-free rate per period.

    Returns:
        Dictionary of metric name -> value.
    """
    returns = equity.pct_change().dropna()
    return {
        "name": name,
        "total_return": total_return(equity),
        "cagr": cagr(equity),
        "ann_volatility": annualized_volatility(returns),
        "max_drawdown": max_drawdown(equity),
        "sharpe": sharpe_ratio(returns, rf),
        "sortino": sortino_ratio(returns, rf),
        "calmar": calmar_ratio(equity),
        "omega": omega_ratio(returns),
        "var_95": historical_var(returns, 0.95),
        "win_rate": win_rate(returns),
        "final_value": float(equity.iloc[-1]),
        "n_periods": len(returns),
    }


# ── Demo Data ───────────────────────────────────────────────────────


def generate_strategy_equity(
    start_date: str,
    periods: int,
    initial_capital: float,
    annual_return: float,
    annual_vol: float,
    seed: int,
) -> pd.Series:
    """Generate synthetic equity curve.

    Args:
        start_date: Start date string.
        periods: Number of trading days.
        initial_capital: Starting value.
        annual_return: Target annualized return.
        annual_vol: Target annualized volatility.
        seed: Random seed.

    Returns:
        Time-indexed equity Series.
    """
    rng = np.random.default_rng(seed)
    daily_mu = annual_return / 252
    daily_sigma = annual_vol / np.sqrt(252)
    daily_returns = rng.normal(daily_mu, daily_sigma, periods)
    prices = initial_capital * np.cumprod(1 + daily_returns)
    prices = np.insert(prices, 0, initial_capital)
    dates = pd.bdate_range(start=start_date, periods=len(prices))
    return pd.Series(prices, index=dates)


def generate_demo_strategies() -> dict[str, pd.Series]:
    """Generate three demo strategies with different risk/return profiles.

    Returns:
        Dictionary of strategy name -> equity Series.
    """
    strategies = {
        "Momentum": generate_strategy_equity(
            start_date="2025-01-01",
            periods=252,
            initial_capital=10000.0,
            annual_return=0.40,
            annual_vol=0.45,
            seed=42,
        ),
        "Mean Reversion": generate_strategy_equity(
            start_date="2025-01-01",
            periods=252,
            initial_capital=10000.0,
            annual_return=0.20,
            annual_vol=0.15,
            seed=123,
        ),
        "Trend Following": generate_strategy_equity(
            start_date="2025-01-01",
            periods=252,
            initial_capital=10000.0,
            annual_return=0.30,
            annual_vol=0.35,
            seed=456,
        ),
    }
    return strategies


# ── Comparison Report ───────────────────────────────────────────────


def format_val(value: float, fmt: str = "pct") -> str:
    """Format a value for display.

    Args:
        value: Numeric value to format.
        fmt: Format type ('pct', 'ratio', 'dollar', 'int').

    Returns:
        Formatted string.
    """
    if value == float("inf"):
        return "inf"
    if value == float("-inf"):
        return "-inf"
    if fmt == "pct":
        return f"{value * 100:.2f}%"
    elif fmt == "ratio":
        return f"{value:.2f}"
    elif fmt == "dollar":
        return f"${value:,.2f}"
    elif fmt == "int":
        return f"{int(value)}"
    return f"{value:.4f}"


def print_comparison_table(metrics_list: list[dict]) -> None:
    """Print side-by-side comparison of strategy metrics.

    Args:
        metrics_list: List of metric dictionaries from compute_all_metrics.
    """
    col_width = 18
    name_width = 22

    # Header
    header = f"{'Metric':<{name_width}}"
    for m in metrics_list:
        header += f"{m['name']:>{col_width}}"
    print(header)
    print("─" * (name_width + col_width * len(metrics_list)))

    # Rows
    rows = [
        ("Total Return", "total_return", "pct"),
        ("CAGR", "cagr", "pct"),
        ("Ann. Volatility", "ann_volatility", "pct"),
        ("Max Drawdown", "max_drawdown", "pct"),
        ("Sharpe Ratio", "sharpe", "ratio"),
        ("Sortino Ratio", "sortino", "ratio"),
        ("Calmar Ratio", "calmar", "ratio"),
        ("Omega Ratio", "omega", "ratio"),
        ("VaR (95%)", "var_95", "pct"),
        ("Win Rate", "win_rate", "pct"),
        ("Final Value", "final_value", "dollar"),
        ("Periods", "n_periods", "int"),
    ]

    for label, key, fmt in rows:
        row = f"{label:<{name_width}}"
        for m in metrics_list:
            row += f"{format_val(m[key], fmt):>{col_width}}"
        print(row)


def print_rankings(metrics_list: list[dict]) -> None:
    """Print strategy rankings by key metrics.

    Args:
        metrics_list: List of metric dictionaries.
    """
    ranking_metrics = [
        ("Sharpe Ratio", "sharpe", True),
        ("Sortino Ratio", "sortino", True),
        ("Calmar Ratio", "calmar", True),
        ("Total Return", "total_return", True),
        ("Max Drawdown", "max_drawdown", True),  # higher (less negative) is better
        ("Ann. Volatility", "ann_volatility", False),  # lower is better
    ]

    print(f"\n{'Metric':<22}{'#1':<20}{'#2':<20}{'#3+':<20}")
    print("─" * 82)

    rank_scores: dict[str, float] = {m["name"]: 0.0 for m in metrics_list}

    for label, key, higher_is_better in ranking_metrics:
        sorted_strats = sorted(
            metrics_list,
            key=lambda x: x[key],
            reverse=higher_is_better,
        )
        row = f"{label:<22}"
        for i, s in enumerate(sorted_strats):
            row += f"{s['name']:<20}"
            # Award points: 3 for 1st, 2 for 2nd, 1 for 3rd, etc.
            rank_scores[s["name"]] += len(sorted_strats) - i
        print(row)

    # Overall ranking
    print(f"\n{'─' * 60}")
    print("  OVERALL RANKING (by accumulated rank points)")
    print(f"{'─' * 60}")
    overall = sorted(rank_scores.items(), key=lambda x: x[1], reverse=True)
    for rank, (name, score) in enumerate(overall, 1):
        marker = " ← Best Risk-Adjusted" if rank == 1 else ""
        print(f"  #{rank}  {name:<25} ({score:.0f} points){marker}")


def print_correlation_matrix(strategies: dict[str, pd.Series]) -> None:
    """Print return correlation matrix between strategies.

    Args:
        strategies: Dictionary of strategy name -> equity Series.
    """
    returns_df = pd.DataFrame(
        {name: eq.pct_change().dropna() for name, eq in strategies.items()}
    )
    # Align on common dates
    returns_df = returns_df.dropna()
    corr = returns_df.corr()

    print(f"\n{'─' * 60}")
    print("  RETURN CORRELATION MATRIX")
    print(f"{'─' * 60}")

    col_width = 18
    name_width = 18
    header = f"{'':<{name_width}}"
    for name in corr.columns:
        header += f"{name:>{col_width}}"
    print(header)

    for row_name in corr.index:
        row = f"{row_name:<{name_width}}"
        for col_name in corr.columns:
            row += f"{corr.loc[row_name, col_name]:>{col_width}.3f}"
        print(row)


def print_full_comparison(strategies: dict[str, pd.Series]) -> None:
    """Print complete multi-strategy comparison report.

    Args:
        strategies: Dictionary of strategy name -> equity Series.
    """
    print("=" * 70)
    print("  MULTI-STRATEGY COMPARISON REPORT")
    print(f"  Strategies: {', '.join(strategies.keys())}")
    print("=" * 70)

    # Compute metrics
    metrics_list = []
    for name, equity in strategies.items():
        metrics = compute_all_metrics(name, equity)
        metrics_list.append(metrics)

    # Side-by-side metrics table
    print(f"\n{'─' * 60}")
    print("  PERFORMANCE METRICS")
    print(f"{'─' * 60}")
    print_comparison_table(metrics_list)

    # Rankings
    print(f"\n{'─' * 60}")
    print("  STRATEGY RANKINGS")
    print(f"{'─' * 60}")
    print_rankings(metrics_list)

    # Correlation
    print_correlation_matrix(strategies)

    # Diversification benefit
    print(f"\n{'─' * 60}")
    print("  EQUAL-WEIGHT PORTFOLIO")
    print(f"{'─' * 60}")
    returns_df = pd.DataFrame(
        {name: eq.pct_change().dropna() for name, eq in strategies.items()}
    )
    returns_df = returns_df.dropna()
    equal_weight_returns = returns_df.mean(axis=1)
    eq_equity = (1 + equal_weight_returns).cumprod() * 10000
    eq_metrics = compute_all_metrics("Equal Weight", eq_equity)

    print(f"  Total Return:    {format_val(eq_metrics['total_return'], 'pct')}")
    print(f"  CAGR:            {format_val(eq_metrics['cagr'], 'pct')}")
    print(f"  Sharpe:          {format_val(eq_metrics['sharpe'], 'ratio')}")
    print(f"  Max Drawdown:    {format_val(eq_metrics['max_drawdown'], 'pct')}")
    print(f"  Calmar:          {format_val(eq_metrics['calmar'], 'ratio')}")
    print(f"  Ann. Volatility: {format_val(eq_metrics['ann_volatility'], 'pct')}")

    # Check if equal-weight beats all individual strategies on Sharpe
    individual_sharpes = [m["sharpe"] for m in metrics_list]
    if eq_metrics["sharpe"] > max(individual_sharpes):
        print("\n  Equal-weight portfolio achieves HIGHER Sharpe than any")
        print("  individual strategy — diversification benefit confirmed.")
    else:
        best_individual = max(metrics_list, key=lambda x: x["sharpe"])
        print(f"\n  Best individual strategy ({best_individual['name']}) has higher")
        print("  Sharpe than equal-weight blend.")

    print(f"\n{'=' * 70}")
    print("  Note: This is analytical output for informational purposes.")
    print("  It does not constitute financial advice.")
    print(f"{'=' * 70}\n")


# ── CSV Loading ─────────────────────────────────────────────────────


def load_strategies_from_csv(
    filepaths: list[str],
    value_col: str = "portfolio_value",
    date_col: Optional[str] = None,
) -> dict[str, pd.Series]:
    """Load multiple equity curves from CSV files.

    Args:
        filepaths: List of CSV file paths.
        value_col: Column name for portfolio values.
        date_col: Column name for dates.

    Returns:
        Dictionary of filename (without ext) -> equity Series.
    """
    strategies = {}
    for fp in filepaths:
        df = pd.read_csv(fp)
        name = fp.rsplit("/", 1)[-1].rsplit(".", 1)[0]

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
            print(f"Warning: '{value_col}' not found in {fp}. Available: {available}")
            continue

        strategies[name] = df[value_col].sort_index()

    return strategies


# ── Main ────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Compare multiple trading strategies."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with three synthetic demo strategies.",
    )
    parser.add_argument(
        "--csv",
        nargs="+",
        type=str,
        default=None,
        help="Paths to CSV files (one per strategy).",
    )
    parser.add_argument(
        "--value-col",
        type=str,
        default="portfolio_value",
        help="Column name for portfolio values (default: portfolio_value).",
    )
    parser.add_argument(
        "--date-col",
        type=str,
        default=None,
        help="Column name for dates (default: auto-detect).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()

    if args.demo:
        print("Generating 3 demo strategies (1 year each)...")
        print("  Momentum:       40% target return, 45% target vol")
        print("  Mean Reversion: 20% target return, 15% target vol")
        print("  Trend Following: 30% target return, 35% target vol\n")
        strategies = generate_demo_strategies()
        print_full_comparison(strategies)

    elif args.csv:
        if len(args.csv) < 2:
            print("Error: Provide at least 2 CSV files for comparison.")
            sys.exit(1)

        try:
            strategies = load_strategies_from_csv(
                args.csv,
                value_col=args.value_col,
                date_col=args.date_col,
            )
        except Exception as e:
            print(f"Error loading CSV files: {e}")
            sys.exit(1)

        if len(strategies) < 2:
            print("Error: Need at least 2 valid strategies to compare.")
            sys.exit(1)

        print(f"Loaded {len(strategies)} strategies\n")
        print_full_comparison(strategies)

    else:
        print("Usage:")
        print("  python scripts/compare_strategies.py --demo")
        print("  python scripts/compare_strategies.py --csv strat1.csv strat2.csv strat3.csv")
        sys.exit(1)


if __name__ == "__main__":
    main()
