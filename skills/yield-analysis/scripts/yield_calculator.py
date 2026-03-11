#!/usr/bin/env python3
"""Offline DeFi yield calculator with fee APR, IL estimation, net yield,
break-even analysis, and sensitivity reporting.

Computes real yield from pool parameters without requiring any API calls.
Includes a --demo mode that compares three representative pool scenarios
(stablecoin, correlated, volatile).

Usage:
    python scripts/yield_calculator.py
    python scripts/yield_calculator.py --demo
    python scripts/yield_calculator.py --tvl 5000000 --volume 1500000 --fee-rate 0.0025 --volatility 0.8

Dependencies:
    uv pip install numpy

Environment Variables:
    None required — this script runs entirely offline.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from typing import Optional

try:
    import numpy as np
except ImportError:
    print("numpy is required. Install with: uv pip install numpy")
    sys.exit(1)


# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class PoolParams:
    """Parameters describing a liquidity pool and position."""

    name: str
    tvl: float  # Total pool TVL in USD
    daily_volume: float  # Average daily trading volume in USD
    fee_rate: float  # Swap fee rate (e.g. 0.0025 for 0.25%)
    annual_volatility: float  # Annualised volatility of the price ratio (0-1+)
    emission_apr: float  # Emission-based APR as decimal (e.g. 0.10 for 10%)
    emission_depreciation: float  # Expected 30-day emission token decline (0-1)
    position_size: float  # Your deposit in USD
    gas_cost_annual: float  # Estimated annual gas/tx costs in USD
    rebalance_cost_annual: float  # CLMM rebalance costs in USD (0 for standard pools)


@dataclass
class YieldReport:
    """Computed yield metrics for a pool position."""

    pool_name: str
    fee_apr: float
    emission_apr_raw: float
    emission_apr_adjusted: float
    estimated_il: float
    gas_cost_pct: float
    rebalance_cost_pct: float
    net_apr: float
    net_apy: float
    daily_income: float
    annual_income: float
    break_even_days: Optional[float]
    hold_vs_lp_advantage: float  # positive = LP is better


# ── Core Calculations ───────────────────────────────────────────────


def fee_apr(daily_volume: float, fee_rate: float, tvl: float) -> float:
    """Calculate annualised fee APR for a liquidity pool.

    Args:
        daily_volume: Average daily trading volume in USD.
        fee_rate: Swap fee rate as decimal (e.g. 0.0025).
        tvl: Total pool TVL in USD.

    Returns:
        Fee APR as a decimal (e.g. 0.20 for 20%).
    """
    if tvl <= 0:
        return 0.0
    return (daily_volume * fee_rate / tvl) * 365


def estimate_annual_il(annual_volatility: float) -> float:
    """Estimate annualised impermanent loss from volatility.

    Uses the approximation for constant-product AMMs:
        IL ≈ volatility^2 / 8
    This is a second-order Taylor expansion valid for moderate price moves.

    For high-volatility assets, actual IL may exceed this estimate.

    Args:
        annual_volatility: Annualised price-ratio volatility as decimal.

    Returns:
        Estimated annual IL as a positive decimal (e.g. 0.08 for 8%).
    """
    return (annual_volatility ** 2) / 8


def il_from_price_ratio(price_ratio: float) -> float:
    """Exact IL for a constant-product AMM given a price ratio change.

    Formula: IL = 2 * sqrt(r) / (1 + r) - 1

    Args:
        price_ratio: P_new / P_initial (e.g. 2.0 for a 2x price increase).

    Returns:
        IL as a negative decimal (e.g. -0.0566 for ~5.7% loss).
    """
    if price_ratio <= 0:
        return -1.0
    return 2 * math.sqrt(price_ratio) / (1 + price_ratio) - 1


def apr_to_apy(apr: float, compounds_per_year: int = 365) -> float:
    """Convert APR to APY with specified compounding frequency.

    Args:
        apr: Annual percentage rate as decimal.
        compounds_per_year: Number of compounding periods.

    Returns:
        APY as a decimal.
    """
    if compounds_per_year <= 0:
        return apr
    return (1 + apr / compounds_per_year) ** compounds_per_year - 1


def compute_yield(params: PoolParams) -> YieldReport:
    """Compute full yield report for a pool position.

    Args:
        params: Pool and position parameters.

    Returns:
        Complete yield analysis report.
    """
    # Fee income
    f_apr = fee_apr(params.daily_volume, params.fee_rate, params.tvl)

    # Emission yield adjusted for depreciation
    emission_raw = params.emission_apr
    emission_adj = emission_raw * (1 - params.emission_depreciation)

    # IL estimate
    il_annual = estimate_annual_il(params.annual_volatility)

    # Cost percentages relative to position
    gas_pct = params.gas_cost_annual / params.position_size if params.position_size > 0 else 0
    rebalance_pct = params.rebalance_cost_annual / params.position_size if params.position_size > 0 else 0

    # Net APR
    net = f_apr + emission_adj - il_annual - gas_pct - rebalance_pct

    # Net APY (daily compounding)
    net_apy = apr_to_apy(max(net, 0), 365) if net > 0 else net

    # Daily and annual income
    daily = net * params.position_size / 365
    annual = net * params.position_size

    # Break-even: how many days until fee income covers IL + costs
    daily_gross = (f_apr + emission_adj) * params.position_size / 365
    daily_cost = (il_annual + gas_pct + rebalance_pct) * params.position_size / 365
    if daily_gross > daily_cost and daily_cost > 0:
        # Days for cumulative net to cover initial entry cost (~$1 gas on Solana)
        entry_cost = 1.0  # approximate Solana deposit cost
        break_even = entry_cost / (daily_gross - daily_cost)
    elif daily_gross <= daily_cost:
        break_even = None  # Never breaks even
    else:
        break_even = 0.0

    # LP vs hold comparison: positive means LP is better
    # Hold earns 0 from fees/emissions but avoids IL
    hold_return = 0.0  # holding earns nothing extra (unless staking)
    lp_return = net
    advantage = lp_return - hold_return

    return YieldReport(
        pool_name=params.name,
        fee_apr=f_apr,
        emission_apr_raw=emission_raw,
        emission_apr_adjusted=emission_adj,
        estimated_il=il_annual,
        gas_cost_pct=gas_pct,
        rebalance_cost_pct=rebalance_pct,
        net_apr=net,
        net_apy=net_apy,
        daily_income=daily,
        annual_income=annual,
        break_even_days=break_even,
        hold_vs_lp_advantage=advantage,
    )


# ── Sensitivity Analysis ───────────────────────────────────────────


def sensitivity_table(
    params: PoolParams,
    volatilities: Optional[list[float]] = None,
) -> list[tuple[float, float, float]]:
    """Compute net yield across different volatility scenarios.

    Args:
        params: Base pool parameters.
        volatilities: List of volatilities to test. Defaults to a range.

    Returns:
        List of (volatility, net_apr, estimated_il) tuples.
    """
    if volatilities is None:
        volatilities = [0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.2, 1.5, 2.0]

    results = []
    for vol in volatilities:
        p = PoolParams(
            name=params.name,
            tvl=params.tvl,
            daily_volume=params.daily_volume,
            fee_rate=params.fee_rate,
            annual_volatility=vol,
            emission_apr=params.emission_apr,
            emission_depreciation=params.emission_depreciation,
            position_size=params.position_size,
            gas_cost_annual=params.gas_cost_annual,
            rebalance_cost_annual=params.rebalance_cost_annual,
        )
        report = compute_yield(p)
        results.append((vol, report.net_apr, report.estimated_il))
    return results


# ── Display ─────────────────────────────────────────────────────────


def format_pct(value: float) -> str:
    """Format a decimal as a percentage string."""
    return f"{value * 100:+.2f}%" if value < 0 else f"{value * 100:.2f}%"


def print_report(report: YieldReport) -> None:
    """Print a formatted yield report to stdout.

    Args:
        report: Computed yield report.
    """
    print(f"\n{'═' * 60}")
    print(f"  YIELD REPORT: {report.pool_name}")
    print(f"{'═' * 60}")
    print(f"  Fee APR:                    {format_pct(report.fee_apr)}")
    print(f"  Emission APR (raw):         {format_pct(report.emission_apr_raw)}")
    print(f"  Emission APR (adjusted):    {format_pct(report.emission_apr_adjusted)}")
    print(f"  Estimated IL:               {format_pct(report.estimated_il)}")
    print(f"  Gas cost:                   {format_pct(report.gas_cost_pct)}")
    print(f"  Rebalance cost:             {format_pct(report.rebalance_cost_pct)}")
    print(f"{'─' * 60}")
    print(f"  Net APR:                    {format_pct(report.net_apr)}")
    print(f"  Net APY (daily compound):   {format_pct(report.net_apy)}")
    print(f"  Daily income:               ${report.daily_income:,.2f}")
    print(f"  Annual income:              ${report.annual_income:,.2f}")
    if report.break_even_days is not None:
        print(f"  Break-even:                 {report.break_even_days:.1f} days")
    else:
        print(f"  Break-even:                 Never (costs exceed income)")
    print(f"  LP vs Hold advantage:       {format_pct(report.hold_vs_lp_advantage)}")
    print(f"{'═' * 60}\n")


def print_sensitivity(params: PoolParams) -> None:
    """Print sensitivity analysis table.

    Args:
        params: Base pool parameters for sensitivity sweep.
    """
    results = sensitivity_table(params)
    print(f"\n{'─' * 50}")
    print(f"  SENSITIVITY: {params.name}")
    print(f"  Net yield vs. annual volatility")
    print(f"{'─' * 50}")
    print(f"  {'Volatility':>12}  {'Est. IL':>10}  {'Net APR':>10}")
    print(f"  {'─' * 12}  {'─' * 10}  {'─' * 10}")
    for vol, net, il in results:
        net_str = format_pct(net)
        print(f"  {format_pct(vol):>12}  {format_pct(il):>10}  {net_str:>10}")
    print(f"{'─' * 50}\n")


def print_comparison(reports: list[YieldReport]) -> None:
    """Print a side-by-side comparison table.

    Args:
        reports: List of yield reports to compare.
    """
    print(f"\n{'═' * 72}")
    print(f"  YIELD COMPARISON")
    print(f"{'═' * 72}")
    header = f"  {'Pool':<22} {'Fee APR':>9} {'IL':>9} {'Net APR':>9} {'Net APY':>9}"
    print(header)
    print(f"  {'─' * 22} {'─' * 9} {'─' * 9} {'─' * 9} {'─' * 9}")
    for r in sorted(reports, key=lambda x: x.net_apr, reverse=True):
        print(
            f"  {r.pool_name:<22} "
            f"{format_pct(r.fee_apr):>9} "
            f"{format_pct(r.estimated_il):>9} "
            f"{format_pct(r.net_apr):>9} "
            f"{format_pct(r.net_apy):>9}"
        )
    print(f"{'═' * 72}\n")


# ── Demo Scenarios ──────────────────────────────────────────────────


def demo_scenarios() -> list[PoolParams]:
    """Return three representative pool scenarios for demo mode.

    Returns:
        List of PoolParams for stablecoin, correlated, and volatile pools.
    """
    return [
        PoolParams(
            name="USDC-USDT (Stable)",
            tvl=50_000_000,
            daily_volume=15_000_000,
            fee_rate=0.0001,  # 1 bps
            annual_volatility=0.02,
            emission_apr=0.02,
            emission_depreciation=0.1,
            position_size=10_000,
            gas_cost_annual=10,
            rebalance_cost_annual=0,
        ),
        PoolParams(
            name="SOL-mSOL (Correlated)",
            tvl=20_000_000,
            daily_volume=5_000_000,
            fee_rate=0.0004,  # 4 bps
            annual_volatility=0.10,
            emission_apr=0.05,
            emission_depreciation=0.20,
            position_size=10_000,
            gas_cost_annual=20,
            rebalance_cost_annual=15,
        ),
        PoolParams(
            name="SOL-USDC (Volatile)",
            tvl=12_000_000,
            daily_volume=3_000_000,
            fee_rate=0.0025,  # 25 bps
            annual_volatility=0.80,
            emission_apr=0.15,
            emission_depreciation=0.35,
            position_size=10_000,
            gas_cost_annual=30,
            rebalance_cost_annual=50,
        ),
    ]


# ── CLI ─────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="DeFi yield calculator — compute real yield from pool parameters"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo comparing stablecoin, correlated, and volatile pool scenarios",
    )
    parser.add_argument("--tvl", type=float, default=10_000_000, help="Pool TVL in USD")
    parser.add_argument("--volume", type=float, default=2_000_000, help="Daily volume in USD")
    parser.add_argument("--fee-rate", type=float, default=0.0025, help="Fee rate (e.g. 0.0025)")
    parser.add_argument("--volatility", type=float, default=0.80, help="Annual volatility (e.g. 0.80)")
    parser.add_argument("--emission-apr", type=float, default=0.10, help="Emission APR (e.g. 0.10)")
    parser.add_argument("--emission-depreciation", type=float, default=0.30, help="Emission token depreciation (0-1)")
    parser.add_argument("--position", type=float, default=10_000, help="Your position size in USD")
    parser.add_argument("--name", type=str, default="Custom Pool", help="Pool name for display")
    return parser


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for yield calculator."""
    parser = build_parser()
    args = parser.parse_args()

    if args.demo:
        print("\n  DeFi Yield Calculator — Demo Mode")
        print("  Comparing three representative Solana pool scenarios\n")

        scenarios = demo_scenarios()
        reports = []

        for params in scenarios:
            report = compute_yield(params)
            reports.append(report)
            print_report(report)

        print_comparison(reports)

        # Sensitivity for the volatile pool
        print_sensitivity(scenarios[2])
    else:
        params = PoolParams(
            name=args.name,
            tvl=args.tvl,
            daily_volume=args.volume,
            fee_rate=args.fee_rate,
            annual_volatility=args.volatility,
            emission_apr=args.emission_apr,
            emission_depreciation=args.emission_depreciation,
            position_size=args.position,
            gas_cost_annual=30,
            rebalance_cost_annual=0,
        )

        report = compute_yield(params)
        print_report(report)
        print_sensitivity(params)


if __name__ == "__main__":
    main()
