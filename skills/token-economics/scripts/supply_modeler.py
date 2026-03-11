#!/usr/bin/env python3
"""Supply Modeler — Project token supply dynamics over 12 months.

Takes supply parameters (total supply, circulating, emissions, burns, vesting)
and projects monthly supply changes, inflation rates, and FDV/MCap evolution.
Includes scenario analysis with and without burn mechanisms.

Usage:
    python scripts/supply_modeler.py               # runs demo scenario
    python scripts/supply_modeler.py --interactive  # prompts for parameters

Dependencies:
    None (pure math, no external packages)

Environment Variables:
    None required
"""

import argparse
import sys
from typing import Optional


# ── Data Models ─────────────────────────────────────────────────────
class SupplyParams:
    """Parameters for supply projection model."""

    def __init__(
        self,
        name: str,
        total_supply: float,
        circulating_supply: float,
        token_price: float,
        monthly_emissions: float,
        monthly_burns: float,
        vesting_schedule: Optional[list[float]] = None,
        label: str = "Base Case",
    ) -> None:
        """Initialize supply parameters.

        Args:
            name: Token name or identifier.
            total_supply: Maximum total supply of the token.
            circulating_supply: Current circulating supply.
            token_price: Current token price in USD.
            monthly_emissions: New tokens emitted per month (staking, LM).
            monthly_burns: Tokens burned per month.
            vesting_schedule: List of 12 monthly vesting unlock amounts.
                              If None, assumes zero vesting.
            label: Scenario label for display.
        """
        self.name = name
        self.total_supply = total_supply
        self.circulating_supply = circulating_supply
        self.token_price = token_price
        self.monthly_emissions = monthly_emissions
        self.monthly_burns = monthly_burns
        self.vesting_schedule = vesting_schedule or [0.0] * 12
        self.label = label

        # Pad vesting schedule to 12 months if shorter
        while len(self.vesting_schedule) < 12:
            self.vesting_schedule.append(0.0)


class MonthlyProjection:
    """Single month supply projection result."""

    def __init__(
        self,
        month: int,
        circulating: float,
        total_supply: float,
        emissions: float,
        vesting_unlock: float,
        burns: float,
        net_new: float,
        token_price: float,
    ) -> None:
        self.month = month
        self.circulating = circulating
        self.total_supply = total_supply
        self.emissions = emissions
        self.vesting_unlock = vesting_unlock
        self.burns = burns
        self.net_new = net_new
        self.token_price = token_price

    @property
    def circulating_pct(self) -> float:
        """Percentage of total supply in circulation."""
        return (self.circulating / self.total_supply * 100) if self.total_supply > 0 else 0

    @property
    def monthly_inflation_pct(self) -> float:
        """Monthly inflation rate as percentage."""
        prev = self.circulating - self.net_new
        return (self.net_new / prev * 100) if prev > 0 else 0

    @property
    def market_cap(self) -> float:
        """Estimated market cap."""
        return self.circulating * self.token_price

    @property
    def fdv(self) -> float:
        """Fully diluted valuation."""
        return self.total_supply * self.token_price

    @property
    def fdv_mcap_ratio(self) -> float:
        """FDV to market cap ratio."""
        return self.fdv / self.market_cap if self.market_cap > 0 else 0


# ── Projection Engine ──────────────────────────────────────────────
def project_supply(params: SupplyParams, months: int = 12) -> list[MonthlyProjection]:
    """Project token supply over specified months.

    Args:
        params: Supply parameters for the projection.
        months: Number of months to project (default 12).

    Returns:
        List of MonthlyProjection objects for each month.
    """
    projections: list[MonthlyProjection] = []
    circ = params.circulating_supply

    for m in range(months):
        vest = params.vesting_schedule[m] if m < len(params.vesting_schedule) else 0.0
        emissions = params.monthly_emissions
        burns = params.monthly_burns
        net_new = emissions + vest - burns

        # Cannot exceed total supply
        if circ + net_new > params.total_supply:
            net_new = params.total_supply - circ

        circ += net_new

        projections.append(
            MonthlyProjection(
                month=m + 1,
                circulating=circ,
                total_supply=params.total_supply,
                emissions=emissions,
                vesting_unlock=vest,
                burns=burns,
                net_new=net_new,
                token_price=params.token_price,
            )
        )

    return projections


