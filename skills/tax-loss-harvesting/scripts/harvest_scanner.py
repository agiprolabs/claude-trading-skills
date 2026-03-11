#!/usr/bin/env python3
"""Tax-loss harvesting opportunity scanner.

Scans a portfolio for unrealized losses, scores each harvesting opportunity
on four dimensions (magnitude, urgency, wash safety, offset match), generates
a prioritized harvesting plan, and computes the net benefit of each harvest.

Usage:
    python scripts/harvest_scanner.py --demo

Dependencies:
    None (standard library only)

Environment Variables:
    None required (demo mode uses synthetic data)
"""

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Optional


# ── Configuration ───────────────────────────────────────────────────

DEFAULT_MARGINAL_TAX_RATE_ST = 0.37   # Federal short-term (ordinary income)
DEFAULT_MARGINAL_TAX_RATE_LT = 0.20   # Federal long-term capital gains
DEFAULT_ANNUAL_DEDUCTION_LIMIT = 3_000.0
DEFAULT_TRANSACTION_COST_BPS = 50      # 0.50% round-trip (swap + slippage)
LONG_TERM_THRESHOLD_DAYS = 365
WASH_SALE_WINDOW_DAYS = 30
REFERENCE_LOSS_AMOUNT = 10_000.0       # For magnitude normalization

SCORE_WEIGHTS = {
    "magnitude": 0.35,
    "urgency": 0.25,
    "wash_safety": 0.20,
    "offset_match": 0.20,
}


# ── Data Models ─────────────────────────────────────────────────────

@dataclass
class Lot:
    """A single tax lot within a portfolio position."""

    symbol: str
    quantity: float
    cost_basis_per_unit: float
    acquisition_date: date
    current_price: float
    wash_sale_risk: float = 0.0  # 0.0 = safe, 1.0 = same-token re-entry planned

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.cost_basis_per_unit

    @property
    def current_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.current_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return self.unrealized_pnl / self.cost_basis

    @property
    def days_held(self) -> int:
        return (date.today() - self.acquisition_date).days

    @property
    def is_long_term(self) -> bool:
        return self.days_held >= LONG_TERM_THRESHOLD_DAYS

    @property
    def days_to_long_term(self) -> int:
        return max(0, LONG_TERM_THRESHOLD_DAYS - self.days_held)

    @property
    def has_loss(self) -> bool:
        return self.unrealized_pnl < 0


@dataclass
class HarvestOpportunity:
    """A scored tax-loss harvesting opportunity."""

    lot: Lot
    magnitude_score: float = 0.0
    urgency_score: float = 0.0
    wash_safety_score: float = 0.0
    offset_match_score: float = 0.0
    composite_score: float = 0.0
    tax_savings: float = 0.0
    transaction_cost: float = 0.0
    re_entry_cost: float = 0.0
    net_benefit: float = 0.0
    re_entry_eligible_date: Optional[date] = None


@dataclass
class TaxSummary:
    """Annual tax gain/loss summary with carryforward."""

    realized_gains_st: float = 0.0
    realized_gains_lt: float = 0.0
    realized_losses_st: float = 0.0
    realized_losses_lt: float = 0.0
    prior_carryforward: float = 0.0
    annual_deduction_limit: float = DEFAULT_ANNUAL_DEDUCTION_LIMIT

    @property
    def net_st(self) -> float:
        return self.realized_gains_st + self.realized_losses_st

    @property
    def net_lt(self) -> float:
        return self.realized_gains_lt + self.realized_losses_lt

    @property
    def total_net(self) -> float:
        return self.net_st + self.net_lt - self.prior_carryforward

    @property
    def available_st_gains(self) -> float:
        return max(0.0, self.realized_gains_st + self.realized_losses_st)

    @property
    def available_lt_gains(self) -> float:
        return max(0.0, self.realized_gains_lt + self.realized_losses_lt)

    def compute_carryforward(self) -> dict:
        """Compute deduction used and carryforward for the year."""
        if self.total_net >= 0:
            return {
                "net_st": self.net_st,
                "net_lt": self.net_lt,
                "total_net": self.total_net,
                "deduction_used": 0.0,
                "carryforward": 0.0,
            }
        excess_loss = abs(self.total_net)
        deduction_used = min(excess_loss, self.annual_deduction_limit)
        carryforward = max(0.0, excess_loss - self.annual_deduction_limit)
        return {
            "net_st": self.net_st,
            "net_lt": self.net_lt,
            "total_net": self.total_net,
            "deduction_used": deduction_used,
            "carryforward": carryforward,
        }


