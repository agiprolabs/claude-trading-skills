#!/usr/bin/env python3
"""Generate a multi-chart performance report from a portfolio equity curve.

Creates three report pages as individual PNG files:
  Page 1: Equity curve + drawdown panel
  Page 2: Monthly returns table + return distribution histogram
  Page 3: Trade analysis — win/loss bar chart + holding period distribution

Also prints a summary of key performance statistics to the console.
Uses synthetic demo data by default.

Usage:
    python scripts/performance_report.py
    python scripts/performance_report.py --output-dir ./reports
    python scripts/performance_report.py --days 500

Dependencies:
    uv pip install matplotlib pandas numpy scipy

Environment Variables:
    None required — uses synthetic data for demonstration.
"""

import argparse
import os
import sys
from typing import Optional

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


# ── Configuration ───────────────────────────────────────────────────
BACKGROUND = "#1a1a2e"
GRID_COLOR = "#333333"
GREEN = "#00ff88"
RED = "#ff4444"
BLUE = "#4488ff"
AMBER = "#ffaa00"
ORANGE = "#ff6600"
TEXT_COLOR = "#e0e0e0"
DIM = "#555555"
FIGURE_DPI = 150
SEED = 42


# ── Dark Theme ──────────────────────────────────────────────────────
def apply_dark_theme() -> None:
    """Apply dark background trading theme globally."""
    plt.style.use("dark_background")
    plt.rcParams.update({
        "figure.facecolor": BACKGROUND,
        "axes.facecolor": BACKGROUND,
        "axes.edgecolor": GRID_COLOR,
        "axes.labelcolor": TEXT_COLOR,
        "grid.color": GRID_COLOR,
        "grid.alpha": 0.4,
        "grid.linestyle": "--",
        "text.color": TEXT_COLOR,
        "xtick.color": "#aaaaaa",
        "ytick.color": "#aaaaaa",
        "legend.facecolor": BACKGROUND,
        "legend.edgecolor": GRID_COLOR,
        "savefig.facecolor": BACKGROUND,
        "savefig.edgecolor": "none",
        "savefig.dpi": FIGURE_DPI,
    })