def find_milestones(
    projections: list[MonthlyProjection],
    milestones: list[float] = [50.0, 75.0, 90.0, 100.0],
) -> list[dict]:
    """Find when circulating supply reaches key percentage milestones.

    Args:
        projections: List of monthly projections.
        milestones: Percentage milestones to track.

    Returns:
        List of milestone events with month and details.
    """
    results: list[dict] = []
    remaining = list(milestones)

    # Check starting point
    if projections:
        start_pct = (
            (projections[0].circulating - projections[0].net_new)
            / projections[0].total_supply
            * 100
        )
        # Remove milestones already passed
        remaining = [m for m in remaining if m > start_pct]

    for proj in projections:
        hit = [m for m in remaining if proj.circulating_pct >= m]
        for milestone in hit:
            results.append({
                "milestone_pct": milestone,
                "month": proj.month,
                "circulating": proj.circulating,
                "circulating_pct": proj.circulating_pct,
            })
            remaining.remove(milestone)

    # Report milestones not reached
    for m in remaining:
        results.append({
            "milestone_pct": m,
            "month": None,
            "circulating": None,
            "circulating_pct": None,
        })

    return results


def compare_scenarios(
    base: list[MonthlyProjection],
    alt: list[MonthlyProjection],
) -> list[dict]:
    """Compare two projection scenarios month by month.

    Args:
        base: Base case projections.
        alt: Alternative scenario projections.

    Returns:
        Monthly comparison with differences.
    """
    comparisons: list[dict] = []
    for b, a in zip(base, alt):
        comparisons.append({
            "month": b.month,
            "base_circulating_pct": round(b.circulating_pct, 2),
            "alt_circulating_pct": round(a.circulating_pct, 2),
            "diff_pct": round(a.circulating_pct - b.circulating_pct, 2),
            "base_inflation_pct": round(b.monthly_inflation_pct, 3),
            "alt_inflation_pct": round(a.monthly_inflation_pct, 3),
        })
    return comparisons


# ── Display ─────────────────────────────────────────────────────────
def format_num(n: float) -> str:
    """Format number with K/M/B suffix.

    Args:
        n: Number to format.

    Returns:
        Formatted string.
    """
    if abs(n) >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:.0f}"


def print_projection_table(
    params: SupplyParams,
    projections: list[MonthlyProjection],
) -> None:
    """Print formatted projection table.

    Args:
        params: Supply parameters used.
        projections: Projection results.
    """
    print(f"\n{'=' * 80}")
    print(f"  SUPPLY PROJECTION: {params.name} — {params.label}")
    print(f"{'=' * 80}")
    print(f"  Total Supply:      {format_num(params.total_supply)}")
    print(f"  Starting Circ:     {format_num(params.circulating_supply)}")
    start_pct = params.circulating_supply / params.total_supply * 100
    print(f"  Starting Circ %:   {start_pct:.1f}%")
    print(f"  Token Price:       ${params.token_price:,.4f}")
    print(f"  Monthly Emissions: {format_num(params.monthly_emissions)}")
    print(f"  Monthly Burns:     {format_num(params.monthly_burns)}")
    total_vest = sum(params.vesting_schedule[:12])
    if total_vest > 0:
        print(f"  Total Vesting (12mo): {format_num(total_vest)}")

    # Table header
    print(f"\n  {'Mo':>3} | {'Circulating':>12} | {'Circ %':>7} | {'Net New':>10} "
          f"| {'Mo.Infl%':>8} | {'FDV/MCap':>8} | {'Est MCap':>12}")
    print(f"  {'-' * 3}-+-{'-' * 12}-+-{'-' * 7}-+-{'-' * 10}-"
          f"+-{'-' * 8}-+-{'-' * 8}-+-{'-' * 12}")

    for p in projections:
        mcap_str = f"${p.market_cap / 1e9:.2f}B" if p.market_cap >= 1e9 else f"${p.market_cap / 1e6:.1f}M"
        print(
            f"  {p.month:>3} | {format_num(p.circulating):>12} | "
            f"{p.circulating_pct:>6.1f}% | {format_num(p.net_new):>10} | "
            f"{p.monthly_inflation_pct:>7.2f}% | {p.fdv_mcap_ratio:>7.2f}x | "
            f"{mcap_str:>12}"
        )

    # Summary
    first = projections[0]
    last = projections[-1]
    total_new = sum(p.net_new for p in projections)
    total_inflation = (total_new / params.circulating_supply) * 100

    print(f"\n  12-Month Summary:")
    print(f"    Net new tokens:      {format_num(total_new)}")
    print(f"    Cumulative inflation: {total_inflation:.1f}%")
    print(f"    Circ % change:       {start_pct:.1f}% -> {last.circulating_pct:.1f}%")
    print(f"    FDV/MCap change:     {params.total_supply / params.circulating_supply:.2f}x -> {last.fdv_mcap_ratio:.2f}x")


