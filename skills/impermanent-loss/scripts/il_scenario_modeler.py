#!/usr/bin/env python3
"""Monte Carlo simulation of LP positions over time with IL and fee modeling.

Simulates many random price paths using geometric Brownian motion, computes
impermanent loss and fee accumulation for each path, and reports the
distribution of outcomes including probability of profit at various horizons.

Usage:
    python scripts/il_scenario_modeler.py
    python scripts/il_scenario_modeler.py --demo
    python scripts/il_scenario_modeler.py --days 90 --sims 500 --daily-vol 0.06
    python scripts/il_scenario_modeler.py --deposit 50000 --fee-rate 0.003

Dependencies:
    uv pip install numpy

Environment Variables:
    DAILY_VOL        - Daily volatility as decimal (default: 0.05 = 5%)
    FEE_RATE         - Pool fee rate as decimal (default: 0.003 = 0.30%)
    VOLUME_TVL_RATIO - Daily volume / TVL ratio (default: 0.5)
    DEPOSIT_SOL      - Deposit size in USD (default: 10000)
"""

import argparse
import math
import os
import sys
from typing import Optional

try:
    import numpy as np
except ImportError:
    print("numpy is required. Install with: uv pip install numpy")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────

DEFAULT_DAILY_VOL = float(os.getenv("DAILY_VOL", "0.05"))
DEFAULT_FEE_RATE = float(os.getenv("FEE_RATE", "0.003"))
DEFAULT_VOLUME_TVL = float(os.getenv("VOLUME_TVL_RATIO", "0.5"))
DEFAULT_DEPOSIT = float(os.getenv("DEPOSIT_SOL", "10000"))


# ── Core IL Functions ───────────────────────────────────────────────


def il_constant_product(price_ratio: float) -> float:
    """Compute IL for constant-product AMM.

    Args:
        price_ratio: P_new / P_initial.

    Returns:
        IL as decimal (negative = loss).
    """
    if price_ratio <= 0:
        raise ValueError(f"Price ratio must be positive, got {price_ratio}")
    r = price_ratio
    return 2.0 * math.sqrt(r) / (1.0 + r) - 1.0


def il_array(price_ratios: np.ndarray) -> np.ndarray:
    """Vectorized IL computation for arrays of price ratios.

    Args:
        price_ratios: Array of P_new / P_initial values.

    Returns:
        Array of IL values (negative = loss).
    """
    r = price_ratios
    return 2.0 * np.sqrt(r) / (1.0 + r) - 1.0


# ── Price Path Simulation ──────────────────────────────────────────


def simulate_price_paths(
    initial_price: float,
    daily_vol: float,
    days: int,
    n_sims: int,
    drift: float = 0.0,
    seed: Optional[int] = None,
) -> np.ndarray:
    """Generate random price paths using geometric Brownian motion.

    Args:
        initial_price: Starting price.
        daily_vol: Daily volatility (std dev of log returns).
        days: Number of days to simulate.
        n_sims: Number of simulation paths.
        drift: Daily drift (annualized return / 252). Default 0.
        seed: Random seed for reproducibility.

    Returns:
        Array of shape (n_sims, days + 1) with price paths.
    """
    if seed is not None:
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng()

    dt = 1.0  # daily time step
    log_returns = rng.normal(
        loc=(drift - 0.5 * daily_vol**2) * dt,
        scale=daily_vol * math.sqrt(dt),
        size=(n_sims, days),
    )

    # Cumulative sum of log returns → price paths
    cum_log_returns = np.cumsum(log_returns, axis=1)
    prices = initial_price * np.exp(cum_log_returns)

    # Prepend initial price
    initial_col = np.full((n_sims, 1), initial_price)
    return np.hstack([initial_col, prices])


# ── LP Position Simulation ─────────────────────────────────────────


