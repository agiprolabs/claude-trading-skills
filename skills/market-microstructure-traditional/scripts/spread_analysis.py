#!/usr/bin/env python3
"""Bid-ask spread analysis: compute quoted, effective, and realized spreads.

Analyzes order book and trade data to decompose spreads into adverse selection,
inventory, and order processing components. Includes --demo mode with synthetic
data so no API key is required to run.

Usage:
    python scripts/spread_analysis.py --demo
    python scripts/spread_analysis.py --input trades.csv

Dependencies:
    uv pip install numpy pandas matplotlib

Environment Variables:
    None required for --demo mode.
"""

import argparse
import sys
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ── Data Structures ─────────────────────────────────────────────────


@dataclass
class SpreadMetrics:
    """Aggregated spread metrics for a trading session."""

    quoted_spread_bps: float
    effective_spread_bps: float
    realized_spread_bps: float
    adverse_selection_bps: float
    price_impact_bps: float
    n_trades: int

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = [
            "=== Spread Analysis Summary ===",
            f"  Trades analyzed:        {self.n_trades:,}",
            f"  Quoted spread:          {self.quoted_spread_bps:.2f} bps",
            f"  Effective spread:       {self.effective_spread_bps:.2f} bps",
            f"  Realized spread (5s):   {self.realized_spread_bps:.2f} bps",
            f"  Adverse selection:      {self.adverse_selection_bps:.2f} bps",
            f"  Avg price impact:       {self.price_impact_bps:.2f} bps",
        ]
        return "\n".join(lines)


# ── Synthetic Data Generation ───────────────────────────────────────