# ── Data Generation ────────────────────────────────────────────────
def generate_equity(n_days: int = 365, initial: float = 10_000.0,
                    seed: int = SEED) -> pd.Series:
    """Generate synthetic equity curve with realistic characteristics.

    Args:
        n_days: Number of trading days.
        initial: Starting portfolio value.
        seed: Random seed.

    Returns:
        Series of portfolio values indexed by business day.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n_days, freq="B")

    # Base returns with slight positive drift
    daily_ret = rng.normal(0.0006, 0.014, n_days)

    # Inject a drawdown period
    dd_start = n_days // 4
    dd_end = dd_start + n_days // 8
    daily_ret[dd_start:dd_end] -= 0.007

    # Inject a rally
    rally_start = n_days * 2 // 3
    rally_end = rally_start + n_days // 10
    daily_ret[rally_start:rally_end] += 0.005

    equity = initial * np.cumprod(1 + daily_ret)
    return pd.Series(equity, index=dates, name="Equity")


def generate_trade_list(n_trades: int = 80, seed: int = SEED) -> pd.DataFrame:
    """Generate a synthetic list of closed trades.

    Args:
        n_trades: Number of trades.
        seed: Random seed.

    Returns:
        DataFrame with columns: entry_date, exit_date, return_pct,
        hold_hours, size_usd, side.
    """
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2025-01-01")
    trades = []

    for i in range(n_trades):
        entry_date = base + pd.Timedelta(hours=int(rng.integers(0, 8000)))
        hold_hours = int(rng.integers(1, 72))
        exit_date = entry_date + pd.Timedelta(hours=hold_hours)

        # 55% win rate with positive skew
        is_win = rng.random() < 0.55
        if is_win:
            ret = float(rng.exponential(0.04))
        else:
            ret = -float(rng.exponential(0.035))

        size_usd = float(rng.uniform(200, 2000))
        side = "long" if rng.random() > 0.25 else "short"

        trades.append({
            "entry_date": entry_date,
            "exit_date": exit_date,
            "return_pct": ret,
            "hold_hours": hold_hours,
            "size_usd": size_usd,
            "side": side,
        })

    return pd.DataFrame(trades)


# ── Performance Metrics ─────────────────────────────────────────────
def compute_metrics(equity: pd.Series, trades: pd.DataFrame) -> dict:
    """Compute key performance metrics.

    Args:
        equity: Portfolio equity series.
        trades: Trade list DataFrame.

    Returns:
        Dict of metric name to value.
    """
    returns = equity.pct_change().dropna()
    peak = equity.cummax()
    drawdown = (equity - peak) / peak

    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1
    ann_return = (1 + total_return) ** (252 / len(equity)) - 1
    ann_vol = float(returns.std()) * np.sqrt(252)
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0
    max_dd = float(drawdown.min())

    # Trade metrics
    wins = trades[trades["return_pct"] > 0]
    losses = trades[trades["return_pct"] <= 0]
    win_rate = len(wins) / len(trades) if len(trades) > 0 else 0
    avg_win = float(wins["return_pct"].mean()) if len(wins) > 0 else 0
    avg_loss = float(losses["return_pct"].mean()) if len(losses) > 0 else 0
    profit_factor = (
        abs(float(wins["return_pct"].sum()) / float(losses["return_pct"].sum()))
        if len(losses) > 0 and float(losses["return_pct"].sum()) != 0
        else float("inf")
    )
    avg_hold = float(trades["hold_hours"].mean())

    return {
        "total_return": total_return,
        "ann_return": ann_return,
        "ann_volatility": ann_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "total_trades": len(trades),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "avg_hold_hours": avg_hold,
    }


def print_metrics(metrics: dict) -> None:
    """Print performance metrics to console."""
    print("=" * 50)
    print("  PERFORMANCE SUMMARY")
    print("=" * 50)
    print(f"  Total Return:     {metrics['total_return']:>10.2%}")
    print(f"  Ann. Return:      {metrics['ann_return']:>10.2%}")
    print(f"  Ann. Volatility:  {metrics['ann_volatility']:>10.2%}")
    print(f"  Sharpe Ratio:     {metrics['sharpe_ratio']:>10.2f}")
    print(f"  Max Drawdown:     {metrics['max_drawdown']:>10.2%}")
    print("-" * 50)
    print(f"  Total Trades:     {metrics['total_trades']:>10d}")
    print(f"  Win Rate:         {metrics['win_rate']:>10.1%}")
    print(f"  Avg Win:          {metrics['avg_win']:>10.2%}")
    print(f"  Avg Loss:         {metrics['avg_loss']:>10.2%}")
    print(f"  Profit Factor:    {metrics['profit_factor']:>10.2f}")
    print(f"  Avg Hold (hrs):   {metrics['avg_hold_hours']:>10.1f}")
    print("=" * 50)


# ── Page 1: Equity Curve + Drawdown ─────────────────────────────────
def page_equity(equity: pd.Series, metrics: dict,
                output_dir: str) -> str:
    """Generate equity curve with drawdown panel.

    Args:
        equity: Portfolio equity series.
        metrics: Pre-computed performance metrics.
        output_dir: Directory to save output.

    Returns:
        Path to saved chart.
    """
    peak = equity.cummax()
    dd = (equity - peak) / peak

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(14, 8), height_ratios=[2, 1], sharex=True
    )

    ax1.plot(equity.index, equity, color=GREEN, linewidth=1.5, label="Equity")
    ax1.plot(equity.index, peak, color=DIM, linewidth=0.8, linestyle="--",
             label="Peak")
    ax1.set_ylabel("Portfolio Value ($)", fontsize=11)
    ax1.set_title("Performance Report — Equity Curve", fontsize=14,
                  fontweight="bold")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)

    # Stats box
    stats_text = (
        f"Return: {metrics['total_return']:.1%}\n"
        f"Sharpe: {metrics['sharpe_ratio']:.2f}\n"
        f"Max DD: {metrics['max_drawdown']:.1%}\n"
        f"Win Rate: {metrics['win_rate']:.0%}"
    )
    ax1.text(
        0.02, 0.95, stats_text, transform=ax1.transAxes,
        fontsize=10, fontfamily="monospace", verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#222233",
                  edgecolor=GRID_COLOR, alpha=0.9),
    )

    ax2.fill_between(equity.index, dd, 0, color=RED, alpha=0.5)
    ax2.plot(equity.index, dd, color=RED, linewidth=0.8)
    ax2.set_ylabel("Drawdown", fontsize=11)
    ax2.set_xlabel("Date", fontsize=11)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    save_path = os.path.join(output_dir, "report_p1_equity.png")
    fig.savefig(save_path, dpi=FIGURE_DPI, facecolor=BACKGROUND,
                edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return save_path


# ── Page 2: Monthly Returns + Distribution ──────────────────────────
def page_returns(equity: pd.Series, output_dir: str) -> str:
    """Generate monthly returns text table and return distribution.

    Args:
        equity: Portfolio equity series.
        output_dir: Directory to save output.

    Returns:
        Path to saved chart.
    """
    returns = equity.pct_change().dropna()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    # Left: Monthly returns as text table
    monthly = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    monthly_df = pd.DataFrame({
        "Month": monthly.index.strftime("%Y-%m"),
        "Return": monthly.values,
    })

    ax1.axis("off")
    ax1.set_title("Monthly Returns", fontsize=14, fontweight="bold",
                  pad=20)

    # Build table data
    table_data = []
    cell_colors = []
    for _, row in monthly_df.iterrows():
        ret_val = row["Return"]
        table_data.append([row["Month"], f"{ret_val:.2%}"])
        if ret_val >= 0:
            cell_colors.append([BACKGROUND, "#1a3a2e"])
        else:
            cell_colors.append([BACKGROUND, "#3a1a1e"])

    if table_data:
        table = ax1.table(
            cellText=table_data,
            colLabels=["Month", "Return"],
            cellColours=cell_colors,
            colColours=[GRID_COLOR, GRID_COLOR],
            loc="center",
            cellLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(0.8, 1.4)
        for key, cell in table.get_celld().items():
            cell.set_edgecolor(GRID_COLOR)
            cell.set_text_props(color=TEXT_COLOR)

    # Right: Return distribution
    ax2.hist(returns, bins=50, density=True, alpha=0.7,
             color=BLUE, edgecolor="#222222")

    mu = float(returns.mean())
    sigma = float(returns.std())
    x = np.linspace(float(returns.min()), float(returns.max()), 200)
    ax2.plot(x, stats.norm.pdf(x, mu, sigma), color=AMBER, linewidth=2,
             label=f"Normal (mu={mu:.4f})")

    var_95 = float(returns.quantile(0.05))
    ax2.axvline(var_95, color=RED, linestyle="--", linewidth=1.5,
                label=f"VaR 95%: {var_95:.4f}")

    ax2.set_title("Return Distribution", fontsize=14, fontweight="bold")
    ax2.set_xlabel("Daily Return", fontsize=11)
    ax2.set_ylabel("Density", fontsize=11)
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    save_path = os.path.join(output_dir, "report_p2_returns.png")
    fig.savefig(save_path, dpi=FIGURE_DPI, facecolor=BACKGROUND,
                edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return save_path


# ── Page 3: Trade Analysis ──────────────────────────────────────────
def page_trades(trades: pd.DataFrame, output_dir: str) -> str:
    """Generate trade analysis: win/loss distribution + holding period.

    Args:
        trades: Trade list DataFrame.
        output_dir: Directory to save output.

    Returns:
        Path to saved chart.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    # Left: Return distribution by trade
    wins = trades[trades["return_pct"] >= 0]["return_pct"]
    losses = trades[trades["return_pct"] < 0]["return_pct"]

    bins = np.linspace(
        float(trades["return_pct"].min()) - 0.01,
        float(trades["return_pct"].max()) + 0.01,
        30
    )

    ax1.hist(wins, bins=bins, alpha=0.7, color=GREEN, label=f"Wins ({len(wins)})",
             edgecolor="#222222")
    ax1.hist(losses, bins=bins, alpha=0.7, color=RED,
             label=f"Losses ({len(losses)})", edgecolor="#222222")
    ax1.axvline(0, color=DIM, linewidth=1, linestyle="-")

    ax1.set_title("Trade Returns Distribution", fontsize=14,
                  fontweight="bold")
    ax1.set_xlabel("Return per Trade", fontsize=11)
    ax1.set_ylabel("Count", fontsize=11)
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)

    # Right: Holding period distribution
    hold_bins = np.arange(0, float(trades["hold_hours"].max()) + 5, 4)
    colors_hold = []
    for i in range(len(hold_bins) - 1):
        mask = (trades["hold_hours"] >= hold_bins[i]) & (
            trades["hold_hours"] < hold_bins[i + 1]
        )
        subset = trades.loc[mask, "return_pct"]
        avg_ret = float(subset.mean()) if len(subset) > 0 else 0
        colors_hold.append(GREEN if avg_ret >= 0 else RED)

    counts, _, patches = ax2.hist(
        trades["hold_hours"], bins=hold_bins, alpha=0.7,
        color=BLUE, edgecolor="#222222"
    )
    for patch, c in zip(patches, colors_hold):
        patch.set_facecolor(c)
        patch.set_alpha(0.7)

    ax2.set_title("Holding Period Distribution", fontsize=14,
                  fontweight="bold")
    ax2.set_xlabel("Holding Period (hours)", fontsize=11)
    ax2.set_ylabel("Count", fontsize=11)
    ax2.grid(True, alpha=0.3)

    # Stats
    win_rate = len(wins) / len(trades) if len(trades) > 0 else 0
    avg_ret = float(trades["return_pct"].mean())
    stats_text = (
        f"Win rate: {win_rate:.0%}  |  "
        f"Avg return: {avg_ret:.2%}  |  "
        f"Avg hold: {trades['hold_hours'].mean():.0f}h"
    )
    fig.suptitle(stats_text, fontsize=11, color=TEXT_COLOR, y=0.02,
                 fontfamily="monospace")

    fig.tight_layout(rect=[0, 0.04, 1, 1])
    save_path = os.path.join(output_dir, "report_p3_trades.png")
    fig.savefig(save_path, dpi=FIGURE_DPI, facecolor=BACKGROUND,
                edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return save_path


# ── Main ────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate multi-chart performance report."
    )
    parser.add_argument(
        "--output-dir", type=str, default=".",
        help="Directory to save report PNGs (default: current directory)."
    )
    parser.add_argument(
        "--days", type=int, default=365,
        help="Number of trading days for synthetic equity (default: 365)."
    )
    return parser.parse_args()


def main() -> None:
    """Generate the full performance report."""
    args = parse_args()
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    apply_dark_theme()

    print("Generating synthetic portfolio data...")
    equity = generate_equity(n_days=args.days)
    trades = generate_trade_list(n_trades=80)
    metrics = compute_metrics(equity, trades)

    print()
    print_metrics(metrics)
    print()

    pages = []

    print("Generating Page 1: Equity Curve + Drawdown...")
    pages.append(page_equity(equity, metrics, output_dir))

    print("Generating Page 2: Monthly Returns + Distribution...")
    pages.append(page_returns(equity, output_dir))

    print("Generating Page 3: Trade Analysis...")
    pages.append(page_trades(trades, output_dir))

    print()
    print("Report pages generated:")
    for path in pages:
        print(f"  {os.path.abspath(path)}")

    print()
    print(f"All {len(pages)} report pages saved to: {os.path.abspath(output_dir)}")


if __name__ == "__main__":
    main()
