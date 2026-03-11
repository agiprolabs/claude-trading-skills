#!/usr/bin/env python3
"""Market maker simulation with inventory management and P&L tracking.

Simulates a simple market maker using the Avellaneda-Stoikov framework.
The MM quotes bid/ask prices that skew based on inventory, captures spread,
and faces adverse selection from informed traders. Includes --demo mode.

Usage:
    python scripts/market_maker_sim.py --demo
    python scripts/market_maker_sim.py --demo --gamma 0.1 --n-steps 5000

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
class MarketMakerState:
    """Current state of the market maker."""

    cash: float = 0.0
    inventory: int = 0
    n_trades: int = 0
    n_buys_filled: int = 0
    n_sells_filled: int = 0
    total_spread_captured: float = 0.0
    total_adverse_selection_loss: float = 0.0
    max_inventory: int = 0
    min_inventory: int = 0


@dataclass
class SimulationConfig:
    """Configuration for the market maker simulation."""

    n_steps: int = 2000
    initial_price: float = 100.0
    volatility: float = 0.001
    gamma: float = 0.05           # risk aversion
    k: float = 1.5                # order arrival intensity
    base_spread_bps: float = 10.0 # minimum spread
    max_inventory: int = 50       # inventory limit
    informed_fraction: float = 0.15
    trade_probability: float = 0.3
    seed: int = 42


@dataclass
class TradeRecord:
    """Record of a single fill."""

    step: int
    side: str             # "buy" or "sell" (from MM perspective)
    price: float
    midprice: float
    inventory_before: int
    inventory_after: int
    pnl: float            # immediate mark-to-market P&L
    is_informed: bool


@dataclass
class SimulationResult:
    """Complete simulation output."""

    config: SimulationConfig
    prices: np.ndarray
    inventories: np.ndarray
    pnl_series: np.ndarray
    bid_prices: np.ndarray
    ask_prices: np.ndarray
    trades: list[TradeRecord]
    final_state: MarketMakerState


# ── Price Simulation ────────────────────────────────────────────────


def simulate_price_path(
    n_steps: int,
    initial_price: float,
    volatility: float,
    seed: int = 42,
) -> np.ndarray:
    """Generate a geometric Brownian motion price path.

    Args:
        n_steps: Number of time steps.
        initial_price: Starting price.
        volatility: Per-step return volatility.
        seed: Random seed.

    Returns:
        Array of prices.
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, volatility, n_steps)
    # Add small drift and occasional jumps for realism
    jumps = rng.choice([0, 1], size=n_steps, p=[0.98, 0.02])
    jump_sizes = rng.normal(0, volatility * 5, n_steps) * jumps
    returns += jump_sizes
    prices = initial_price * np.exp(np.cumsum(returns))
    return prices


# ── Avellaneda-Stoikov Quoting ──────────────────────────────────────


def compute_optimal_quotes(
    midprice: float,
    inventory: int,
    gamma: float,
    sigma: float,
    time_remaining: float,
    k: float,
    min_spread_bps: float = 5.0,
) -> tuple[float, float]:
    """Compute optimal bid and ask using Avellaneda-Stoikov model.

    The reservation price shifts away from inventory, and the optimal
    spread depends on volatility and risk aversion.

    Args:
        midprice: Current fair price.
        inventory: Current inventory (positive = long).
        gamma: Risk aversion parameter.
        sigma: Volatility (per step).
        time_remaining: Fraction of session remaining (0 to 1).
        k: Order arrival rate parameter.
        min_spread_bps: Minimum spread floor in basis points.

    Returns:
        Tuple of (bid_price, ask_price).
    """
    # Reservation price: skew away from inventory
    T = max(time_remaining, 0.001)
    reservation_price = midprice - inventory * gamma * (sigma ** 2) * T

    # Optimal spread
    spread = gamma * (sigma ** 2) * T + (2.0 / gamma) * np.log(1 + gamma / k)

    # Apply minimum spread
    min_spread = midprice * min_spread_bps / 10_000
    spread = max(spread, min_spread)

    bid = reservation_price - spread / 2
    ask = reservation_price + spread / 2

    return bid, ask


# ── Simulation Engine ───────────────────────────────────────────────