def simulate_lp_positions(
    price_paths: np.ndarray,
    deposit: float,
    fee_rate: float,
    volume_tvl_ratio: float,
) -> dict[str, np.ndarray]:
    """Simulate LP positions across all price paths.

    Computes daily IL, daily fees, and cumulative net position for each path.

    Args:
        price_paths: Array of shape (n_sims, days + 1).
        deposit: Initial deposit in quote currency.
        fee_rate: Pool fee rate (e.g., 0.003 for 0.30%).
        volume_tvl_ratio: Daily volume / TVL ratio.

    Returns:
        Dictionary with:
            - price_ratios: (n_sims, days + 1) price ratios over time
            - il_pct: (n_sims, days + 1) IL at each timestep
            - cumulative_fees_pct: (n_sims, days + 1) cumulative fee income
            - net_pct: (n_sims, days + 1) net position (fees - IL)
            - hold_values: (n_sims, days + 1) hold portfolio values
            - lp_values: (n_sims, days + 1) LP values including fees
    """
    n_sims, n_steps = price_paths.shape
    initial_price = price_paths[0, 0]

    # Price ratios relative to initial
    price_ratios = price_paths / initial_price

    # IL at each timestep (relative to holding from day 0)
    il_pct = il_array(price_ratios)

    # Daily fee income as fraction of deposit
    # Assumes constant volume/TVL ratio and that fees accrue daily
    daily_fee_pct = volume_tvl_ratio * fee_rate
    cumulative_fees_pct = np.zeros_like(price_ratios)
    for t in range(1, n_steps):
        cumulative_fees_pct[:, t] = cumulative_fees_pct[:, t - 1] + daily_fee_pct

    # Net position: fees earned minus IL (IL is negative, so net = fees + IL)
    # Actually: net = fees_pct + il_pct (since il_pct is negative)
    # Positive net = profitable
    net_pct = cumulative_fees_pct + il_pct

    # Absolute values
    hold_values = deposit * (1.0 + price_ratios) / 2.0
    lp_values = hold_values * (1.0 + il_pct) + deposit * cumulative_fees_pct

    return {
        "price_ratios": price_ratios,
        "il_pct": il_pct,
        "cumulative_fees_pct": cumulative_fees_pct,
        "net_pct": net_pct,
        "hold_values": hold_values,
        "lp_values": lp_values,
    }


# ── Analysis and Reporting ──────────────────────────────────────────


def analyze_results(
    results: dict[str, np.ndarray],
    deposit: float,
    horizons: Optional[list[int]] = None,
) -> None:
    """Print comprehensive analysis of simulation results.

    Args:
        results: Output from simulate_lp_positions().
        deposit: Initial deposit value.
        horizons: List of day indices to analyze (default: [1, 7, 30, 90]).
    """
    n_sims, n_steps = results["net_pct"].shape
    max_day = n_steps - 1

    if horizons is None:
        horizons = [d for d in [1, 7, 14, 30, 60, 90, 180, 365] if d <= max_day]

    print(f"\n{'=' * 75}")
    print("  MONTE CARLO LP SIMULATION — RESULTS")
    print(f"{'=' * 75}")
    print(f"  Simulations: {n_sims:,}")
    print(f"  Time Horizon: {max_day} days")
    print(f"  Deposit: ${deposit:,.2f}")

    # Final day statistics
    final_net = results["net_pct"][:, -1]
    final_il = results["il_pct"][:, -1]
    final_fees = results["cumulative_fees_pct"][:, -1]

    print(f"\n  {'─' * 70}")
    print(f"  FINAL DAY ({max_day}) STATISTICS")
    print(f"  {'─' * 70}")
    print(f"  {'Metric':>25}  {'Mean':>10}  {'Median':>10}  {'5th %':>10}  {'95th %':>10}")
    print(f"  {'─' * 70}")

    for label, data in [
        ("IL (%)", final_il * 100),
        ("Fees Earned (%)", final_fees * 100),
        ("Net Position (%)", final_net * 100),
    ]:
        mean = np.mean(data)
        median = np.median(data)
        p5 = np.percentile(data, 5)
        p95 = np.percentile(data, 95)
        print(f"  {label:>25}  {mean:>+10.2f}  {median:>+10.2f}  {p5:>+10.2f}  {p95:>+10.2f}")

    # Probability of profit at various horizons
    print(f"\n  {'─' * 70}")
    print(f"  PROBABILITY OF PROFIT BY TIME HORIZON")
    print(f"  {'─' * 70}")
    print(
        f"  {'Day':>6}  {'P(Profit)':>10}  {'Mean Net':>10}  "
        f"{'Median Net':>12}  {'Worst 5%':>10}  {'Best 5%':>10}"
    )
    print(f"  {'─' * 70}")

    for day in horizons:
        if day >= n_steps:
            continue
        net = results["net_pct"][:, day]
        prob_profit = np.mean(net > 0) * 100
        mean_net = np.mean(net) * 100
        median_net = np.median(net) * 100
        worst_5 = np.percentile(net, 5) * 100
        best_5 = np.percentile(net, 95) * 100
        print(
            f"  {day:>6}  {prob_profit:>9.1f}%  {mean_net:>+9.2f}%  "
            f"{median_net:>+11.2f}%  {worst_5:>+9.2f}%  {best_5:>+9.2f}%"
        )

    # Scenario analysis
    print(f"\n  {'─' * 70}")
    print(f"  SCENARIO ANALYSIS (Day {max_day})")
    print(f"  {'─' * 70}")

    final_lp = results["lp_values"][:, -1]
    final_hold = results["hold_values"][:, -1]

    # Worst case
    worst_idx = np.argmin(final_net)
    print(f"  Worst Case (5th percentile net):")
    p5_net = np.percentile(final_net, 5)
    worst_mask = final_net <= np.percentile(final_net, 5)
    worst_avg_lp = np.mean(final_lp[worst_mask])
    worst_avg_hold = np.mean(final_hold[worst_mask])
    worst_avg_ratio = np.mean(results["price_ratios"][:, -1][worst_mask])
    print(f"    Price ratio: {worst_avg_ratio:.2f}x | LP: ${worst_avg_lp:,.0f} | Hold: ${worst_avg_hold:,.0f}")
    print(f"    Net: {p5_net * 100:+.2f}% (${p5_net * deposit:+,.0f})")

    # Median case
    median_net_val = np.median(final_net)
    med_mask = (final_net >= np.percentile(final_net, 45)) & (
        final_net <= np.percentile(final_net, 55)
    )
    if np.any(med_mask):
        med_avg_lp = np.mean(final_lp[med_mask])
        med_avg_hold = np.mean(final_hold[med_mask])
        med_avg_ratio = np.mean(results["price_ratios"][:, -1][med_mask])
    else:
        med_avg_lp = np.median(final_lp)
        med_avg_hold = np.median(final_hold)
        med_avg_ratio = np.median(results["price_ratios"][:, -1])

    print(f"  Median Case:")
    print(f"    Price ratio: {med_avg_ratio:.2f}x | LP: ${med_avg_lp:,.0f} | Hold: ${med_avg_hold:,.0f}")
    print(f"    Net: {median_net_val * 100:+.2f}% (${median_net_val * deposit:+,.0f})")

    # Best case
    p95_net = np.percentile(final_net, 95)
    best_mask = final_net >= np.percentile(final_net, 95)
    best_avg_lp = np.mean(final_lp[best_mask])
    best_avg_hold = np.mean(final_hold[best_mask])
    best_avg_ratio = np.mean(results["price_ratios"][:, -1][best_mask])
    print(f"  Best Case (95th percentile net):")
    print(f"    Price ratio: {best_avg_ratio:.2f}x | LP: ${best_avg_lp:,.0f} | Hold: ${best_avg_hold:,.0f}")
    print(f"    Net: {p95_net * 100:+.2f}% (${p95_net * deposit:+,.0f})")

    print(f"{'=' * 75}\n")


