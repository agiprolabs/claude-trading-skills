#!/usr/bin/env python3
"""Walk-forward pairs trading backtest with synthetic cointegrated data.

Generates a synthetic cointegrated pair, estimates the hedge ratio on the
training half, constructs the spread, and simulates z-score-based pairs
trading on the out-of-sample half with transaction costs.

Usage:
    python scripts/pairs_backtest.py              # Run with defaults
    python scripts/pairs_backtest.py --demo        # Same as above
    python scripts/pairs_backtest.py --n 500 --cost 0.002

Dependencies:
    uv pip install pandas numpy scipy

Environment Variables:
    None required — runs entirely on synthetic data.
"""

import argparse
import sys
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats


# ── Configuration ───────────────────────────────────────────────────
ENTRY_ZSCORE: float = 2.0
EXIT_ZSCORE: float = 0.0
STOP_ZSCORE: float = 3.0
COST_PER_LEG: float = 0.003  # 0.3% per leg (30 bps)
INITIAL_CAPITAL: float = 100_000.0
POSITION_SIZE_PCT: float = 0.10  # 10% of capital per leg


# ── Data Classes ────────────────────────────────────────────────────
@dataclass
class Trade:
    """Record of a single pairs trade round trip."""

    entry_idx: int
    exit_idx: int
    direction: str  # "long_spread" or "short_spread"
    entry_zscore: float
    exit_zscore: float
    y_entry_price: float
    y_exit_price: float
    x_entry_price: float
    x_exit_price: float
    hedge_ratio: float
    qty_y: float
    qty_x: float
    gross_pnl: float
    costs: float
    net_pnl: float
    holding_periods: int
    exit_reason: str


@dataclass
class BacktestResult:
    """Complete backtest result summary."""

    trades: list[Trade] = field(default_factory=list)
    equity_curve: np.ndarray = field(default_factory=lambda: np.array([]))
    total_pnl: float = 0.0
    total_costs: float = 0.0
    net_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    num_trades: int = 0
    win_rate: float = 0.0
    avg_pnl_per_trade: float = 0.0
    avg_holding_period: float = 0.0
    profit_factor: float = 0.0
    y_buyhold_return: float = 0.0
    x_buyhold_return: float = 0.0