def run_simulation(config: SimulationConfig) -> SimulationResult:
    """Run a complete market maker simulation.

    Args:
        config: Simulation parameters.

    Returns:
        SimulationResult with full history.
    """
    rng = np.random.default_rng(config.seed)

    # Generate true price path
    true_prices = simulate_price_path(
        config.n_steps, config.initial_price, config.volatility, config.seed
    )

    # State tracking arrays
    inventories = np.zeros(config.n_steps)
    pnl_series = np.zeros(config.n_steps)
    bid_prices = np.zeros(config.n_steps)
    ask_prices = np.zeros(config.n_steps)

    state = MarketMakerState()
    trades: list[TradeRecord] = []

    for t in range(config.n_steps):
        midprice = true_prices[t]
        time_remaining = (config.n_steps - t) / config.n_steps

        # Compute quotes
        bid, ask = compute_optimal_quotes(
            midprice=midprice,
            inventory=state.inventory,
            gamma=config.gamma,
            sigma=config.volatility,
            time_remaining=time_remaining,
            k=config.k,
            min_spread_bps=config.base_spread_bps,
        )

        # Enforce inventory limits by widening quotes
        if state.inventory >= config.max_inventory:
            bid = midprice * 0.99  # very low bid, discourage more buying
        if state.inventory <= -config.max_inventory:
            ask = midprice * 1.01  # very high ask, discourage more selling

        bid_prices[t] = bid
        ask_prices[t] = ask

        # Simulate incoming order
        if rng.random() < config.trade_probability:
            is_informed = rng.random() < config.informed_fraction

            if is_informed:
                # Informed trader knows future direction
                future_idx = min(t + 50, config.n_steps - 1)
                future_price = true_prices[future_idx]
                # Buy if price is going up, sell if going down
                incoming_side = "buy" if future_price > midprice else "sell"
            else:
                incoming_side = "buy" if rng.random() > 0.5 else "sell"

            if incoming_side == "buy" and ask <= midprice * 1.005:
                # Incoming buy lifts our ask -> we sell
                fill_price = ask
                state.cash += fill_price
                state.inventory -= 1
                state.n_sells_filled += 1
                state.n_trades += 1

                spread_captured = fill_price - midprice
                state.total_spread_captured += spread_captured

                trades.append(TradeRecord(
                    step=t,
                    side="sell",
                    price=fill_price,
                    midprice=midprice,
                    inventory_before=state.inventory + 1,
                    inventory_after=state.inventory,
                    pnl=spread_captured,
                    is_informed=is_informed,
                ))

            elif incoming_side == "sell" and bid >= midprice * 0.995:
                # Incoming sell hits our bid -> we buy
                fill_price = bid
                state.cash -= fill_price
                state.inventory += 1
                state.n_buys_filled += 1
                state.n_trades += 1

                spread_captured = midprice - fill_price
                state.total_spread_captured += spread_captured

                trades.append(TradeRecord(
                    step=t,
                    side="buy",
                    price=fill_price,
                    midprice=midprice,
                    inventory_before=state.inventory - 1,
                    inventory_after=state.inventory,
                    pnl=spread_captured,
                    is_informed=is_informed,
                ))

        # Track state
        state.max_inventory = max(state.max_inventory, state.inventory)
        state.min_inventory = min(state.min_inventory, state.inventory)
        inventories[t] = state.inventory
        # Mark-to-market P&L: cash + inventory * midprice
        pnl_series[t] = state.cash + state.inventory * midprice

    # Compute adverse selection loss from informed trades
    informed_trades = [tr for tr in trades if tr.is_informed]
    for tr in informed_trades:
        future_idx = min(tr.step + 50, config.n_steps - 1)
        future_mid = true_prices[future_idx]
        if tr.side == "sell":
            # We sold; if price went up, we lost
            loss = max(0, future_mid - tr.price)
        else:
            # We bought; if price went down, we lost
            loss = max(0, tr.price - future_mid)
        state.total_adverse_selection_loss += loss

    return SimulationResult(
        config=config,
        prices=true_prices,
        inventories=inventories,
        pnl_series=pnl_series,
        bid_prices=bid_prices,
        ask_prices=ask_prices,
        trades=trades,
        final_state=state,
    )


# ── Reporting ───────────────────────────────────────────────────────