def print_sensitivity_analysis(
    deposit: float = 10000.0,
    days: int = 30,
    n_sims: int = 200,
    seed: int = 42,
) -> None:
    """Run sensitivity analysis across volatility and fee parameters.

    Args:
        deposit: Deposit size.
        days: Simulation horizon.
        n_sims: Simulations per scenario.
        seed: Random seed.
    """
    print(f"\n{'=' * 80}")
    print(f"  SENSITIVITY ANALYSIS — {days}-Day Horizon, {n_sims} Simulations Each")
    print(f"{'=' * 80}")
    print(
        f"  {'Daily Vol':>10}  {'Fee Rate':>10}  {'V/TVL':>6}  "
        f"{'P(Profit)':>10}  {'Mean Net':>10}  {'E[Daily Fee]':>13}"
    )
    print("-" * 80)

    vols = [0.02, 0.05, 0.08, 0.12]
    fee_rates = [0.001, 0.003, 0.01]
    vtl_ratios = [0.3, 0.8]

    for vol in vols:
        for fr in fee_rates:
            for vtl in vtl_ratios:
                paths = simulate_price_paths(
                    initial_price=100.0,
                    daily_vol=vol,
                    days=days,
                    n_sims=n_sims,
                    seed=seed,
                )
                results = simulate_lp_positions(paths, deposit, fr, vtl)
                final_net = results["net_pct"][:, -1]
                prob = np.mean(final_net > 0) * 100
                mean_net = np.mean(final_net) * 100
                daily_fee = vtl * fr * 100

                print(
                    f"  {vol * 100:>9.0f}%  {fr * 100:>9.2f}%  {vtl:>5.1f}  "
                    f"{prob:>9.1f}%  {mean_net:>+9.2f}%  {daily_fee:>12.4f}%"
                )

    print(f"{'=' * 80}")
    print("  Higher vol increases IL. Higher fee rate & V/TVL ratio increase fee income.")
    print("  P(Profit) = probability that fees > IL after the time horizon.\n")


# ── Demo Mode ───────────────────────────────────────────────────────


