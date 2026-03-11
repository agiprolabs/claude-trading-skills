#!/usr/bin/env python3
"""Simulated order execution comparing TWAP, VWAP, and adaptive strategies.

Simulates a market with linear price impact (temporary + permanent) and
geometric Brownian motion price dynamics. Runs multiple trials for each
execution strategy and compares average cost, standard deviation, and
worst-case performance.

Usage:
    python scripts/execution_simulator.py

Dependencies:
    uv pip install numpy

Environment Variables:
    None required — runs entirely in simulation.
"""

import argparse
import math
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


# ── Configuration ───────────────────────────────────────────────────

@dataclass
class MarketParams:
    """Parameters for the simulated market."""

    initial_price: float = 100.0
    volatility: float = 0.02          # Per-step volatility (sigma)
    drift: float = 0.0                # Per-step drift (mu)
    temporary_impact: float = 0.001   # eta: temporary impact coefficient
    permanent_impact: float = 0.0005  # gamma: permanent impact coefficient
    base_spread: float = 0.001        # Base spread as fraction of price
    avg_volume: float = 1000.0        # Average volume per step


@dataclass
class OrderParams:
    """Parameters for the order to execute."""

    total_quantity: float = 100.0     # Total units to trade
    num_steps: int = 20               # Number of decision steps
    direction: int = 1                # 1 = buy, -1 = sell


@dataclass
class SimulationParams:
    """Parameters for the simulation."""

    num_trials: int = 1000            # Number of Monte Carlo trials
    random_seed: int = 42             # For reproducibility


@dataclass
class ExecutionResult:
    """Result from a single execution trial."""

    total_cost: float = 0.0           # Total implementation shortfall
    avg_exec_price: float = 0.0       # Volume-weighted avg execution price
    arrival_price: float = 0.0        # Price at order arrival
    final_price: float = 0.0         # Price at end of execution
    trades: List[Tuple[int, float, float]] = field(default_factory=list)


# ── Market Simulator ────────────────────────────────────────────────

class MarketSimulator:
    """Simulates a market with price impact for order execution."""

    def __init__(self, params: MarketParams, seed: Optional[int] = None) -> None:
        self.params = params
        self.rng = np.random.RandomState(seed)
        self.reset()

    def reset(self) -> float:
        """Reset market to initial state. Returns the initial price."""
        self.price = self.params.initial_price
        self.step_count = 0
        return self.price

    def volume_profile(self, step: int, total_steps: int) -> float:
        """U-shaped intraday volume profile.

        Args:
            step: Current step index.
            total_steps: Total number of steps.

        Returns:
            Volume multiplier (>1 at start/end, <1 in middle).
        """
        t = step / max(total_steps - 1, 1)
        return 1.0 + 0.5 * (4.0 * (t - 0.5) ** 2)

    def execute_trade(self, quantity: float) -> Tuple[float, float]:
        """Execute a trade and return (execution_price, post_trade_mid_price).

        Args:
            quantity: Units to trade (positive = buy, negative = sell).

        Returns:
            Tuple of (execution_price, new_mid_price).

        Raises:
            ValueError: If quantity is negative.
        """
        if quantity < 0:
            raise ValueError("Quantity must be non-negative; use direction for sell.")

        p = self.params
        trade_rate = quantity / p.avg_volume if p.avg_volume > 0 else 0.0

        # Price dynamics: GBM step
        dw = self.rng.normal(0, 1)
        price_return = p.drift + p.volatility * dw

        # Permanent impact (shifts the mid-price)
        perm_impact = p.permanent_impact * trade_rate

        # Update mid-price
        self.price *= (1.0 + price_return + perm_impact)

        # Temporary impact (affects execution price only)
        temp_impact = p.temporary_impact * trade_rate
        exec_price = self.price * (1.0 + temp_impact + p.base_spread / 2.0)

        self.step_count += 1
        return exec_price, self.price

    def get_price(self) -> float:
        """Return current mid-price."""
        return self.price


# ── Execution Strategies ────────────────────────────────────────────