# ── Scoring Engine ──────────────────────────────────────────────────

def compute_magnitude_score(
    unrealized_loss: float,
    reference_amount: float = REFERENCE_LOSS_AMOUNT,
) -> float:
    """Normalize loss magnitude to [0, 1]."""
    return min(abs(unrealized_loss) / reference_amount, 1.0)


def compute_urgency_score(days_to_long_term: int) -> float:
    """Score urgency of harvesting before long-term threshold.

    Higher score = closer to crossing into long-term territory,
    meaning a short-term loss is about to become a long-term loss.
    """
    if days_to_long_term <= 0:
        return 0.0  # Already long-term, no urgency for ST harvesting
    return max(0.0, 1.0 - days_to_long_term / LONG_TERM_THRESHOLD_DAYS)


def compute_wash_safety_score(wash_sale_risk: float) -> float:
    """Invert wash sale risk to get a safety score."""
    return 1.0 - max(0.0, min(1.0, wash_sale_risk))


def compute_offset_match_score(
    unrealized_loss: float,
    available_matching_gains: float,
) -> float:
    """Score how well this loss matches available gains."""
    if abs(unrealized_loss) < 0.01:
        return 0.0
    return min(1.0, available_matching_gains / abs(unrealized_loss))


def score_opportunity(
    lot: Lot,
    tax_summary: TaxSummary,
    marginal_rate_st: float = DEFAULT_MARGINAL_TAX_RATE_ST,
    marginal_rate_lt: float = DEFAULT_MARGINAL_TAX_RATE_LT,
    transaction_cost_bps: int = DEFAULT_TRANSACTION_COST_BPS,
    weights: Optional[dict] = None,
) -> HarvestOpportunity:
    """Score a single lot as a TLH opportunity.

    Args:
        lot: The tax lot to evaluate.
        tax_summary: Year-to-date tax gain/loss summary.
        marginal_rate_st: Marginal tax rate for short-term gains.
        marginal_rate_lt: Marginal tax rate for long-term gains.
        transaction_cost_bps: Round-trip transaction cost in basis points.
        weights: Custom scoring weights (defaults to SCORE_WEIGHTS).

    Returns:
        A fully scored HarvestOpportunity.
    """
    if not lot.has_loss:
        return HarvestOpportunity(lot=lot)

    w = weights or SCORE_WEIGHTS
    loss = lot.unrealized_pnl  # negative

    # Determine applicable tax rate and matching gains
    if lot.is_long_term:
        marginal_rate = marginal_rate_lt
        available_gains = tax_summary.available_lt_gains
    else:
        marginal_rate = marginal_rate_st
        available_gains = tax_summary.available_st_gains

    # Component scores
    mag = compute_magnitude_score(loss)
    urg = compute_urgency_score(lot.days_to_long_term)
    wash = compute_wash_safety_score(lot.wash_sale_risk)
    offset = compute_offset_match_score(loss, available_gains)

    composite = (
        w["magnitude"] * mag
        + w["urgency"] * urg
        + w["wash_safety"] * wash
        + w["offset_match"] * offset
    )

    # Net benefit
    tax_savings = abs(loss) * marginal_rate
    txn_cost = lot.current_value * (transaction_cost_bps / 10_000)
    re_cost = txn_cost  # Assume similar cost to re-enter
    benefit = tax_savings - txn_cost - re_cost

    re_entry_date = date.today() + timedelta(days=WASH_SALE_WINDOW_DAYS + 1)

    return HarvestOpportunity(
        lot=lot,
        magnitude_score=mag,
        urgency_score=urg,
        wash_safety_score=wash,
        offset_match_score=offset,
        composite_score=composite,
        tax_savings=tax_savings,
        transaction_cost=txn_cost,
        re_entry_cost=re_cost,
        net_benefit=benefit,
        re_entry_eligible_date=re_entry_date,
    )