def run_demo() -> None:
    """Run a full demo with realistic SOL volatility parameters."""
    print("\n" + "#" * 75)
    print("#  IMPERMANENT LOSS SCENARIO MODELER — DEMO MODE")
    print("#  Simulating SOL/USDC LP position with realistic parameters")
    print("#" * 75)

    # Realistic SOL parameters
    daily_vol = 0.06  # ~6% daily vol (moderate for SOL)
    fee_rate = 0.0025  # 0.25% fee tier
    volume_tvl = 0.4  # 40% of TVL traded daily
    deposit = 10000.0
    days = 90
    n_sims = 500

    print(f"\n  Parameters:")
    print(f"    Daily Volatility: {daily_vol * 100:.1f}%")
    print(f"    Annualized Vol:   {daily_vol * math.sqrt(365) * 100:.0f}%")
    print(f"    Pool Fee Rate:    {fee_rate * 100:.2f}%")
    print(f"    Volume/TVL Ratio: {volume_tvl:.1f}")
    print(f"    Daily Fee Income: {volume_tvl * fee_rate * 100:.3f}% of deposit")
    print(f"    Expected Daily IL: {daily_vol ** 2 / 8 * 100:.4f}% of deposit")
    print(f"    Daily Edge:       {(volume_tvl * fee_rate - daily_vol ** 2 / 8) * 100:+.4f}%")
    print(f"    Deposit:          ${deposit:,.0f}")
    print(f"    Simulation Days:  {days}")
    print(f"    Simulations:      {n_sims}")

    # Run simulation
    print("\n  Simulating price paths...")
    paths = simulate_price_paths(
        initial_price=150.0,
        daily_vol=daily_vol,
        days=days,
        n_sims=n_sims,
        seed=42,
    )

    print("  Computing LP positions...")
    results = simulate_lp_positions(paths, deposit, fee_rate, volume_tvl)

    # Full analysis
    analyze_results(results, deposit)

    # Sensitivity
    print_sensitivity_analysis(deposit=deposit, days=30, n_sims=200, seed=42)

    print("Demo complete.")


# ── CLI ─────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Monte Carlo LP Position Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python il_scenario_modeler.py --demo\n"
            "  python il_scenario_modeler.py --days 90 --sims 500\n"
            "  python il_scenario_modeler.py --daily-vol 0.08 --fee-rate 0.01\n"
        ),
    )
    parser.add_argument("--demo", action="store_true", help="Run full demo")
    parser.add_argument(
        "--days", type=int, default=30, help="Simulation horizon in days (default: 30)"
    )
    parser.add_argument(
        "--sims", type=int, default=200, help="Number of simulations (default: 200)"
    )
    parser.add_argument(
        "--daily-vol",
        type=float,
        default=DEFAULT_DAILY_VOL,
        help=f"Daily volatility as decimal (default: {DEFAULT_DAILY_VOL})",
    )
    parser.add_argument(
        "--fee-rate",
        type=float,
        default=DEFAULT_FEE_RATE,
        help=f"Pool fee rate as decimal (default: {DEFAULT_FEE_RATE})",
    )
    parser.add_argument(
        "--volume-tvl",
        type=float,
        default=DEFAULT_VOLUME_TVL,
        help=f"Daily volume / TVL ratio (default: {DEFAULT_VOLUME_TVL})",
    )
    parser.add_argument(
        "--deposit",
        type=float,
        default=DEFAULT_DEPOSIT,
        help=f"Deposit size in USD (default: {DEFAULT_DEPOSIT})",
    )
    parser.add_argument(
        "--initial-price",
        type=float,
        default=150.0,
        help="Initial token price (default: 150)",
    )
    parser.add_argument(
        "--drift",
        type=float,
        default=0.0,
        help="Daily price drift (default: 0 = no trend)",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="Run sensitivity analysis across parameter combinations",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the scenario modeler."""
    args = parse_args()

    if args.demo:
        run_demo()
        return

    if args.sensitivity:
        print_sensitivity_analysis(
            deposit=args.deposit, days=args.days, n_sims=args.sims, seed=args.seed or 42
        )
        return

    # Standard simulation
    print(f"\n  Running {args.sims} simulations over {args.days} days...")
    print(f"  Daily vol: {args.daily_vol * 100:.1f}%")
    print(f"  Fee rate: {args.fee_rate * 100:.2f}%")
    print(f"  V/TVL ratio: {args.volume_tvl:.2f}")
    print(f"  Deposit: ${args.deposit:,.0f}")
    print(f"  Initial price: ${args.initial_price:,.2f}")

    daily_edge = args.volume_tvl * args.fee_rate - args.daily_vol**2 / 8
    print(f"  Expected daily edge: {daily_edge * 100:+.4f}%")

    paths = simulate_price_paths(
        initial_price=args.initial_price,
        daily_vol=args.daily_vol,
        days=args.days,
        n_sims=args.sims,
        drift=args.drift,
        seed=args.seed,
    )

    results = simulate_lp_positions(
        paths, args.deposit, args.fee_rate, args.volume_tvl
    )

    analyze_results(results, args.deposit)


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