def execute_twap(
    sim: MarketSimulator,
    order: OrderParams,
) -> ExecutionResult:
    """Execute order using TWAP strategy (equal splits).

    Args:
        sim: Market simulator instance.
        order: Order parameters.

    Returns:
        ExecutionResult with cost metrics.
    """
    arrival_price = sim.get_price()
    trade_per_step = order.total_quantity / order.num_steps
    total_cost = 0.0
    total_qty_executed = 0.0
    weighted_price_sum = 0.0
    trades: List[Tuple[int, float, float]] = []

    for step in range(order.num_steps):
        qty = trade_per_step
        exec_price, _ = sim.execute_trade(qty)
        cost = (exec_price - arrival_price) * qty * order.direction
        total_cost += cost
        weighted_price_sum += exec_price * qty
        total_qty_executed += qty
        trades.append((step, qty, exec_price))

    avg_price = weighted_price_sum / total_qty_executed if total_qty_executed > 0 else arrival_price

    return ExecutionResult(
        total_cost=total_cost,
        avg_exec_price=avg_price,
        arrival_price=arrival_price,
        final_price=sim.get_price(),
        trades=trades,
    )


def execute_vwap(
    sim: MarketSimulator,
    order: OrderParams,
) -> ExecutionResult:
    """Execute order using VWAP strategy (volume-weighted splits).

    Args:
        sim: Market simulator instance.
        order: Order parameters.

    Returns:
        ExecutionResult with cost metrics.
    """
    arrival_price = sim.get_price()

    # Compute expected volume profile
    volume_weights = np.array([
        sim.volume_profile(step, order.num_steps) for step in range(order.num_steps)
    ])
    volume_weights /= volume_weights.sum()

    total_cost = 0.0
    total_qty_executed = 0.0
    weighted_price_sum = 0.0
    trades: List[Tuple[int, float, float]] = []

    for step in range(order.num_steps):
        qty = order.total_quantity * volume_weights[step]
        exec_price, _ = sim.execute_trade(qty)
        cost = (exec_price - arrival_price) * qty * order.direction
        total_cost += cost
        weighted_price_sum += exec_price * qty
        total_qty_executed += qty
        trades.append((step, qty, exec_price))

    avg_price = weighted_price_sum / total_qty_executed if total_qty_executed > 0 else arrival_price

    return ExecutionResult(
        total_cost=total_cost,
        avg_exec_price=avg_price,
        arrival_price=arrival_price,
        final_price=sim.get_price(),
        trades=trades,
    )


def execute_adaptive(
    sim: MarketSimulator,
    order: OrderParams,
) -> ExecutionResult:
    """Execute order using a simple adaptive strategy.

    The adaptive strategy adjusts trade size based on:
    - Trade more when price is favorable (below arrival for buys)
    - Trade less when price is unfavorable
    - Ensure completion by increasing urgency as deadline approaches

    Args:
        sim: Market simulator instance.
        order: Order parameters.

    Returns:
        ExecutionResult with cost metrics.
    """
    arrival_price = sim.get_price()
    remaining = order.total_quantity
    total_cost = 0.0
    total_qty_executed = 0.0
    weighted_price_sum = 0.0
    trades: List[Tuple[int, float, float]] = []

    for step in range(order.num_steps):
        steps_left = order.num_steps - step
        current_price = sim.get_price()

        # Base rate: what we need to trade per remaining step
        base_rate = remaining / steps_left

        # Price signal: trade more when price is favorable
        price_ratio = current_price / arrival_price
        if order.direction == 1:  # Buying
            # Favorable = price below arrival
            price_signal = max(0.5, min(1.5, 2.0 - price_ratio))
        else:  # Selling
            # Favorable = price above arrival
            price_signal = max(0.5, min(1.5, price_ratio))

        # Urgency: increase as deadline approaches
        urgency = 1.0 + 0.5 * (1.0 - steps_left / order.num_steps)

        # Compute trade quantity
        qty = min(remaining, base_rate * price_signal * urgency)
        qty = max(qty, 0.0)

        if qty > 0:
            exec_price, _ = sim.execute_trade(qty)
            cost = (exec_price - arrival_price) * qty * order.direction
            total_cost += cost
            weighted_price_sum += exec_price * qty
            total_qty_executed += qty
            remaining -= qty
            trades.append((step, qty, exec_price))

    # Force-execute any remaining quantity at the last step
    if remaining > 1e-10:
        exec_price, _ = sim.execute_trade(remaining)
        cost = (exec_price - arrival_price) * remaining * order.direction
        total_cost += cost
        weighted_price_sum += exec_price * remaining
        total_qty_executed += remaining
        trades.append((order.num_steps, remaining, exec_price))

    avg_price = weighted_price_sum / total_qty_executed if total_qty_executed > 0 else arrival_price

    return ExecutionResult(
        total_cost=total_cost,
        avg_exec_price=avg_price,
        arrival_price=arrival_price,
        final_price=sim.get_price(),
        trades=trades,
    )


