#!/usr/bin/env python3
"""Almgren-Chriss optimal execution model.

Computes the analytically optimal execution trajectory for liquidating
a position under the Almgren-Chriss framework with linear temporary
and permanent price impact. Compares the optimal trajectory to TWAP
and shows cost breakdown.

Usage:
    python scripts/almgren_chriss.py
    python scripts/almgren_chriss.py --quantity 500 --steps 30 --risk-aversion 1e-5

Dependencies:
    uv pip install numpy

Environment Variables:
    None required — runs entirely with analytical computations.

Reference:
    Almgren, R. & Chriss, N. (2001). "Optimal execution of portfolio
    transactions." Journal of Risk, 3(2), 5-39.
"""

import argparse
import math
import sys
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


# ── Configuration ───────────────────────────────────────────────────

@dataclass
class ACParams:
    """Parameters for the Almgren-Chriss model."""

    total_quantity: float = 100.0      # Q: total shares to liquidate
    num_steps: int = 20                # N: number of trading periods
    time_horizon: float = 1.0          # T: total time (arbitrary units)
    volatility: float = 0.02           # sigma: price volatility per unit time
    temporary_impact: float = 0.001    # eta: temporary impact coefficient
    permanent_impact: float = 0.0005   # gamma: permanent impact coefficient
    fixed_cost: float = 0.0001         # epsilon: fixed cost per trade (half-spread)
    risk_aversion: float = 1e-5        # lambda: risk aversion parameter
    initial_price: float = 100.0       # S0: initial stock price


# ── Core Computations ──────────────────────────────────────────────

def compute_kappa(params: ACParams) -> float:
    """Compute the urgency parameter kappa.

    Kappa controls how front-loaded the optimal trajectory is.
    Higher kappa = more urgent execution.

    Args:
        params: Almgren-Chriss model parameters.

    Returns:
        The kappa parameter value.
    """
    tau = params.time_horizon / params.num_steps
    eta = params.temporary_impact
    sigma = params.volatility
    lam = params.risk_aversion

    inner = (tau ** 2 * lam * sigma ** 2) / (2.0 * eta) + 1.0
    kappa = math.acosh(inner)
    return kappa


def compute_optimal_trajectory(params: ACParams) -> Tuple[np.ndarray, np.ndarray]:
    """Compute the optimal execution trajectory.

    Returns the inventory schedule x_k (remaining quantity at step k)
    and the trade schedule n_k (quantity traded at step k).

    Args:
        params: Almgren-Chriss model parameters.

    Returns:
        Tuple of (inventory_schedule, trade_schedule).
        inventory_schedule: array of length N+1, from Q down to 0.
        trade_schedule: array of length N, trades per step.
    """
    n = params.num_steps
    q = params.total_quantity
    kappa = compute_kappa(params)

    # Inventory at each step: x_k = Q * sinh(kappa * (N - k)) / sinh(kappa * N)
    inventory = np.zeros(n + 1)
    sinh_kn = math.sinh(kappa * n)

    for k in range(n + 1):
        inventory[k] = q * math.sinh(kappa * (n - k)) / sinh_kn

    # Trade schedule: n_k = x_{k-1} - x_k (positive = selling)
    trades = -np.diff(inventory)

    return inventory, trades


def compute_twap_trajectory(params: ACParams) -> Tuple[np.ndarray, np.ndarray]:
    """Compute the TWAP (equal-split) trajectory.

    Args:
        params: Almgren-Chriss model parameters.

    Returns:
        Tuple of (inventory_schedule, trade_schedule).
    """
    n = params.num_steps
    q = params.total_quantity

    trades = np.full(n, q / n)
    inventory = np.zeros(n + 1)
    inventory[0] = q
    for k in range(n):
        inventory[k + 1] = inventory[k] - trades[k]

    return inventory, trades