def print_report(result: SimulationResult) -> None:
    """Print a summary report of the simulation.

    Args:
        result: Completed simulation result.
    """
    state = result.final_state
    config = result.config
    final_mid = result.prices[-1]
    final_pnl = state.cash + state.inventory * final_mid

    print("=" * 55)
    print("  MARKET MAKER SIMULATION REPORT")
    print("=" * 55)
    print()
    print(f"  Configuration:")
    print(f"    Steps:              {config.n_steps:,}")
    print(f"    Initial price:      ${config.initial_price:.2f}")
    print(f"    Volatility:         {config.volatility:.4f} per step")
    print(f"    Risk aversion (γ):  {config.gamma:.3f}")
    print(f"    Informed fraction:  {config.informed_fraction:.0%}")
    print(f"    Max inventory:      ±{config.max_inventory}")
    print()
    print(f"  Trading Activity:")
    print(f"    Total fills:        {state.n_trades:,}")
    print(f"    Buys (we bought):   {state.n_buys_filled:,}")
    print(f"    Sells (we sold):    {state.n_sells_filled:,}")
    print(f"    Fill rate:          {state.n_trades / config.n_steps:.1%} of steps")
    print()
    print(f"  Inventory:")
    print(f"    Final inventory:    {state.inventory:+d}")
    print(f"    Max inventory:      {state.max_inventory:+d}")
    print(f"    Min inventory:      {state.min_inventory:+d}")
    print()
    print(f"  P&L Breakdown:")
    print(f"    Spread captured:    ${state.total_spread_captured:+.2f}")
    print(f"    Adverse selection:  ${-state.total_adverse_selection_loss:.2f}")
    print(f"    Inventory value:    ${state.inventory * final_mid:+.2f}")
    print(f"    Final M2M P&L:      ${final_pnl:+.2f}")
    print()

    # Per-trade statistics
    if result.trades:
        spreads = [abs(tr.price - tr.midprice) / tr.midprice * 10_000
                   for tr in result.trades]
        print(f"  Per-Trade Stats:")
        print(f"    Avg spread captured: {np.mean(spreads):.2f} bps")
        print(f"    Median:              {np.median(spreads):.2f} bps")
        print(f"    Std:                 {np.std(spreads):.2f} bps")

        informed_count = sum(1 for tr in result.trades if tr.is_informed)
        print(f"    Informed fills:      {informed_count} ({informed_count/len(result.trades)*100:.1f}%)")
    print()

    # Sharpe-like metric
    if len(result.pnl_series) > 1:
        pnl_returns = np.diff(result.pnl_series)
        if np.std(pnl_returns) > 0:
            sharpe = np.mean(pnl_returns) / np.std(pnl_returns) * np.sqrt(252 * 24 * 60)
            print(f"  Risk-Adjusted (annualized Sharpe estimate): {sharpe:.2f}")
        print()