# ── Simulation Runner ───────────────────────────────────────────────

def run_simulation(
    strategy_fn,
    market_params: MarketParams,
    order_params: OrderParams,
    num_trials: int,
    base_seed: int,
) -> List[ExecutionResult]:
    """Run multiple trials of an execution strategy.

    Args:
        strategy_fn: Strategy function (execute_twap, execute_vwap, etc.).
        market_params: Market simulation parameters.
        order_params: Order parameters.
        num_trials: Number of Monte Carlo trials.
        base_seed: Base random seed for reproducibility.

    Returns:
        List of ExecutionResult, one per trial.
    """
    results: List[ExecutionResult] = []
    for trial in range(num_trials):
        sim = MarketSimulator(market_params, seed=base_seed + trial)
        result = strategy_fn(sim, order_params)
        results.append(result)
    return results


def compute_statistics(results: List[ExecutionResult]) -> dict:
    """Compute summary statistics from execution results.

    Args:
        results: List of ExecutionResult from multiple trials.

    Returns:
        Dictionary with mean, std, min, max, percentile metrics.
    """
    costs = np.array([r.total_cost for r in results])
    prices = np.array([r.avg_exec_price for r in results])

    return {
        "mean_cost": float(np.mean(costs)),
        "std_cost": float(np.std(costs)),
        "median_cost": float(np.median(costs)),
        "p5_cost": float(np.percentile(costs, 5)),
        "p95_cost": float(np.percentile(costs, 95)),
        "min_cost": float(np.min(costs)),
        "max_cost": float(np.max(costs)),
        "mean_exec_price": float(np.mean(prices)),
        "mean_arrival_price": float(np.mean([r.arrival_price for r in results])),
    }


# ── Reporting ───────────────────────────────────────────────────────

def print_report(
    strategy_stats: dict,
    order_params: OrderParams,
    market_params: MarketParams,
) -> None:
    """Print a formatted comparison report.

    Args:
        strategy_stats: Dict mapping strategy name to statistics dict.
        order_params: Order parameters used.
        market_params: Market parameters used.
    """
    print("=" * 72)
    print("EXECUTION STRATEGY COMPARISON REPORT")
    print("=" * 72)
    print()
    print("Market Parameters:")
    print(f"  Initial price:      {market_params.initial_price:.2f}")
    print(f"  Volatility (σ):     {market_params.volatility:.4f} per step")
    print(f"  Temporary impact:   {market_params.temporary_impact:.4f}")
    print(f"  Permanent impact:   {market_params.permanent_impact:.4f}")
    print(f"  Base spread:        {market_params.base_spread:.4f}")
    print()
    print("Order Parameters:")
    print(f"  Total quantity:     {order_params.total_quantity:.1f}")
    print(f"  Time steps:         {order_params.num_steps}")
    direction = "BUY" if order_params.direction == 1 else "SELL"
    print(f"  Direction:          {direction}")
    print()
    print("-" * 72)
    print(f"{'Strategy':<15} {'Mean Cost':>12} {'Std Dev':>12} {'Median':>12} "
          f"{'P95 Cost':>12} {'Worst':>12}")
    print("-" * 72)

    for name, stats in strategy_stats.items():
        print(f"{name:<15} {stats['mean_cost']:>12.4f} {stats['std_cost']:>12.4f} "
              f"{stats['median_cost']:>12.4f} {stats['p95_cost']:>12.4f} "
              f"{stats['max_cost']:>12.4f}")

    print("-" * 72)
    print()

    # Relative comparison vs TWAP
    if "TWAP" in strategy_stats:
        twap_mean = strategy_stats["TWAP"]["mean_cost"]
        print("Improvement vs TWAP:")
        for name, stats in strategy_stats.items():
            if name == "TWAP":
                continue
            if abs(twap_mean) > 1e-10:
                improvement = (twap_mean - stats["mean_cost"]) / abs(twap_mean) * 100
                print(f"  {name:<15} {improvement:>+8.2f}%")
            else:
                diff = twap_mean - stats["mean_cost"]
                print(f"  {name:<15} {diff:>+8.4f} (absolute)")

    print()
    print("Cost = implementation shortfall (positive = cost, negative = savings)")
    print("Lower is better for all metrics.")
    print()