def print_milestones(milestones: list[dict]) -> None:
    """Print milestone achievement summary.

    Args:
        milestones: List of milestone results.
    """
    print(f"\n  Supply Milestones:")
    for m in milestones:
        if m["month"] is not None:
            print(f"    {m['milestone_pct']:.0f}% circulating: reached in month {m['month']}")
        else:
            print(f"    {m['milestone_pct']:.0f}% circulating: not reached within projection period")


def print_scenario_comparison(
    base_params: SupplyParams,
    alt_params: SupplyParams,
    comparisons: list[dict],
) -> None:
    """Print side-by-side scenario comparison.

    Args:
        base_params: Base scenario parameters.
        alt_params: Alternative scenario parameters.
        comparisons: Monthly comparison data.
    """
    print(f"\n{'=' * 70}")
    print(f"  SCENARIO COMPARISON: {base_params.label} vs {alt_params.label}")
    print(f"{'=' * 70}")
    print(f"  Base burns/mo:  {format_num(base_params.monthly_burns)}")
    print(f"  Alt burns/mo:   {format_num(alt_params.monthly_burns)}")

    print(f"\n  {'Mo':>3} | {'Base Circ%':>10} | {'Alt Circ%':>10} | {'Diff':>7} "
          f"| {'Base Infl%':>10} | {'Alt Infl%':>10}")
    print(f"  {'-' * 3}-+-{'-' * 10}-+-{'-' * 10}-+-{'-' * 7}-+-{'-' * 10}-+-{'-' * 10}")

    for c in comparisons:
        print(
            f"  {c['month']:>3} | {c['base_circulating_pct']:>9.1f}% | "
            f"{c['alt_circulating_pct']:>9.1f}% | {c['diff_pct']:>+6.1f}% | "
            f"{c['base_inflation_pct']:>9.2f}% | {c['alt_inflation_pct']:>9.2f}%"
        )

    # Final difference
    last = comparisons[-1]
    print(f"\n  After 12 months:")
    print(f"    Base scenario: {last['base_circulating_pct']:.1f}% circulating")
    print(f"    Alt scenario:  {last['alt_circulating_pct']:.1f}% circulating")
    print(f"    Difference:    {last['diff_pct']:+.1f} percentage points")


# ── Demo Scenarios ──────────────────────────────────────────────────
def get_demo_params() -> SupplyParams:
    """Create demo parameters resembling a typical DeFi protocol token.

    Returns:
        SupplyParams with realistic example values.
    """
    # Vesting schedule: team cliff at month 6, then linear
    vesting = [
        0, 0, 0, 0, 0,          # months 1-5: no vesting
        25_000_000,              # month 6: cliff unlock (25M)
        5_000_000,               # months 7-12: linear vesting
        5_000_000,
        5_000_000,
        5_000_000,
        5_000_000,
        5_000_000,
    ]

    return SupplyParams(
        name="ExampleProtocol (EXMP)",
        total_supply=1_000_000_000,       # 1B total
        circulating_supply=300_000_000,   # 300M circulating (30%)
        token_price=2.50,
        monthly_emissions=8_000_000,      # 8M/mo from staking + LM
        monthly_burns=2_000_000,          # 2M/mo from fee burns
        vesting_schedule=vesting,
        label="Base Case (with burns)",
    )