def plot_simulation(
    result: SimulationResult,
    output_path: Optional[str] = None,
) -> None:
    """Plot simulation results in a 4-panel chart.

    Args:
        result: Completed simulation result.
        output_path: If provided, save to file instead of showing.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skipping plot.")
        return

    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
    steps = np.arange(result.config.n_steps)

    # Panel 1: Price and quotes
    ax1 = axes[0]
    ax1.plot(steps, result.prices, color="black", linewidth=0.5, label="True Price")
    ax1.plot(steps, result.bid_prices, color="blue", linewidth=0.3, alpha=0.5, label="Bid")
    ax1.plot(steps, result.ask_prices, color="red", linewidth=0.3, alpha=0.5, label="Ask")

    buy_trades = [tr for tr in result.trades if tr.side == "buy"]
    sell_trades = [tr for tr in result.trades if tr.side == "sell"]
    if buy_trades:
        ax1.scatter([tr.step for tr in buy_trades],
                    [tr.price for tr in buy_trades],
                    color="green", s=8, alpha=0.6, label="We Buy", zorder=5)
    if sell_trades:
        ax1.scatter([tr.step for tr in sell_trades],
                    [tr.price for tr in sell_trades],
                    color="red", s=8, alpha=0.6, label="We Sell", zorder=5)
    ax1.set_ylabel("Price")
    ax1.set_title("Market Maker Simulation — Price and Quotes")
    ax1.legend(loc="upper left", fontsize=7)

    # Panel 2: Inventory
    ax2 = axes[1]
    ax2.fill_between(steps, 0, result.inventories, alpha=0.4,
                     color="steelblue", label="Inventory")
    ax2.axhline(y=0, color="black", linewidth=0.5)
    ax2.axhline(y=result.config.max_inventory, color="red",
                linewidth=0.5, linestyle="--", label="Limit")
    ax2.axhline(y=-result.config.max_inventory, color="red",
                linewidth=0.5, linestyle="--")
    ax2.set_ylabel("Inventory")
    ax2.set_title("Inventory Over Time")
    ax2.legend(fontsize=7)

    # Panel 3: Mark-to-Market P&L
    ax3 = axes[2]
    ax3.plot(steps, result.pnl_series, color="darkgreen", linewidth=0.8)
    ax3.axhline(y=0, color="black", linewidth=0.5)
    ax3.set_ylabel("P&L ($)")
    ax3.set_title("Cumulative Mark-to-Market P&L")

    # Panel 4: Spread over time
    ax4 = axes[3]
    spread_bps = (result.ask_prices - result.bid_prices) / result.prices * 10_000
    ax4.plot(steps, spread_bps, color="purple", linewidth=0.5)
    ax4.axhline(y=np.mean(spread_bps), color="red", linestyle="--",
                label=f"Mean: {np.mean(spread_bps):.1f} bps")
    ax4.set_ylabel("Spread (bps)")
    ax4.set_xlabel("Time Step")
    ax4.set_title("Quoted Spread Over Time")
    ax4.legend(fontsize=7)

    plt.tight_layout()
    if output_path:
        plt.savefig(output_path, dpi=150)
        print(f"Plot saved to {output_path}")
    else:
        plt.show()


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run market maker simulation from command line."""
    parser = argparse.ArgumentParser(
        description="Market maker simulation with Avellaneda-Stoikov quoting"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run with synthetic price path (no API key needed)",
    )
    parser.add_argument("--n-steps", type=int, default=2000, help="Simulation steps")
    parser.add_argument("--price", type=float, default=100.0, help="Initial price")
    parser.add_argument("--volatility", type=float, default=0.001, help="Per-step volatility")
    parser.add_argument("--gamma", type=float, default=0.05, help="Risk aversion (0.01-1.0)")
    parser.add_argument("--informed", type=float, default=0.15, help="Informed trader fraction")
    parser.add_argument("--max-inv", type=int, default=50, help="Max inventory limit")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--plot", action="store_true", help="Show plots")
    parser.add_argument("--save-plot", type=str, default=None, help="Save plot to file")

    args = parser.parse_args()

    if not args.demo:
        print("Use --demo to run the simulation. Use --help for options.")
        sys.exit(1)

    config = SimulationConfig(
        n_steps=args.n_steps,
        initial_price=args.price,
        volatility=args.volatility,
        gamma=args.gamma,
        informed_fraction=args.informed,
        max_inventory=args.max_inv,
        seed=args.seed,
    )

    print(f"Running market maker simulation ({config.n_steps:,} steps)...")
    print()

    result = run_simulation(config)
    print_report(result)

    # Parameter sensitivity analysis
    print("=== Gamma Sensitivity ===")
    print(f"  {'Gamma':>8}  {'Trades':>8}  {'Final P&L':>12}  {'Avg Spread':>12}")
    print(f"  {'─' * 8}  {'─' * 8}  {'─' * 12}  {'─' * 12}")
    for g in [0.01, 0.05, 0.1, 0.2, 0.5]:
        test_config = SimulationConfig(
            n_steps=config.n_steps,
            initial_price=config.initial_price,
            volatility=config.volatility,
            gamma=g,
            informed_fraction=config.informed_fraction,
            max_inventory=config.max_inventory,
            seed=config.seed,
        )
        test_result = run_simulation(test_config)
        final_pnl = test_result.final_state.cash + test_result.final_state.inventory * test_result.prices[-1]
        avg_spread = np.mean(
            (test_result.ask_prices - test_result.bid_prices) / test_result.prices * 10_000
        )
        print(f"  {g:>8.3f}  {test_result.final_state.n_trades:>8,}  ${final_pnl:>+11.2f}  {avg_spread:>10.1f} bps")
    print()

    if args.plot or args.save_plot:
        plot_simulation(result, output_path=args.save_plot)


if __name__ == "__main__":
    main()