def print_sample_trajectory(
    market_params: MarketParams,
    order_params: OrderParams,
    seed: int = 42,
) -> None:
    """Print a sample execution trajectory for each strategy.

    Args:
        market_params: Market simulation parameters.
        order_params: Order parameters.
        seed: Random seed for the sample.
    """
    print("=" * 72)
    print("SAMPLE EXECUTION TRAJECTORY (single trial)")
    print("=" * 72)

    strategies = {
        "TWAP": execute_twap,
        "VWAP": execute_vwap,
        "Adaptive": execute_adaptive,
    }

    for name, strategy_fn in strategies.items():
        sim = MarketSimulator(market_params, seed=seed)
        result = strategy_fn(sim, order_params)
        print(f"\n{name} Strategy:")
        print(f"  Arrival price: {result.arrival_price:.4f}")
        print(f"  {'Step':>6} {'Quantity':>10} {'Exec Price':>12} {'Cumulative':>12}")
        cumulative = 0.0
        for step, qty, price in result.trades:
            cumulative += qty
            print(f"  {step:>6} {qty:>10.2f} {price:>12.4f} {cumulative:>12.2f}")
        print(f"  Total cost: {result.total_cost:.4f}")
        print(f"  Avg exec price: {result.avg_exec_price:.4f}")


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Run the execution simulation comparison."""
    parser = argparse.ArgumentParser(
        description="Compare execution strategies in a simulated market."
    )
    parser.add_argument(
        "--trials", type=int, default=1000,
        help="Number of Monte Carlo trials (default: 1000)",
    )
    parser.add_argument(
        "--quantity", type=float, default=100.0,
        help="Total order quantity (default: 100.0)",
    )
    parser.add_argument(
        "--steps", type=int, default=20,
        help="Number of execution steps (default: 20)",
    )
    parser.add_argument(
        "--volatility", type=float, default=0.02,
        help="Per-step volatility (default: 0.02)",
    )
    parser.add_argument(
        "--temp-impact", type=float, default=0.001,
        help="Temporary impact coefficient (default: 0.001)",
    )
    parser.add_argument(
        "--perm-impact", type=float, default=0.0005,
        help="Permanent impact coefficient (default: 0.0005)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--trajectory", action="store_true",
        help="Print a sample execution trajectory",
    )
    args = parser.parse_args()

    market_params = MarketParams(
        volatility=args.volatility,
        temporary_impact=args.temp_impact,
        permanent_impact=args.perm_impact,
    )
    order_params = OrderParams(
        total_quantity=args.quantity,
        num_steps=args.steps,
    )

    strategies = {
        "TWAP": execute_twap,
        "VWAP": execute_vwap,
        "Adaptive": execute_adaptive,
    }

    print(f"Running {args.trials} trials per strategy...\n")

    strategy_stats = {}
    for name, strategy_fn in strategies.items():
        results = run_simulation(
            strategy_fn, market_params, order_params,
            num_trials=args.trials, base_seed=args.seed,
        )
        strategy_stats[name] = compute_statistics(results)

    print_report(strategy_stats, order_params, market_params)

    if args.trajectory:
        print_sample_trajectory(market_params, order_params, seed=args.seed)


if __name__ == "__main__":
    main()