def compute_expected_cost(
    inventory: np.ndarray,
    trades: np.ndarray,
    params: ACParams,
) -> dict:
    """Compute expected execution cost and its components.

    Args:
        inventory: Inventory schedule (length N+1).
        trades: Trade schedule (length N).
        params: Model parameters.

    Returns:
        Dictionary with cost breakdown.
    """
    tau = params.time_horizon / params.num_steps
    n = params.num_steps
    q = params.total_quantity

    # Permanent impact cost: 0.5 * gamma * Q^2
    permanent_cost = 0.5 * params.permanent_impact * q ** 2

    # Fixed transaction cost: epsilon * sum(|n_k|)
    fixed_cost = params.fixed_cost * np.sum(np.abs(trades))

    # Temporary impact cost: eta * sum(n_k^2 / tau)
    temporary_cost = params.temporary_impact * np.sum(trades ** 2 / tau)

    # Timing risk (variance of cost): sigma^2 * tau * sum(x_k^2) for k=1..N
    # We use inventory[1:] since x_0 = Q is fixed
    timing_variance = params.volatility ** 2 * tau * np.sum(inventory[1:] ** 2)

    # Risk-adjusted cost
    risk_penalty = params.risk_aversion * timing_variance
    total_expected_cost = permanent_cost + fixed_cost + temporary_cost
    risk_adjusted_cost = total_expected_cost + risk_penalty

    return {
        "permanent_cost": permanent_cost,
        "fixed_cost": fixed_cost,
        "temporary_cost": temporary_cost,
        "total_expected_cost": total_expected_cost,
        "timing_variance": timing_variance,
        "timing_std": math.sqrt(timing_variance),
        "risk_penalty": risk_penalty,
        "risk_adjusted_cost": risk_adjusted_cost,
    }


def compute_efficient_frontier(
    params: ACParams,
    num_points: int = 10,
) -> List[Tuple[float, float]]:
    """Compute the efficient frontier: expected cost vs risk (std dev).

    Varies risk aversion from very patient to very urgent and plots
    the resulting cost-risk tradeoff.

    Args:
        params: Base model parameters.
        num_points: Number of points on the frontier.

    Returns:
        List of (expected_cost, cost_std_dev) tuples.
    """
    frontier: List[Tuple[float, float]] = []
    lambdas = np.logspace(-7, -2, num_points)

    for lam in lambdas:
        p = ACParams(
            total_quantity=params.total_quantity,
            num_steps=params.num_steps,
            time_horizon=params.time_horizon,
            volatility=params.volatility,
            temporary_impact=params.temporary_impact,
            permanent_impact=params.permanent_impact,
            fixed_cost=params.fixed_cost,
            risk_aversion=lam,
            initial_price=params.initial_price,
        )
        inventory, trades = compute_optimal_trajectory(p)
        costs = compute_expected_cost(inventory, trades, p)
        frontier.append((costs["total_expected_cost"], costs["timing_std"]))

    return frontier


# ── Reporting ───────────────────────────────────────────────────────