# ── Portfolio Scanner ───────────────────────────────────────────────

def scan_portfolio(
    lots: list[Lot],
    tax_summary: TaxSummary,
    min_loss_threshold: float = 50.0,
    min_net_benefit: float = 0.0,
    **kwargs,
) -> list[HarvestOpportunity]:
    """Scan all lots and return scored harvesting opportunities.

    Args:
        lots: All tax lots in the portfolio.
        tax_summary: Year-to-date realized gain/loss summary.
        min_loss_threshold: Minimum dollar loss to consider.
        min_net_benefit: Minimum net benefit to include in results.
        **kwargs: Passed to score_opportunity.

    Returns:
        List of opportunities sorted by composite score (descending).
    """
    opportunities: list[HarvestOpportunity] = []
    for lot in lots:
        if not lot.has_loss:
            continue
        if abs(lot.unrealized_pnl) < min_loss_threshold:
            continue
        opp = score_opportunity(lot, tax_summary, **kwargs)
        if opp.net_benefit >= min_net_benefit:
            opportunities.append(opp)

    opportunities.sort(key=lambda o: o.composite_score, reverse=True)
    return opportunities


# ── Plan Generator ──────────────────────────────────────────────────

def generate_harvest_plan(
    opportunities: list[HarvestOpportunity],
    tax_summary: TaxSummary,
    max_harvests: int = 10,
) -> dict:
    """Generate a harvesting plan from scored opportunities.

    Args:
        opportunities: Scored and sorted opportunities.
        tax_summary: Current year tax summary.
        max_harvests: Maximum number of positions to harvest.

    Returns:
        Plan dict with actions, summary, and carryforward projection.
    """
    actions = []
    total_loss_harvested = 0.0
    total_tax_savings = 0.0
    total_costs = 0.0

    for opp in opportunities[:max_harvests]:
        loss_amount = abs(opp.lot.unrealized_pnl)
        action = {
            "rank": len(actions) + 1,
            "symbol": opp.lot.symbol,
            "action": "SELL",
            "quantity": opp.lot.quantity,
            "current_price": opp.lot.current_price,
            "cost_basis_per_unit": opp.lot.cost_basis_per_unit,
            "loss_amount": round(loss_amount, 2),
            "loss_pct": round(opp.lot.unrealized_pnl_pct * 100, 1),
            "holding_period": "long-term" if opp.lot.is_long_term else "short-term",
            "days_held": opp.lot.days_held,
            "composite_score": round(opp.composite_score, 4),
            "tax_savings": round(opp.tax_savings, 2),
            "transaction_cost": round(opp.transaction_cost, 2),
            "net_benefit": round(opp.net_benefit, 2),
            "wash_sale_risk": opp.lot.wash_sale_risk,
            "re_entry_eligible": str(opp.re_entry_eligible_date),
        }
        actions.append(action)
        total_loss_harvested += loss_amount
        total_tax_savings += opp.tax_savings
        total_costs += opp.transaction_cost + opp.re_entry_cost

    # Project carryforward after harvesting
    projected_losses_st = tax_summary.realized_losses_st
    projected_losses_lt = tax_summary.realized_losses_lt
    for opp in opportunities[:max_harvests]:
        if opp.lot.is_long_term:
            projected_losses_lt += opp.lot.unrealized_pnl
        else:
            projected_losses_st += opp.lot.unrealized_pnl

    projected_summary = TaxSummary(
        realized_gains_st=tax_summary.realized_gains_st,
        realized_gains_lt=tax_summary.realized_gains_lt,
        realized_losses_st=projected_losses_st,
        realized_losses_lt=projected_losses_lt,
        prior_carryforward=tax_summary.prior_carryforward,
    )
    carryforward = projected_summary.compute_carryforward()

    plan = {
        "plan_date": str(date.today()),
        "actions": actions,
        "summary": {
            "positions_to_harvest": len(actions),
            "total_loss_harvested": round(total_loss_harvested, 2),
            "total_tax_savings": round(total_tax_savings, 2),
            "total_transaction_costs": round(total_costs, 2),
            "total_net_benefit": round(total_tax_savings - total_costs, 2),
        },
        "projected_tax_position": {
            "net_short_term": round(carryforward["net_st"], 2),
            "net_long_term": round(carryforward["net_lt"], 2),
            "total_net": round(carryforward["total_net"], 2),
            "deduction_used": round(carryforward["deduction_used"], 2),
            "carryforward_to_next_year": round(carryforward["carryforward"], 2),
        },
    }
    return plan