# ── Synthetic Data ──────────────────────────────────────────────────
def generate_cointegrated_pair(
    n: int = 300,
    hedge_ratio: float = 1.5,
    intercept: float = 10.0,
    spread_vol: float = 1.0,
    mean_reversion_speed: float = 0.05,
    drift: float = 0.01,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a synthetic cointegrated pair.

    Creates two price series X and Y where Y = alpha + beta*X + epsilon,
    with epsilon following an Ornstein-Uhlenbeck process.

    Args:
        n: Number of observations.
        hedge_ratio: True hedge ratio beta.
        intercept: True intercept alpha.
        spread_vol: Volatility of the spread process.
        mean_reversion_speed: Speed of mean reversion (0 to 1).
        drift: Common stochastic trend drift.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (y_prices, x_prices).
    """
    rng = np.random.default_rng(seed)

    x_innovations = drift + rng.normal(0, 1, n)
    x_prices = 100.0 + np.cumsum(x_innovations)

    spread = np.zeros(n)
    for t in range(1, n):
        spread[t] = (
            spread[t - 1]
            - mean_reversion_speed * spread[t - 1]
            + spread_vol * rng.normal()
        )

    y_prices = intercept + hedge_ratio * x_prices + spread

    return y_prices, x_prices


# ── Hedge Ratio Estimation ─────────────────────────────────────────
def estimate_hedge_ratio(
    y_train: np.ndarray,
    x_train: np.ndarray,
) -> tuple[float, float, float]:
    """Estimate hedge ratio using OLS on training data.

    Args:
        y_train: Training prices for Y.
        x_train: Training prices for X.

    Returns:
        Tuple of (hedge_ratio, intercept, r_squared).
    """
    slope, intercept, r_value, _, _ = stats.linregress(x_train, y_train)
    return slope, intercept, r_value ** 2


# ── Spread Construction ────────────────────────────────────────────
def compute_spread(
    y: np.ndarray,
    x: np.ndarray,
    hedge_ratio: float,
    intercept: float,
    lookback: int = 60,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute spread and rolling z-score.

    Uses rolling mean and std from the lookback window for z-score
    computation to avoid look-ahead bias.

    Args:
        y: Price series Y.
        x: Price series X.
        hedge_ratio: Estimated hedge ratio.
        intercept: Estimated intercept.
        lookback: Lookback window for rolling statistics.

    Returns:
        Tuple of (spread, z_score).
    """
    spread = y - hedge_ratio * x - intercept

    rolling_mean = pd.Series(spread).rolling(window=lookback, min_periods=lookback).mean().values
    rolling_std = pd.Series(spread).rolling(window=lookback, min_periods=lookback).std().values

    z_score = np.full_like(spread, np.nan)
    valid = ~np.isnan(rolling_mean) & ~np.isnan(rolling_std) & (rolling_std > 1e-10)
    z_score[valid] = (spread[valid] - rolling_mean[valid]) / rolling_std[valid]

    return spread, z_score


# ── Backtest Engine ─────────────────────────────────────────────────
def run_pairs_backtest(
    y: np.ndarray,
    x: np.ndarray,
    hedge_ratio: float,
    intercept: float,
    entry_z: float = ENTRY_ZSCORE,
    exit_z: float = EXIT_ZSCORE,
    stop_z: float = STOP_ZSCORE,
    cost_per_leg: float = COST_PER_LEG,
    capital: float = INITIAL_CAPITAL,
    position_pct: float = POSITION_SIZE_PCT,
    lookback: int = 60,
) -> BacktestResult:
    """Run pairs trading backtest on out-of-sample data.

    Simulates z-score based entry/exit with transaction costs.

    Args:
        y: Out-of-sample Y prices.
        x: Out-of-sample X prices.
        hedge_ratio: Estimated hedge ratio from training.
        intercept: Estimated intercept from training.
        entry_z: Z-score threshold for entry (absolute value).
        exit_z: Z-score threshold for exit (absolute value).
        stop_z: Z-score threshold for stop loss (absolute value).
        cost_per_leg: Transaction cost per leg as fraction.
        capital: Initial capital.
        position_pct: Fraction of capital per leg.
        lookback: Rolling window for z-score computation.

    Returns:
        BacktestResult with trades, equity curve, and performance metrics.
    """
    spread, z_score = compute_spread(y, x, hedge_ratio, intercept, lookback)
    n = len(y)

    result = BacktestResult()
    equity = capital
    equity_curve = [equity]
    trades: list[Trade] = []

    in_position = False
    direction: Optional[str] = None
    entry_idx = 0
    entry_z_val = 0.0
    qty_y = 0.0
    qty_x = 0.0
    y_entry = 0.0
    x_entry = 0.0

    for i in range(lookback, n):
        z = z_score[i]
        if np.isnan(z):
            equity_curve.append(equity)
            continue

        if not in_position:
            # Check entry signals
            if z < -entry_z:
                # Long spread: buy Y, sell X
                direction = "long_spread"
                in_position = True
                entry_idx = i
                entry_z_val = z
                y_entry = y[i]
                x_entry = x[i]
                leg_capital = equity * position_pct
                qty_y = leg_capital / y[i]
                qty_x = (qty_y * hedge_ratio * y[i]) / x[i]

            elif z > entry_z:
                # Short spread: sell Y, buy X
                direction = "short_spread"
                in_position = True
                entry_idx = i
                entry_z_val = z
                y_entry = y[i]
                x_entry = x[i]
                leg_capital = equity * position_pct
                qty_y = leg_capital / y[i]
                qty_x = (qty_y * hedge_ratio * y[i]) / x[i]

        else:
            # Check exit signals
            exit_reason = ""
            should_exit = False

            if direction == "long_spread":
                if z >= -exit_z:
                    should_exit = True
                    exit_reason = "convergence"
                elif z < -stop_z:
                    should_exit = True
                    exit_reason = "stop_loss"
            elif direction == "short_spread":
                if z <= exit_z:
                    should_exit = True
                    exit_reason = "convergence"
                elif z > stop_z:
                    should_exit = True
                    exit_reason = "stop_loss"

            # Time stop: 2x typical half-life (assume ~20 periods)
            if i - entry_idx > 40:
                should_exit = True
                exit_reason = "time_stop"

            if should_exit:
                # Calculate P&L
                if direction == "long_spread":
                    y_pnl = qty_y * (y[i] - y_entry)
                    x_pnl = qty_x * (x_entry - x[i])  # Short X
                else:
                    y_pnl = qty_y * (y_entry - y[i])  # Short Y
                    x_pnl = qty_x * (x[i] - x_entry)  # Long X

                gross_pnl = y_pnl + x_pnl

                # Transaction costs: 2 legs entry + 2 legs exit = 4 transactions
                entry_cost = cost_per_leg * (qty_y * y_entry + qty_x * x_entry)
                exit_cost = cost_per_leg * (qty_y * y[i] + qty_x * x[i])
                total_cost = entry_cost + exit_cost

                net_pnl = gross_pnl - total_cost
                equity += net_pnl

                trade = Trade(
                    entry_idx=entry_idx,
                    exit_idx=i,
                    direction=direction or "",
                    entry_zscore=entry_z_val,
                    exit_zscore=z,
                    y_entry_price=y_entry,
                    y_exit_price=y[i],
                    x_entry_price=x_entry,
                    x_exit_price=x[i],
                    hedge_ratio=hedge_ratio,
                    qty_y=qty_y,
                    qty_x=qty_x,
                    gross_pnl=gross_pnl,
                    costs=total_cost,
                    net_pnl=net_pnl,
                    holding_periods=i - entry_idx,
                    exit_reason=exit_reason,
                )
                trades.append(trade)

                in_position = False
                direction = None

        equity_curve.append(equity)

    # Close any open position at end
    if in_position:
        i = n - 1
        if direction == "long_spread":
            y_pnl = qty_y * (y[i] - y_entry)
            x_pnl = qty_x * (x_entry - x[i])
        else:
            y_pnl = qty_y * (y_entry - y[i])
            x_pnl = qty_x * (x[i] - x_entry)
        gross_pnl = y_pnl + x_pnl
        total_cost = cost_per_leg * (qty_y * y_entry + qty_x * x_entry + qty_y * y[i] + qty_x * x[i])
        net_pnl = gross_pnl - total_cost
        equity += net_pnl
        trades.append(Trade(
            entry_idx=entry_idx, exit_idx=i, direction=direction or "",
            entry_zscore=entry_z_val, exit_zscore=float(z_score[i]) if not np.isnan(z_score[i]) else 0.0,
            y_entry_price=y_entry, y_exit_price=y[i],
            x_entry_price=x_entry, x_exit_price=x[i],
            hedge_ratio=hedge_ratio, qty_y=qty_y, qty_x=qty_x,
            gross_pnl=gross_pnl, costs=total_cost, net_pnl=net_pnl,
            holding_periods=i - entry_idx, exit_reason="end_of_data",
        ))
        equity_curve.append(equity)

    # Compute performance metrics
    result.trades = trades
    result.equity_curve = np.array(equity_curve)
    result.num_trades = len(trades)
    result.total_pnl = sum(t.gross_pnl for t in trades)
    result.total_costs = sum(t.costs for t in trades)
    result.net_pnl = sum(t.net_pnl for t in trades)

    if trades:
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        result.win_rate = len(wins) / len(trades) * 100
        result.avg_pnl_per_trade = result.net_pnl / len(trades)
        result.avg_holding_period = np.mean([t.holding_periods for t in trades])

        gross_profit = sum(t.net_pnl for t in wins) if wins else 0.0
        gross_loss = abs(sum(t.net_pnl for t in losses)) if losses else 1e-10
        result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Sharpe ratio from equity curve returns
    eq = result.equity_curve
    if len(eq) > 1:
        returns = np.diff(eq) / eq[:-1]
        returns = returns[~np.isnan(returns)]
        if len(returns) > 0 and np.std(returns) > 1e-10:
            result.sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252)
        else:
            result.sharpe_ratio = 0.0

    # Max drawdown
    peak = np.maximum.accumulate(eq)
    drawdown = (peak - eq) / peak
    result.max_drawdown_pct = float(np.max(drawdown)) * 100
    result.max_drawdown = float(np.max(peak - eq))

    # Buy-and-hold returns for comparison
    result.y_buyhold_return = (y[-1] / y[lookback] - 1) * 100
    result.x_buyhold_return = (x[-1] / x[lookback] - 1) * 100

    return result