def get_demo_no_burns() -> SupplyParams:
    """Create demo params without burn mechanism for comparison.

    Returns:
        SupplyParams identical to demo but with zero burns.
    """
    params = get_demo_params()
    params.monthly_burns = 0
    params.label = "No Burns"
    return params


# ── Interactive Mode ────────────────────────────────────────────────
def get_interactive_params() -> SupplyParams:
    """Prompt user for supply parameters interactively.

    Returns:
        SupplyParams from user input.
    """
    print("\n  Enter token supply parameters:")
    print("  (Press Enter for defaults shown in brackets)\n")

    def prompt_float(label: str, default: float) -> float:
        val = input(f"  {label} [{default:,.0f}]: ").strip()
        if not val:
            return default
        try:
            return float(val.replace(",", "").replace("_", ""))
        except ValueError:
            print(f"  Invalid number, using default: {default:,.0f}")
            return default

    name = input("  Token name [MyToken]: ").strip() or "MyToken"
    total = prompt_float("Total supply", 1_000_000_000)
    circ = prompt_float("Circulating supply", total * 0.3)
    price = prompt_float("Token price (USD)", 1.0)
    emissions = prompt_float("Monthly emissions", total * 0.008)
    burns = prompt_float("Monthly burns", total * 0.002)

    vest_input = input("  Include vesting schedule? (y/n) [n]: ").strip().lower()
    vesting: list[float] = [0.0] * 12
    if vest_input == "y":
        cliff_month = int(input("  Cliff month (1-12) [6]: ").strip() or "6")
        cliff_amount = prompt_float("Cliff unlock amount", total * 0.05)
        monthly_vest = prompt_float("Monthly vesting after cliff", total * 0.005)
        for m in range(12):
            if m + 1 == cliff_month:
                vesting[m] = cliff_amount
            elif m + 1 > cliff_month:
                vesting[m] = monthly_vest

    return SupplyParams(
        name=name,
        total_supply=total,
        circulating_supply=circ,
        token_price=price,
        monthly_emissions=emissions,
        monthly_burns=burns,
        vesting_schedule=vesting,
        label="Custom Scenario",
    )


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Entry point for the supply modeler."""
    parser = argparse.ArgumentParser(
        description="Model token supply dynamics over 12 months"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=False,
        help="Run with demo parameters (default if no other option specified)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        default=False,
        help="Interactively input supply parameters",
    )
    parser.add_argument(
        "--no-compare",
        action="store_true",
        default=False,
        help="Skip burn vs no-burn comparison",
    )
    args = parser.parse_args()

    if args.interactive:
        params = get_interactive_params()
    else:
        if not args.demo:
            print("No parameters specified, running demo mode.")
            print("Use --interactive for custom parameters.\n")
        params = get_demo_params()

    # Run base projection
    projections = project_supply(params)
    print_projection_table(params, projections)

    # Milestones
    milestones = find_milestones(projections)
    print_milestones(milestones)

    # Scenario comparison (burn vs no-burn)
    if not args.no_compare:
        if args.interactive:
            no_burn = SupplyParams(
                name=params.name,
                total_supply=params.total_supply,
                circulating_supply=params.circulating_supply,
                token_price=params.token_price,
                monthly_emissions=params.monthly_emissions,
                monthly_burns=0,
                vesting_schedule=list(params.vesting_schedule),
                label="No Burns",
            )
        else:
            no_burn = get_demo_no_burns()

        alt_projections = project_supply(no_burn)
        comparisons = compare_scenarios(projections, alt_projections)
        print_scenario_comparison(params, no_burn, comparisons)

    print(f"\n{'=' * 70}")
    print("  NOTE: Projections assume constant price and emission rates.")
    print("  Actual supply dynamics depend on governance, market conditions,")
    print("  and protocol changes. This is informational, not financial advice.")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