def generate_synthetic_orderbook(
    n_snapshots: int = 1000,
    base_price: float = 100.0,
    base_spread_bps: float = 10.0,
    volatility: float = 0.001,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic order book snapshots with bid/ask prices.

    Args:
        n_snapshots: Number of time steps.
        base_price: Starting midprice.
        base_spread_bps: Average quoted spread in basis points.
        volatility: Per-step return volatility.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: timestamp, bid, ask, midprice.
    """
    rng = np.random.default_rng(seed)

    # Random walk midprice
    returns = rng.normal(0, volatility, n_snapshots)
    midprices = base_price * np.exp(np.cumsum(returns))

    # Spread varies around base with some noise
    half_spread_frac = (base_spread_bps / 10_000) / 2
    spread_noise = rng.uniform(0.5, 1.5, n_snapshots)

    bids = midprices * (1 - half_spread_frac * spread_noise)
    asks = midprices * (1 + half_spread_frac * spread_noise)

    timestamps = pd.date_range("2025-01-01", periods=n_snapshots, freq="100ms")

    return pd.DataFrame({
        "timestamp": timestamps,
        "bid": bids,
        "ask": asks,
        "midprice": midprices,
    })


def generate_synthetic_trades(
    orderbook: pd.DataFrame,
    trades_per_snapshot: float = 0.3,
    informed_fraction: float = 0.15,
    seed: int = 123,
) -> pd.DataFrame:
    """Generate synthetic trades against an order book.

    Informed trades tend to buy before price rises and sell before drops.
    Uninformed trades are random.

    Args:
        orderbook: Order book snapshots from generate_synthetic_orderbook.
        trades_per_snapshot: Average number of trades per snapshot.
        informed_fraction: Fraction of trades that are informed.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: timestamp, price, side, midprice, is_informed.
    """
    rng = np.random.default_rng(seed)
    trades = []

    midprices = orderbook["midprice"].values
    future_returns = np.zeros(len(midprices))
    lookahead = 50  # look 50 steps ahead for "information"
    for i in range(len(midprices) - lookahead):
        future_returns[i] = (midprices[i + lookahead] - midprices[i]) / midprices[i]

    for i, row in orderbook.iterrows():
        if rng.random() > trades_per_snapshot:
            continue

        is_informed = rng.random() < informed_fraction

        if is_informed:
            # Informed traders buy before price rises, sell before drops
            side = "buy" if future_returns[i] > 0 else "sell"
        else:
            side = "buy" if rng.random() > 0.5 else "sell"

        # Trade executes at ask for buys, bid for sells, with some noise
        if side == "buy":
            price = row["ask"] * (1 + rng.uniform(0, 0.0001))
        else:
            price = row["bid"] * (1 - rng.uniform(0, 0.0001))

        trades.append({
            "timestamp": row["timestamp"],
            "price": price,
            "side": side,
            "midprice": row["midprice"],
            "is_informed": is_informed,
        })

    return pd.DataFrame(trades)


# ── Spread Computation ──────────────────────────────────────────────


def compute_quoted_spread(orderbook: pd.DataFrame) -> pd.Series:
    """Compute quoted spread in basis points for each snapshot.

    Args:
        orderbook: DataFrame with bid and ask columns.

    Returns:
        Series of quoted spreads in basis points.
    """
    midprice = (orderbook["bid"] + orderbook["ask"]) / 2
    return (orderbook["ask"] - orderbook["bid"]) / midprice * 10_000


def compute_effective_spread(trades: pd.DataFrame) -> pd.Series:
    """Compute effective half-spread in basis points for each trade.

    The effective spread measures the actual cost paid relative to the
    midprice at the time of the trade.

    Args:
        trades: DataFrame with price, side, and midprice columns.

    Returns:
        Series of effective half-spreads in basis points.
    """
    sign = trades["side"].map({"buy": 1.0, "sell": -1.0})
    return sign * (trades["price"] - trades["midprice"]) / trades["midprice"] * 10_000


def compute_realized_spread(
    trades: pd.DataFrame,
    orderbook: pd.DataFrame,
    delay_steps: int = 50,
) -> pd.Series:
    """Compute realized spread: what the market maker actually keeps.

    Realized spread = trade_sign * (trade_price - midprice_after_delay).
    The difference between effective and realized spread is adverse selection.

    Args:
        trades: Trade DataFrame with timestamp, price, side columns.
        orderbook: Order book DataFrame with timestamp and midprice.
        delay_steps: Number of order book snapshots to look ahead.

    Returns:
        Series of realized half-spreads in basis points.
    """
    # Map each trade to the midprice delay_steps later
    ob_midprices = orderbook.set_index("timestamp")["midprice"]
    ob_timestamps = orderbook["timestamp"].values

    realized = []
    for _, trade in trades.iterrows():
        # Find the orderbook index closest to trade timestamp
        idx = np.searchsorted(ob_timestamps, trade["timestamp"])
        future_idx = min(idx + delay_steps, len(ob_midprices) - 1)
        future_mid = ob_midprices.iloc[future_idx]

        sign = 1.0 if trade["side"] == "buy" else -1.0
        rs = sign * (trade["price"] - future_mid) / trade["midprice"] * 10_000
        realized.append(rs)

    return pd.Series(realized, index=trades.index)


def compute_kyle_lambda(
    trades: pd.DataFrame,
    interval: str = "1s",
) -> dict:
    """Estimate Kyle's lambda from trade data.

    Aggregates signed volume and midprice changes over intervals, then
    regresses price changes on signed volume.

    Args:
        trades: Trade DataFrame with timestamp, price, side, midprice.
        interval: Time interval for aggregation.

    Returns:
        Dict with lambda estimate and R-squared.
    """
    df = trades.copy()
    df["signed_volume"] = df["side"].map({"buy": 1.0, "sell": -1.0})
    df = df.set_index("timestamp")

    agg = df.resample(interval).agg({
        "signed_volume": "sum",
        "midprice": "last",
    }).dropna()

    agg["midprice_change"] = agg["midprice"].diff()
    agg = agg.dropna()

    if len(agg) < 10:
        return {"lambda": 0.0, "r_squared": 0.0, "n_intervals": len(agg)}

    X = agg["signed_volume"].values.reshape(-1, 1)
    y = agg["midprice_change"].values

    X_with_const = np.column_stack([np.ones(len(X)), X])
    beta, residuals, _, _ = np.linalg.lstsq(X_with_const, y, rcond=None)

    y_hat = X_with_const @ beta
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return {
        "lambda": float(beta[1]),
        "r_squared": float(r_sq),
        "n_intervals": len(agg),
    }


def analyze_spreads(
    trades: pd.DataFrame,
    orderbook: pd.DataFrame,
    delay_steps: int = 50,
) -> SpreadMetrics:
    """Run full spread analysis and return aggregated metrics.

    Args:
        trades: Trade DataFrame.
        orderbook: Order book DataFrame.
        delay_steps: Steps for realized spread delay.

    Returns:
        SpreadMetrics with all computed values.
    """
    quoted = compute_quoted_spread(orderbook)
    effective = compute_effective_spread(trades)
    realized = compute_realized_spread(trades, orderbook, delay_steps)

    adverse_selection = effective.mean() - realized.mean()

    # Price impact: midprice move in trade direction after delay
    signs = trades["side"].map({"buy": 1.0, "sell": -1.0})
    ob_midprices = orderbook.set_index("timestamp")["midprice"]
    ob_timestamps = orderbook["timestamp"].values

    impacts = []
    for _, trade in trades.iterrows():
        idx = np.searchsorted(ob_timestamps, trade["timestamp"])
        future_idx = min(idx + delay_steps, len(ob_midprices) - 1)
        future_mid = ob_midprices.iloc[future_idx]
        sign = 1.0 if trade["side"] == "buy" else -1.0
        impact = sign * (future_mid - trade["midprice"]) / trade["midprice"] * 10_000
        impacts.append(impact)

    return SpreadMetrics(
        quoted_spread_bps=float(quoted.mean()),
        effective_spread_bps=float(effective.mean()),
        realized_spread_bps=float(realized.mean()),
        adverse_selection_bps=float(adverse_selection),
        price_impact_bps=float(np.mean(impacts)),
        n_trades=len(trades),
    )


# ── Visualization ───────────────────────────────────────────────────


def plot_spread_analysis(
    orderbook: pd.DataFrame,
    trades: pd.DataFrame,
    metrics: SpreadMetrics,
    output_path: Optional[str] = None,
) -> None:
    """Plot spread analysis results.

    Args:
        orderbook: Order book DataFrame.
        trades: Trade DataFrame.
        metrics: Computed spread metrics.
        output_path: If provided, save plot to this path instead of showing.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skipping plot.")
        return

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    # Panel 1: Price with bid/ask
    ax1 = axes[0]
    ax1.fill_between(orderbook["timestamp"], orderbook["bid"], orderbook["ask"],
                     alpha=0.3, color="blue", label="Bid-Ask")
    ax1.plot(orderbook["timestamp"], orderbook["midprice"],
             color="black", linewidth=0.5, label="Midprice")

    buys = trades[trades["side"] == "buy"]
    sells = trades[trades["side"] == "sell"]
    ax1.scatter(buys["timestamp"], buys["price"], color="green",
                s=10, alpha=0.6, label="Buys", zorder=5)
    ax1.scatter(sells["timestamp"], sells["price"], color="red",
                s=10, alpha=0.6, label="Sells", zorder=5)
    ax1.set_ylabel("Price")
    ax1.set_title("Order Book and Trades")
    ax1.legend(loc="upper left", fontsize=8)

    # Panel 2: Quoted spread over time
    ax2 = axes[1]
    quoted = compute_quoted_spread(orderbook)
    ax2.plot(orderbook["timestamp"], quoted, color="purple", linewidth=0.5)
    ax2.axhline(y=metrics.quoted_spread_bps, color="red", linestyle="--",
                label=f"Mean: {metrics.quoted_spread_bps:.1f} bps")
    ax2.set_ylabel("Quoted Spread (bps)")
    ax2.set_title("Quoted Spread Over Time")
    ax2.legend(fontsize=8)

    # Panel 3: Spread decomposition bar chart
    ax3 = axes[2]
    components = ["Quoted", "Effective", "Realized", "Adverse\nSelection"]
    values = [
        metrics.quoted_spread_bps,
        metrics.effective_spread_bps,
        metrics.realized_spread_bps,
        metrics.adverse_selection_bps,
    ]
    colors = ["steelblue", "seagreen", "coral", "crimson"]
    ax3.bar(components, values, color=colors, edgecolor="black", linewidth=0.5)
    for i, v in enumerate(values):
        ax3.text(i, v + 0.2, f"{v:.2f}", ha="center", fontsize=9)
    ax3.set_ylabel("Basis Points")
    ax3.set_title("Spread Decomposition")

    plt.tight_layout()
    if output_path:
        plt.savefig(output_path, dpi=150)
        print(f"Plot saved to {output_path}")
    else:
        plt.show()


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run spread analysis from command line."""
    parser = argparse.ArgumentParser(
        description="Bid-ask spread analysis and decomposition"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run with synthetic data (no API key needed)",
    )
    parser.add_argument(
        "--input", type=str, default=None,
        help="Path to CSV with trade data (columns: timestamp, price, side, midprice)",
    )
    parser.add_argument(
        "--plot", action="store_true",
        help="Show spread analysis plots",
    )
    parser.add_argument(
        "--save-plot", type=str, default=None,
        help="Save plot to file instead of displaying",
    )
    args = parser.parse_args()

    if args.demo:
        print("Generating synthetic order book and trades...")
        orderbook = generate_synthetic_orderbook(
            n_snapshots=2000,
            base_price=150.0,
            base_spread_bps=12.0,
            volatility=0.0008,
        )
        trades = generate_synthetic_trades(
            orderbook,
            trades_per_snapshot=0.25,
            informed_fraction=0.20,
        )
        print(f"  Order book snapshots: {len(orderbook):,}")
        print(f"  Trades generated:     {len(trades):,}")
        print()

    elif args.input:
        trades = pd.read_csv(args.input, parse_dates=["timestamp"])
        if "midprice" not in trades.columns:
            print("Error: CSV must have a 'midprice' column.")
            sys.exit(1)
        # Build a minimal orderbook from trade data
        orderbook = pd.DataFrame({
            "timestamp": trades["timestamp"],
            "midprice": trades["midprice"],
            "bid": trades["midprice"] * 0.9995,
            "ask": trades["midprice"] * 1.0005,
        })
        print(f"Loaded {len(trades):,} trades from {args.input}")
        print()
    else:
        print("Specify --demo or --input. Use --help for options.")
        sys.exit(1)

    # Run analysis
    print("Computing spread metrics...")
    metrics = analyze_spreads(trades, orderbook, delay_steps=50)
    print()
    print(metrics.summary())
    print()

    # Kyle's lambda
    print("Estimating Kyle's lambda...")
    kyle = compute_kyle_lambda(trades, interval="1s")
    print(f"  Lambda:       {kyle['lambda']:.6f}")
    print(f"  R-squared:    {kyle['r_squared']:.4f}")
    print(f"  N intervals:  {kyle['n_intervals']}")
    print()

    # Informed vs uninformed breakdown (demo only)
    if args.demo and "is_informed" in trades.columns:
        informed = trades[trades["is_informed"]]
        uninformed = trades[~trades["is_informed"]]
        print("=== Informed vs Uninformed Breakdown ===")
        print(f"  Informed trades:   {len(informed):,} ({len(informed)/len(trades)*100:.1f}%)")
        print(f"  Uninformed trades: {len(uninformed):,} ({len(uninformed)/len(trades)*100:.1f}%)")

        eff_informed = compute_effective_spread(informed)
        eff_uninformed = compute_effective_spread(uninformed)
        print(f"  Effective spread (informed):   {eff_informed.mean():.2f} bps")
        print(f"  Effective spread (uninformed): {eff_uninformed.mean():.2f} bps")
        print()

    # Plot
    if args.plot or args.save_plot:
        plot_spread_analysis(orderbook, trades, metrics, output_path=args.save_plot)


if __name__ == "__main__":
    main()