# ── Report Printing ─────────────────────────────────────────────────
def print_backtest_report(result: BacktestResult, capital: float = INITIAL_CAPITAL) -> None:
    """Print comprehensive backtest performance report.

    Args:
        result: BacktestResult from run_pairs_backtest().
        capital: Initial capital for percentage calculations.
    """
    sep = "=" * 60
    sub = "-" * 60

    print(f"\n{sep}")
    print("  PAIRS TRADING BACKTEST REPORT")
    print(sep)

    print(f"\n{'PERFORMANCE SUMMARY':^60}")
    print(sub)
    print(f"  Initial capital:     ${capital:>12,.2f}")
    print(f"  Final equity:        ${result.equity_curve[-1]:>12,.2f}")
    print(f"  Net P&L:             ${result.net_pnl:>12,.2f}  ({result.net_pnl / capital * 100:+.2f}%)")
    print(f"  Gross P&L:           ${result.total_pnl:>12,.2f}")
    print(f"  Total costs:         ${result.total_costs:>12,.2f}")
    print(f"  Sharpe ratio:        {result.sharpe_ratio:>12.2f}")
    print(f"  Max drawdown:        ${result.max_drawdown:>12,.2f}  ({result.max_drawdown_pct:.2f}%)")

    print(f"\n{'TRADE STATISTICS':^60}")
    print(sub)
    print(f"  Number of trades:    {result.num_trades:>12d}")
    print(f"  Win rate:            {result.win_rate:>12.1f}%")
    print(f"  Profit factor:       {result.profit_factor:>12.2f}")
    print(f"  Avg P&L per trade:   ${result.avg_pnl_per_trade:>12,.2f}")
    print(f"  Avg holding period:  {result.avg_holding_period:>12.1f} bars")

    # Exit reason breakdown
    if result.trades:
        reasons: dict[str, int] = {}
        for t in result.trades:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
        print(f"\n{'EXIT REASONS':^60}")
        print(sub)
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            pct = count / result.num_trades * 100
            print(f"  {reason:<20s}: {count:>4d}  ({pct:.1f}%)")

    # Individual trades
    if result.trades:
        print(f"\n{'TRADE LOG':^60}")
        print(sub)
        print(f"  {'#':>3s}  {'Dir':>6s}  {'Entry Z':>8s}  {'Exit Z':>8s}  "
              f"{'Gross':>10s}  {'Net':>10s}  {'Bars':>5s}  {'Reason':>12s}")
        print(f"  {'---':>3s}  {'------':>6s}  {'--------':>8s}  {'--------':>8s}  "
              f"{'----------':>10s}  {'----------':>10s}  {'-----':>5s}  {'------------':>12s}")
        for i, t in enumerate(result.trades):
            d = "LONG" if t.direction == "long_spread" else "SHORT"
            print(f"  {i + 1:>3d}  {d:>6s}  {t.entry_zscore:>8.2f}  {t.exit_zscore:>8.2f}  "
                  f"${t.gross_pnl:>9,.2f}  ${t.net_pnl:>9,.2f}  {t.holding_periods:>5d}  "
                  f"{t.exit_reason:>12s}")

    # Comparison with buy-and-hold
    print(f"\n{'COMPARISON: PAIRS vs BUY-AND-HOLD':^60}")
    print(sub)
    print(f"  Pairs strategy:      {result.net_pnl / capital * 100:>+10.2f}%")
    print(f"  Buy-hold Y:          {result.y_buyhold_return:>+10.2f}%")
    print(f"  Buy-hold X:          {result.x_buyhold_return:>+10.2f}%")
    bh_avg = (result.y_buyhold_return + result.x_buyhold_return) / 2
    print(f"  Buy-hold avg:        {bh_avg:>+10.2f}%")

    advantage = result.net_pnl / capital * 100 - bh_avg
    print(f"  Pairs advantage:     {advantage:>+10.2f}% vs avg buy-hold")

    print(f"\n{sep}")
    print("  This backtest uses synthetic data for demonstration.")
    print("  Past performance does not indicate future results.")
    print("  This is for informational purposes only.")
    print(sep)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run walk-forward pairs trading backtest."""
    parser = argparse.ArgumentParser(
        description="Walk-forward pairs trading backtest with synthetic data"
    )
    parser.add_argument(
        "--demo", action="store_true", default=True,
        help="Run demo with synthetic data (default: True)",
    )
    parser.add_argument(
        "--n", type=int, default=300,
        help="Number of synthetic data points (default: 300)",
    )
    parser.add_argument(
        "--hedge-ratio", type=float, default=1.5,
        help="True hedge ratio for synthetic data (default: 1.5)",
    )
    parser.add_argument(
        "--cost", type=float, default=COST_PER_LEG,
        help=f"Transaction cost per leg as fraction (default: {COST_PER_LEG})",
    )
    parser.add_argument(
        "--entry-z", type=float, default=ENTRY_ZSCORE,
        help=f"Entry z-score threshold (default: {ENTRY_ZSCORE})",
    )
    parser.add_argument(
        "--exit-z", type=float, default=EXIT_ZSCORE,
        help=f"Exit z-score threshold (default: {EXIT_ZSCORE})",
    )
    parser.add_argument(
        "--capital", type=float, default=INITIAL_CAPITAL,
        help=f"Initial capital (default: {INITIAL_CAPITAL})",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (default: 42)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Walk-Forward Pairs Trading Backtest")
    print("=" * 60)

    # Generate synthetic data
    print(f"\nGenerating synthetic cointegrated pair (n={args.n}, seed={args.seed})...")
    y, x = generate_cointegrated_pair(
        n=args.n,
        hedge_ratio=args.hedge_ratio,
        seed=args.seed,
    )

    # Walk-forward split
    split = len(y) // 2
    y_train, y_test = y[:split], y[split:]
    x_train, x_test = x[:split], x[split:]

    print(f"  Training:  {split} observations (first half)")
    print(f"  Testing:   {len(y) - split} observations (second half)")

    # Estimate hedge ratio on training data
    print("\nEstimating hedge ratio on training data...")
    hedge_ratio, intercept, r_sq = estimate_hedge_ratio(y_train, x_train)
    print(f"  Hedge ratio (beta): {hedge_ratio:.4f}")
    print(f"  Intercept (alpha):  {intercept:.4f}")
    print(f"  R-squared:          {r_sq:.4f}")
    print(f"  True hedge ratio:   {args.hedge_ratio:.4f}")
    print(f"  Estimation error:   {abs(hedge_ratio - args.hedge_ratio) / args.hedge_ratio * 100:.2f}%")

    # Run backtest on test data
    print(f"\nRunning backtest on out-of-sample data...")
    print(f"  Entry z-score: +/-{args.entry_z}")
    print(f"  Exit z-score:  +/-{args.exit_z}")
    print(f"  Stop z-score:  +/-{STOP_ZSCORE}")
    print(f"  Cost per leg:  {args.cost * 100:.1f}%")
    print(f"  Capital:       ${args.capital:,.0f}")

    result = run_pairs_backtest(
        y=y_test,
        x=x_test,
        hedge_ratio=hedge_ratio,
        intercept=intercept,
        entry_z=args.entry_z,
        exit_z=args.exit_z,
        stop_z=STOP_ZSCORE,
        cost_per_leg=args.cost,
        capital=args.capital,
        position_pct=POSITION_SIZE_PCT,
    )

    print_backtest_report(result, capital=args.capital)


if __name__ == "__main__":
    main()