# ── Demo Data ───────────────────────────────────────────────────────

def build_demo_portfolio() -> list[Lot]:
    """Build a synthetic portfolio with a mix of gains and losses."""
    today = date.today()
    return [
        Lot(
            symbol="SOL",
            quantity=100.0,
            cost_basis_per_unit=180.00,
            acquisition_date=today - timedelta(days=200),
            current_price=135.00,
            wash_sale_risk=0.3,
        ),
        Lot(
            symbol="BONK",
            quantity=50_000_000.0,
            cost_basis_per_unit=0.000035,
            acquisition_date=today - timedelta(days=90),
            current_price=0.000018,
            wash_sale_risk=0.0,
        ),
        Lot(
            symbol="JTO",
            quantity=2_000.0,
            cost_basis_per_unit=4.50,
            acquisition_date=today - timedelta(days=350),
            current_price=2.80,
            wash_sale_risk=0.1,
        ),
        Lot(
            symbol="WIF",
            quantity=5_000.0,
            cost_basis_per_unit=2.20,
            acquisition_date=today - timedelta(days=45),
            current_price=1.10,
            wash_sale_risk=0.8,
        ),
        Lot(
            symbol="PYTH",
            quantity=10_000.0,
            cost_basis_per_unit=0.50,
            acquisition_date=today - timedelta(days=400),
            current_price=0.35,
            wash_sale_risk=0.0,
        ),
        # Positions with GAINS (should be excluded from harvest scan)
        Lot(
            symbol="JUP",
            quantity=3_000.0,
            cost_basis_per_unit=0.60,
            acquisition_date=today - timedelta(days=180),
            current_price=1.25,
            wash_sale_risk=0.0,
        ),
        Lot(
            symbol="RAY",
            quantity=500.0,
            cost_basis_per_unit=1.80,
            acquisition_date=today - timedelta(days=120),
            current_price=5.50,
            wash_sale_risk=0.0,
        ),
    ]


def build_demo_tax_summary() -> TaxSummary:
    """Build a year-to-date tax summary with some realized gains."""
    return TaxSummary(
        realized_gains_st=4_500.0,
        realized_gains_lt=2_200.0,
        realized_losses_st=-800.0,
        realized_losses_lt=-300.0,
        prior_carryforward=1_500.0,
    )


# ── Display ─────────────────────────────────────────────────────────

