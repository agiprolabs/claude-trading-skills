#!/usr/bin/env python3
"""Generate professional trading charts from synthetic data.

Creates four chart types commonly used in trading analysis:
1. Candlestick chart with EMA overlays and volume bars
2. Equity curve with drawdown panel
3. Return distribution histogram with normal fit
4. Price chart with entry/exit trade markers

All charts use dark theme styling suitable for trading dashboards.
Outputs are saved as PNG files in the current directory.

Usage:
    python scripts/chart_generator.py
    python scripts/chart_generator.py --output-dir ./charts

Dependencies:
    uv pip install matplotlib mplfinance pandas numpy scipy

Environment Variables:
    None required — uses synthetic data for demonstration.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for file output

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
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
LIGHT_BLUE = "#3399ff"
TEXT_COLOR = "#e0e0e0"
TEXT_SECONDARY = "#aaaaaa"
DIM = "#555555"

FIGURE_DPI = 150
BARS = 100
SEED = 42


# ── Dark Theme Setup ───────────────────────────────────────────────
def apply_dark_theme() -> None:
    """Apply dark background trading theme to matplotlib."""
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
        "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY,
        "legend.facecolor": BACKGROUND,
        "legend.edgecolor": GRID_COLOR,
        "savefig.facecolor": BACKGROUND,
        "savefig.edgecolor": "none",
        "savefig.dpi": FIGURE_DPI,
    })


# ── Synthetic Data Generation ──────────────────────────────────────
def generate_ohlcv(n_bars: int = BARS, seed: int = SEED) -> pd.DataFrame:
    """Generate synthetic OHLCV data resembling a volatile token.

    Args:
        n_bars: Number of candlestick bars to generate.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with DatetimeIndex and Open/High/Low/Close/Volume columns.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n_bars, freq="1h")

    # Random walk with drift for close prices
    log_returns = rng.normal(0.0005, 0.02, n_bars)
    close = 100.0 * np.exp(np.cumsum(log_returns))

    # Derive OHLV from close
    spread = close * rng.uniform(0.005, 0.025, n_bars)
    high = close + spread * rng.uniform(0.3, 1.0, n_bars)
    low = close - spread * rng.uniform(0.3, 1.0, n_bars)
    open_price = close + rng.normal(0, spread * 0.3)

    # Ensure OHLC consistency
    high = np.maximum(high, np.maximum(open_price, close))
    low = np.minimum(low, np.minimum(open_price, close))

    volume = rng.lognormal(mean=10, sigma=0.8, size=n_bars)

    df = pd.DataFrame({
        "Open": open_price,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)

    return df


def generate_equity_curve(n_days: int = 252, seed: int = SEED) -> pd.Series:
    """Generate a synthetic equity curve over n_days.

    Args:
        n_days: Number of trading days.
        seed: Random seed for reproducibility.

    Returns:
        Series indexed by date with portfolio value.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n_days, freq="B")
    daily_returns = rng.normal(0.0008, 0.015, n_days)

    # Add a drawdown period in the middle
    drawdown_start = n_days // 3
    drawdown_end = drawdown_start + n_days // 6
    daily_returns[drawdown_start:drawdown_end] -= 0.008

    equity = 10_000.0 * np.cumprod(1 + daily_returns)
    return pd.Series(equity, index=dates, name="Equity")


def generate_trades(price: pd.Series, n_trades: int = 15,
                    seed: int = SEED) -> pd.DataFrame:
    """Generate synthetic trade entries and exits on a price series.

    Args:
        price: Price series with DatetimeIndex.
        n_trades: Number of trades to generate.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: entry_date, entry_price, exit_date,
        exit_price, return_pct, side.
    """
    rng = np.random.default_rng(seed)
    n = len(price)
    trades = []

    for _ in range(n_trades):
        entry_idx = rng.integers(5, n - 10)
        hold = rng.integers(2, 8)
        exit_idx = min(entry_idx + hold, n - 1)

        entry_price = float(price.iloc[entry_idx])
        exit_price = float(price.iloc[exit_idx])
        side = "long" if rng.random() > 0.3 else "short"

        if side == "long":
            ret = (exit_price - entry_price) / entry_price
        else:
            ret = (entry_price - exit_price) / entry_price

        trades.append({
            "entry_date": price.index[entry_idx],
            "entry_price": entry_price,
            "exit_date": price.index[exit_idx],
            "exit_price": exit_price,
            "return_pct": ret,
            "side": side,
        })

    return pd.DataFrame(trades)


# ── Chart 1: Candlestick with EMAs ─────────────────────────────────
def chart_candlestick(df: pd.DataFrame, output_dir: str) -> str:
    """Create candlestick chart with EMA overlays and volume.

    Args:
        df: OHLCV DataFrame with DatetimeIndex.
        output_dir: Directory to save the chart.

    Returns:
        Path to saved chart file.
    """
    try:
        import mplfinance as mpf
    except ImportError:
        print("mplfinance not installed. Run: uv pip install mplfinance")
        sys.exit(1)

    ema20 = df["Close"].ewm(span=20).mean()
    ema50 = df["Close"].ewm(span=50).mean()

    ap = [
        mpf.make_addplot(ema20, color=ORANGE, width=1.2),
        mpf.make_addplot(ema50, color=LIGHT_BLUE, width=1.2),
    ]

    mc = mpf.make_marketcolors(
        up=GREEN, down=RED,
        wick={"up": GREEN, "down": RED},
        edge={"up": GREEN, "down": RED},
        volume={"up": GREEN, "down": RED},
    )
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds", marketcolors=mc,
        facecolor=BACKGROUND, figcolor=BACKGROUND,
        gridcolor=GRID_COLOR, gridstyle="--",
    )

    save_path = os.path.join(output_dir, "candlestick.png")
    mpf.plot(
        df, type="candle", style=style, addplot=ap,
        volume=True, figsize=(14, 8),
        title="\nCandlestick — EMA(20, 50) with Volume",
        savefig=dict(fname=save_path, dpi=FIGURE_DPI, facecolor=BACKGROUND),
    )
    return save_path


# ── Chart 2: Equity Curve with Drawdown ─────────────────────────────
def chart_equity_drawdown(equity: pd.Series, output_dir: str) -> str:
    """Create equity curve with drawdown panel.

    Args:
        equity: Portfolio equity series.
        output_dir: Directory to save the chart.

    Returns:
        Path to saved chart file.
    """
    peak = equity.cummax()
    drawdown = (equity - peak) / peak

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(14, 8), height_ratios=[2, 1], sharex=True
    )

    # Equity panel
    ax1.plot(equity.index, equity, color=GREEN, linewidth=1.5, label="Equity")
    ax1.plot(equity.index, peak, color=DIM, linewidth=0.8, linestyle="--",
             label="Peak")
    ax1.set_ylabel("Portfolio Value ($)", fontsize=11)
    ax1.set_title("Equity Curve with Drawdown", fontsize=14, fontweight="bold")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)

    # Stats box
    total_ret = (equity.iloc[-1] / equity.iloc[0]) - 1
    max_dd = float(drawdown.min())
    stats_text = f"Return: {total_ret:.1%}\nMax DD: {max_dd:.1%}"
    ax1.text(
        0.02, 0.95, stats_text, transform=ax1.transAxes,
        fontsize=10, fontfamily="monospace", verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#222233",
                  edgecolor=GRID_COLOR, alpha=0.9),
    )

    # Drawdown panel
    ax2.fill_between(equity.index, drawdown, 0, color=RED, alpha=0.5)
    ax2.plot(equity.index, drawdown, color=RED, linewidth=0.8)
    ax2.set_ylabel("Drawdown", fontsize=11)
    ax2.set_xlabel("Date", fontsize=11)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    save_path = os.path.join(output_dir, "equity_drawdown.png")
    fig.savefig(save_path, dpi=FIGURE_DPI, facecolor=BACKGROUND,
                edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return save_path


# ── Chart 3: Return Distribution ────────────────────────────────────
def chart_return_distribution(returns: pd.Series, output_dir: str) -> str:
    """Create return distribution histogram with normal fit and VaR.

    Args:
        returns: Series of periodic returns.
        output_dir: Directory to save the chart.

    Returns:
        Path to saved chart file.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.hist(returns, bins=50, density=True, alpha=0.7,
            color=BLUE, edgecolor="#222222")

    # Normal distribution overlay
    mu = float(returns.mean())
    sigma = float(returns.std())
    x = np.linspace(float(returns.min()), float(returns.max()), 200)
    ax.plot(x, stats.norm.pdf(x, mu, sigma), color=AMBER,
            linewidth=2, label=f"Normal (mu={mu:.4f}, sigma={sigma:.4f})")

    # VaR and CVaR lines
    var_95 = float(returns.quantile(0.05))
    tail = returns[returns <= var_95]
    cvar_95 = float(tail.mean()) if len(tail) > 0 else var_95
    ax.axvline(var_95, color=RED, linestyle="--", linewidth=1.5,
               label=f"VaR 95%: {var_95:.4f}")
    ax.axvline(cvar_95, color=ORANGE, linestyle=":", linewidth=1.5,
               label=f"CVaR 95%: {cvar_95:.4f}")

    ax.set_title("Return Distribution", fontsize=14, fontweight="bold")
    ax.set_xlabel("Daily Return", fontsize=11)
    ax.set_ylabel("Density", fontsize=11)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    save_path = os.path.join(output_dir, "return_distribution.png")
    fig.savefig(save_path, dpi=FIGURE_DPI, facecolor=BACKGROUND,
                edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return save_path


# ── Chart 4: Trade Markers on Price ──────────────────────────────────
def chart_trade_markers(price: pd.Series, trades: pd.DataFrame,
                        output_dir: str) -> str:
    """Create price chart with entry/exit trade markers.

    Args:
        price: Close price series.
        trades: DataFrame with entry_date, entry_price, exit_date,
                exit_price, return_pct, side columns.
        output_dir: Directory to save the chart.

    Returns:
        Path to saved chart file.
    """
    fig, ax = plt.subplots(figsize=(14, 7))

    # Price line
    ax.plot(price.index, price, color="#cccccc", linewidth=1, alpha=0.8,
            label="Price")

    # Entry markers
    for _, t in trades.iterrows():
        marker = "^" if t["side"] == "long" else "v"
        color = GREEN if t["side"] == "long" else RED
        ax.scatter(t["entry_date"], t["entry_price"],
                   marker=marker, color=color, s=100, zorder=5, edgecolors="white",
                   linewidths=0.5)

    # Exit markers (colored by P&L)
    for _, t in trades.iterrows():
        exit_color = GREEN if t["return_pct"] >= 0 else RED
        ax.scatter(t["exit_date"], t["exit_price"],
                   marker="x", color=exit_color, s=80, zorder=5, linewidths=2)

    # Connect entry to exit
    for _, t in trades.iterrows():
        line_color = GREEN if t["return_pct"] >= 0 else RED
        ax.plot([t["entry_date"], t["exit_date"]],
                [t["entry_price"], t["exit_price"]],
                color=line_color, linewidth=0.6, alpha=0.4)

    # Summary stats
    wins = len(trades[trades["return_pct"] >= 0])
    total = len(trades)
    win_rate = wins / total if total > 0 else 0
    avg_ret = float(trades["return_pct"].mean())
    stats_text = (
        f"Trades: {total}\n"
        f"Win rate: {win_rate:.0%}\n"
        f"Avg return: {avg_ret:.2%}"
    )
    ax.text(
        0.02, 0.95, stats_text, transform=ax.transAxes,
        fontsize=10, fontfamily="monospace", verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#222233",
                  edgecolor=GRID_COLOR, alpha=0.9),
    )

    # Legend entries for marker types
    ax.scatter([], [], marker="^", color=GREEN, s=60, label="Long entry")
    ax.scatter([], [], marker="v", color=RED, s=60, label="Short entry")
    ax.scatter([], [], marker="x", color=GREEN, s=60, label="Win exit")
    ax.scatter([], [], marker="x", color=RED, s=60, label="Loss exit")

    ax.set_title("Trade Markers on Price", fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Price", fontsize=11)
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    save_path = os.path.join(output_dir, "trade_markers.png")
    fig.savefig(save_path, dpi=FIGURE_DPI, facecolor=BACKGROUND,
                edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return save_path


# ── Main ────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate professional trading charts from synthetic data."
    )
    parser.add_argument(
        "--output-dir", type=str, default=".",
        help="Directory to save chart PNGs (default: current directory)."
    )
    return parser.parse_args()


def main() -> None:
    """Generate all demo charts and print file paths."""
    args = parse_args()
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    apply_dark_theme()
    print("Generating synthetic trading data...")

    # Generate data
    ohlcv = generate_ohlcv()
    equity = generate_equity_curve()
    daily_returns = equity.pct_change().dropna()
    trades = generate_trades(ohlcv["Close"])

    print(f"  OHLCV: {len(ohlcv)} bars")
    print(f"  Equity: {len(equity)} days")
    print(f"  Trades: {len(trades)} trades")
    print()

    # Generate charts
    charts = []

    print("Creating candlestick chart...")
    charts.append(chart_candlestick(ohlcv, output_dir))

    print("Creating equity curve with drawdown...")
    charts.append(chart_equity_drawdown(equity, output_dir))

    print("Creating return distribution...")
    charts.append(chart_return_distribution(daily_returns, output_dir))

    print("Creating trade markers chart...")
    charts.append(chart_trade_markers(ohlcv["Close"], trades, output_dir))

    print()
    print("Charts generated:")
    for path in charts:
        abs_path = os.path.abspath(path)
        print(f"  {abs_path}")

    print()
    print(f"All {len(charts)} charts saved to: {os.path.abspath(output_dir)}")


if __name__ == "__main__":
    main()