def print_trajectory_comparison(params: ACParams) -> None:
    """Print optimal vs TWAP trajectory comparison.

    Args:
        params: Almgren-Chriss model parameters.
    """
    kappa = compute_kappa(params)
    tau = params.time_horizon / params.num_steps

    opt_inv, opt_trades = compute_optimal_trajectory(params)
    twap_inv, twap_trades = compute_twap_trajectory(params)

    opt_costs = compute_expected_cost(opt_inv, opt_trades, params)
    twap_costs = compute_expected_cost(twap_inv, twap_trades, params)

    print("=" * 72)
    print("ALMGREN-CHRISS OPTIMAL EXECUTION")
    print("=" * 72)
    print()
    print("Model Parameters:")
    print(f"  Total quantity (Q):      {params.total_quantity:.1f}")
    print(f"  Time horizon (T):        {params.time_horizon:.2f}")
    print(f"  Time steps (N):          {params.num_steps}")
    print(f"  Step size (tau):         {tau:.4f}")
    print(f"  Volatility (sigma):      {params.volatility:.4f}")
    print(f"  Temp. impact (eta):      {params.temporary_impact:.6f}")
    print(f"  Perm. impact (gamma):    {params.permanent_impact:.6f}")
    print(f"  Fixed cost (epsilon):    {params.fixed_cost:.6f}")
    print(f"  Risk aversion (lambda):  {params.risk_aversion:.2e}")
    print(f"  Initial price (S0):      {params.initial_price:.2f}")
    print()
    print(f"  Urgency parameter (kappa): {kappa:.6f}")
    print()

    # Trajectory table
    print("-" * 72)
    print(f"{'Step':>6} {'Optimal':>12} {'TWAP':>12} {'Opt Inv':>12} {'TWAP Inv':>12}")
    print(f"{'':>6} {'Trade':>12} {'Trade':>12} {'Remaining':>12} {'Remaining':>12}")
    print("-" * 72)

    for k in range(params.num_steps):
        print(f"{k:>6} {opt_trades[k]:>12.4f} {twap_trades[k]:>12.4f} "
              f"{opt_inv[k]:>12.4f} {twap_inv[k]:>12.4f}")

    print(f"{'end':>6} {'':>12} {'':>12} "
          f"{opt_inv[-1]:>12.4f} {twap_inv[-1]:>12.4f}")
    print("-" * 72)
    print()

    # Cost comparison
    print("Cost Breakdown:")
    print(f"{'Component':<25} {'Optimal':>15} {'TWAP':>15}")
    print("-" * 55)
    print(f"{'Permanent impact':<25} {opt_costs['permanent_cost']:>15.6f} "
          f"{twap_costs['permanent_cost']:>15.6f}")
    print(f"{'Fixed transaction':<25} {opt_costs['fixed_cost']:>15.6f} "
          f"{twap_costs['fixed_cost']:>15.6f}")
    print(f"{'Temporary impact':<25} {opt_costs['temporary_cost']:>15.6f} "
          f"{twap_costs['temporary_cost']:>15.6f}")
    print(f"{'Total expected cost':<25} {opt_costs['total_expected_cost']:>15.6f} "
          f"{twap_costs['total_expected_cost']:>15.6f}")
    print(f"{'Timing risk (std)':<25} {opt_costs['timing_std']:>15.6f} "
          f"{twap_costs['timing_std']:>15.6f}")
    print(f"{'Risk penalty (lam*var)':<25} {opt_costs['risk_penalty']:>15.6f} "
          f"{twap_costs['risk_penalty']:>15.6f}")
    print("-" * 55)
    print(f"{'Risk-adjusted cost':<25} {opt_costs['risk_adjusted_cost']:>15.6f} "
          f"{twap_costs['risk_adjusted_cost']:>15.6f}")
    print()

    # Improvement
    if abs(twap_costs["risk_adjusted_cost"]) > 1e-12:
        improvement = ((twap_costs["risk_adjusted_cost"] - opt_costs["risk_adjusted_cost"])
                       / abs(twap_costs["risk_adjusted_cost"]) * 100)
        print(f"Optimal risk-adjusted cost improvement vs TWAP: {improvement:+.2f}%")
    print()


def print_efficient_frontier(params: ACParams) -> None:
    """Print the efficient frontier (cost vs risk tradeoff).

    Args:
        params: Base model parameters.
    """
    frontier = compute_efficient_frontier(params, num_points=8)

    print("=" * 72)
    print("EFFICIENT FRONTIER (Cost vs Risk)")
    print("=" * 72)
    print()
    print(f"{'Expected Cost':>15} {'Cost Std Dev':>15} {'Tradeoff':>15}")
    print("-" * 45)

    for cost, std in frontier:
        if std > 1e-12:
            ratio = cost / std
            print(f"{cost:>15.6f} {std:>15.6f} {ratio:>15.4f}")
        else:
            print(f"{cost:>15.6f} {std:>15.6f} {'N/A':>15}")

    print()
    print("Lower expected cost requires accepting higher risk (std dev).")
    print("Higher risk aversion pushes the solution toward lower risk, higher cost.")
    print()