def print_portfolio_summary(lots: list[Lot]) -> None:
    """Print a table of all portfolio positions."""
    print("\n" + "=" * 90)
    print("PORTFOLIO POSITIONS")
    print("=" * 90)
    header = f"{'Symbol':<8} {'Qty':>14} {'Basis':>10} {'Price':>10} {'Value':>12} {'P&L':>10} {'P&L%':>7} {'Days':>5}"
    print(header)
    print("-" * 90)

    total_value = 0.0
    total_pnl = 0.0
    for lot in lots:
        pnl_str = f"${lot.unrealized_pnl:,.2f}"
        pct_str = f"{lot.unrealized_pnl_pct * 100:.1f}%"
        print(
            f"{lot.symbol:<8} "
            f"{lot.quantity:>14,.2f} "
            f"${lot.cost_basis_per_unit:>9.4f} "
            f"${lot.current_price:>9.4f} "
            f"${lot.current_value:>11,.2f} "
            f"{pnl_str:>10} "
            f"{pct_str:>7} "
            f"{lot.days_held:>5}"
        )
        total_value += lot.current_value
        total_pnl += lot.unrealized_pnl

    print("-" * 90)
    print(f"{'TOTAL':<8} {'':>14} {'':>10} {'':>10} ${total_value:>11,.2f} ${total_pnl:>9,.2f}")
    print()


def print_tax_summary(summary: TaxSummary) -> None:
    """Print the year-to-date tax summary."""
    print("=" * 60)
    print("YEAR-TO-DATE TAX SUMMARY")
    print("=" * 60)
    cf = summary.compute_carryforward()
    print(f"  Realized ST gains:        ${summary.realized_gains_st:>10,.2f}")
    print(f"  Realized ST losses:       ${summary.realized_losses_st:>10,.2f}")
    print(f"  Net short-term:           ${cf['net_st']:>10,.2f}")
    print()
    print(f"  Realized LT gains:        ${summary.realized_gains_lt:>10,.2f}")
    print(f"  Realized LT losses:       ${summary.realized_losses_lt:>10,.2f}")
    print(f"  Net long-term:            ${cf['net_lt']:>10,.2f}")
    print()
    print(f"  Prior-year carryforward:  ${summary.prior_carryforward:>10,.2f}")
    print(f"  Total net:                ${cf['total_net']:>10,.2f}")
    print(f"  Deduction used:           ${cf['deduction_used']:>10,.2f}")
    print(f"  Carryforward:             ${cf['carryforward']:>10,.2f}")
    print()


def print_opportunities(opportunities: list[HarvestOpportunity]) -> None:
    """Print scored harvesting opportunities."""
    print("=" * 100)
    print("TAX-LOSS HARVESTING OPPORTUNITIES (ranked by composite score)")
    print("=" * 100)
    header = (
        f"{'#':>2} {'Symbol':<8} {'Loss':>10} {'Loss%':>7} "
        f"{'Mag':>5} {'Urg':>5} {'Wash':>5} {'Off':>5} {'Score':>6} "
        f"{'Savings':>9} {'Costs':>8} {'Net':>9} {'Period':<6}"
    )
    print(header)
    print("-" * 100)

    for i, opp in enumerate(opportunities, 1):
        loss = opp.lot.unrealized_pnl
        period = "LT" if opp.lot.is_long_term else "ST"
        print(
            f"{i:>2} {opp.lot.symbol:<8} "
            f"${loss:>9,.2f} "
            f"{opp.lot.unrealized_pnl_pct * 100:>6.1f}% "
            f"{opp.magnitude_score:>5.3f} "
            f"{opp.urgency_score:>5.3f} "
            f"{opp.wash_safety_score:>5.3f} "
            f"{opp.offset_match_score:>5.3f} "
            f"{opp.composite_score:>6.4f} "
            f"${opp.tax_savings:>8,.2f} "
            f"${opp.transaction_cost + opp.re_entry_cost:>7,.2f} "
            f"${opp.net_benefit:>8,.2f} "
            f"{period:<6}"
        )
    print()


def print_plan(plan: dict) -> None:
    """Print the harvesting plan."""
    print("=" * 80)
    print("HARVESTING PLAN")
    print("=" * 80)

    for action in plan["actions"]:
        print(f"\n  #{action['rank']} {action['action']} {action['symbol']}")
        print(f"     Quantity:          {action['quantity']:,.2f}")
        print(f"     Loss:              ${action['loss_amount']:,.2f} ({action['loss_pct']}%)")
        print(f"     Holding period:    {action['holding_period']} ({action['days_held']} days)")
        print(f"     Score:             {action['composite_score']:.4f}")
        print(f"     Tax savings:       ${action['tax_savings']:,.2f}")
        print(f"     Transaction cost:  ${action['transaction_cost']:,.2f}")
        print(f"     Net benefit:       ${action['net_benefit']:,.2f}")
        wash_label = "LOW" if action["wash_sale_risk"] < 0.3 else ("MED" if action["wash_sale_risk"] < 0.7 else "HIGH")
        print(f"     Wash sale risk:    {wash_label} ({action['wash_sale_risk']:.1f})")
        print(f"     Re-entry eligible: {action['re_entry_eligible']}")

    s = plan["summary"]
    print(f"\n  {'─' * 50}")
    print(f"  Positions to harvest:     {s['positions_to_harvest']}")
    print(f"  Total loss harvested:     ${s['total_loss_harvested']:,.2f}")
    print(f"  Total tax savings:        ${s['total_tax_savings']:,.2f}")
    print(f"  Total transaction costs:  ${s['total_transaction_costs']:,.2f}")
    print(f"  TOTAL NET BENEFIT:        ${s['total_net_benefit']:,.2f}")

    p = plan["projected_tax_position"]
    print(f"\n  PROJECTED TAX POSITION (after harvesting):")
    print(f"    Net short-term:         ${p['net_short_term']:,.2f}")
    print(f"    Net long-term:          ${p['net_long_term']:,.2f}")
    print(f"    Total net:              ${p['total_net']:,.2f}")
    print(f"    Deduction used:         ${p['deduction_used']:,.2f}")
    print(f"    Carryforward:           ${p['carryforward_to_next_year']:,.2f}")
    print()


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tax-loss harvesting opportunity scanner"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with synthetic demo portfolio",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output plan as JSON instead of formatted text",
    )
    parser.add_argument(
        "--min-loss",
        type=float,
        default=50.0,
        help="Minimum dollar loss to consider (default: 50)",
    )
    parser.add_argument(
        "--tax-rate-st",
        type=float,
        default=DEFAULT_MARGINAL_TAX_RATE_ST,
        help=f"Short-term marginal tax rate (default: {DEFAULT_MARGINAL_TAX_RATE_ST})",
    )
    parser.add_argument(
        "--tax-rate-lt",
        type=float,
        default=DEFAULT_MARGINAL_TAX_RATE_LT,
        help=f"Long-term marginal tax rate (default: {DEFAULT_MARGINAL_TAX_RATE_LT})",
    )
    args = parser.parse_args()

    if not args.demo:
        print("Currently only --demo mode is supported.")
        print("Usage: python scripts/harvest_scanner.py --demo")
        sys.exit(1)

    # Build demo data
    lots = build_demo_portfolio()
    tax_summary = build_demo_tax_summary()

    # Scan for opportunities
    opportunities = scan_portfolio(
        lots=lots,
        tax_summary=tax_summary,
        min_loss_threshold=args.min_loss,
        marginal_rate_st=args.tax_rate_st,
        marginal_rate_lt=args.tax_rate_lt,
    )

    # Generate plan
    plan = generate_harvest_plan(opportunities, tax_summary)

    if args.json:
        print(json.dumps(plan, indent=2))
        return

    # Display results
    print_portfolio_summary(lots)
    print_tax_summary(tax_summary)
    print_opportunities(opportunities)
    print_plan(plan)

    print("=" * 80)
    print("DISCLAIMER: This analysis is for informational purposes only.")
    print("It is NOT tax advice. Consult a qualified tax professional")
    print("before making any tax-related trading decisions.")
    print("=" * 80)


if __name__ == "__main__":
    main()