def print_sensitivity_analysis(params: ACParams) -> None:
    """Print sensitivity of optimal cost to key parameters.

    Args:
        params: Base model parameters.
    """
    print("=" * 72)
    print("SENSITIVITY ANALYSIS")
    print("=" * 72)
    print()

    base_inv, base_trades = compute_optimal_trajectory(params)
    base_costs = compute_expected_cost(base_inv, base_trades, params)
    base_total = base_costs["risk_adjusted_cost"]

    sensitivities = [
        ("Volatility (sigma)", "volatility", [0.01, 0.02, 0.04, 0.08]),
        ("Temp. impact (eta)", "temporary_impact", [0.0005, 0.001, 0.002, 0.004]),
        ("Risk aversion (lam)", "risk_aversion", [1e-6, 1e-5, 1e-4, 1e-3]),
        ("Time steps (N)", "num_steps", [5, 10, 20, 40]),
    ]

    for label, attr, values in sensitivities:
        print(f"\n{label}:")
        print(f"  {'Value':>12} {'Risk-Adj Cost':>15} {'vs Base':>12}")
        print(f"  {'-' * 39}")

        for val in values:
            p = ACParams(
                total_quantity=params.total_quantity,
                num_steps=int(val) if attr == "num_steps" else params.num_steps,
                time_horizon=params.time_horizon,
                volatility=val if attr == "volatility" else params.volatility,
                temporary_impact=val if attr == "temporary_impact" else params.temporary_impact,
                permanent_impact=params.permanent_impact,
                fixed_cost=params.fixed_cost,
                risk_aversion=val if attr == "risk_aversion" else params.risk_aversion,
                initial_price=params.initial_price,
            )
            inv, trades = compute_optimal_trajectory(p)
            costs = compute_expected_cost(inv, trades, p)
            total = costs["risk_adjusted_cost"]
            if abs(base_total) > 1e-12:
                change = (total - base_total) / abs(base_total) * 100
                print(f"  {val:>12.6f} {total:>15.6f} {change:>+11.1f}%")
            else:
                print(f"  {val:>12.6f} {total:>15.6f} {'N/A':>12}")

    print()


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Run the Almgren-Chriss optimal execution analysis."""
    parser = argparse.ArgumentParser(
        description="Almgren-Chriss optimal execution model."
    )
    parser.add_argument(
        "--quantity", type=float, default=100.0,
        help="Total quantity to execute (default: 100.0)",
    )
    parser.add_argument(
        "--steps", type=int, default=20,
        help="Number of execution steps (default: 20)",
    )
    parser.add_argument(
        "--horizon", type=float, default=1.0,
        help="Time horizon in arbitrary units (default: 1.0)",
    )
    parser.add_argument(
        "--volatility", type=float, default=0.02,
        help="Price volatility per unit time (default: 0.02)",
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
        "--risk-aversion", type=float, default=1e-5,
        help="Risk aversion parameter (default: 1e-5)",
    )
    parser.add_argument(
        "--frontier", action="store_true",
        help="Show the efficient frontier",
    )
    parser.add_argument(
        "--sensitivity", action="store_true",
        help="Show sensitivity analysis",
    )
    args = parser.parse_args()

    params = ACParams(
        total_quantity=args.quantity,
        num_steps=args.steps,
        time_horizon=args.horizon,
        volatility=args.volatility,
        temporary_impact=args.temp_impact,
        permanent_impact=args.perm_impact,
        risk_aversion=args.risk_aversion,
    )

    print_trajectory_comparison(params)

    if args.frontier:
        print_efficient_frontier(params)

    if args.sensitivity:
        print_sensitivity_analysis(params)

    # Default: show all sections
    if not args.frontier and not args.sensitivity:
        print_efficient_frontier(params)
        print_sensitivity_analysis(params)


if __name__ == "__main__":
    main()
