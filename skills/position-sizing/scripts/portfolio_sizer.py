#!/usr/bin/env python3
"""Portfolio-level position sizer and risk dashboard.

Analyzes a portfolio of positions, calculates per-position and total risk,
correlation-adjusted risk, and recommends sizing for the next trade.

Usage:
    python scripts/portfolio_sizer.py          # Uses demo portfolio
    python scripts/portfolio_sizer.py --demo   # Explicitly use demo data

Dependencies:
    None (pure math, no external packages required)

Environment Variables:
    ACCOUNT_SIZE: Total account value in USD (default: 15000, i.e. ~100 SOL)
"""

import math
import os
import sys
from typing import Optional


# ── Configuration ───────────────────────────────────────────────────

ACCOUNT_SIZE = float(os.getenv("ACCOUNT_SIZE", "15000"))

# Portfolio limits
MAX_SINGLE_POSITION_PCT = 0.10   # 10% max single position
MAX_CORRELATED_PCT = 0.25        # 25% max correlated exposure
MAX_TOTAL_EXPOSURE_PCT = 0.70    # 70% max total exposure
DEFAULT_RISK_PCT = 0.02          # 2% risk per trade
DEFAULT_CORRELATION = 0.50       # Assumed correlation within same sector


# ── Data Structures ─────────────────────────────────────────────────

class Position:
    """Represents a single portfolio position.

    Attributes:
        symbol: Token symbol.
        entry_price: Price at entry.
        current_price: Current market price.
        stop_loss: Stop loss price.
        units: Number of units held.
        sector: Sector/category for correlation grouping.
    """

    def __init__(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        stop_loss: float,
        units: float,
        sector: str = "general",
    ) -> None:
        self.symbol = symbol
        self.entry_price = entry_price
        self.current_price = current_price
        self.stop_loss = stop_loss
        self.units = units
        self.sector = sector

    @property
    def position_value(self) -> float:
        """Current position value."""
        return self.units * self.current_price

    @property
    def entry_value(self) -> float:
        """Position value at entry."""
        return self.units * self.entry_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss."""
        return self.units * (self.current_price - self.entry_price)

    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized P&L as percentage of entry value."""
        if self.entry_value == 0:
            return 0.0
        return (self.unrealized_pnl / self.entry_value) * 100

    @property
    def risk_per_unit(self) -> float:
        """Dollar risk per unit (distance to stop)."""
        return abs(self.current_price - self.stop_loss)

    @property
    def total_risk(self) -> float:
        """Total dollar risk if stop is hit."""
        return self.units * self.risk_per_unit

    @property
    def risk_reward_from_current(self) -> float:
        """Current risk as fraction of current value."""
        if self.position_value == 0:
            return 0.0
        return self.total_risk / self.position_value


# ── Demo Data ───────────────────────────────────────────────────────

def get_demo_positions() -> list:
    """Return a demo portfolio with 5 example positions.

    Returns:
        List of Position objects representing a sample portfolio.
    """
    return [
        Position(
            symbol="SOL",
            entry_price=145.00,
            current_price=150.00,
            stop_loss=135.00,
            units=20.0,
            sector="l1",
        ),
        Position(
            symbol="JUP",
            entry_price=0.72,
            current_price=0.80,
            stop_loss=0.60,
            units=5000.0,
            sector="defi",
        ),
        Position(
            symbol="BONK",
            entry_price=0.000018,
            current_price=0.000020,
            stop_loss=0.000012,
            units=50_000_000.0,
            sector="meme",
        ),
        Position(
            symbol="WIF",
            entry_price=1.80,
            current_price=1.65,
            stop_loss=1.40,
            units=500.0,
            sector="meme",
        ),
        Position(
            symbol="PYTH",
            entry_price=0.35,
            current_price=0.38,
            stop_loss=0.28,
            units=3000.0,
            sector="defi",
        ),
    ]


# ── Portfolio Analytics ─────────────────────────────────────────────

def calculate_portfolio_metrics(
    positions: list,
    account_size: float,
) -> dict:
    """Calculate portfolio-level risk metrics.

    Args:
        positions: List of Position objects.
        account_size: Total account value in USD.

    Returns:
        Dictionary containing portfolio metrics.
    """
    total_value = sum(p.position_value for p in positions)
    total_risk = sum(p.total_risk for p in positions)
    total_pnl = sum(p.unrealized_pnl for p in positions)
    cash = account_size - total_value

    # Exposure percentages
    exposure_pct = (total_value / account_size) * 100 if account_size > 0 else 0
    risk_pct = (total_risk / account_size) * 100 if account_size > 0 else 0
    cash_pct = (cash / account_size) * 100 if account_size > 0 else 0

    return {
        "total_value": total_value,
        "total_risk": total_risk,
        "total_pnl": total_pnl,
        "cash": cash,
        "exposure_pct": exposure_pct,
        "risk_pct": risk_pct,
        "cash_pct": cash_pct,
        "num_positions": len(positions),
    }


def calculate_sector_exposure(
    positions: list,
    account_size: float,
) -> dict:
    """Calculate exposure by sector for correlation analysis.

    Args:
        positions: List of Position objects.
        account_size: Total account value.

    Returns:
        Dictionary mapping sector to exposure metrics.
    """
    sectors: dict = {}
    for p in positions:
        if p.sector not in sectors:
            sectors[p.sector] = {
                "positions": [],
                "total_value": 0.0,
                "total_risk": 0.0,
            }
        sectors[p.sector]["positions"].append(p.symbol)
        sectors[p.sector]["total_value"] += p.position_value
        sectors[p.sector]["total_risk"] += p.total_risk

    for sector_data in sectors.values():
        sector_data["exposure_pct"] = (sector_data["total_value"] / account_size) * 100
        sector_data["risk_pct"] = (sector_data["total_risk"] / account_size) * 100

    return sectors


def calculate_correlation_adjusted_risk(
    positions: list,
    default_corr: float = DEFAULT_CORRELATION,
) -> float:
    """Calculate portfolio risk adjusted for assumed correlation.

    Uses a simplified model where positions in the same sector have
    a fixed correlation and positions in different sectors are uncorrelated.

    The correlation-adjusted portfolio variance is:
        Var(P) = sum(var_i) + 2 * sum_{i<j, same sector}(corr * std_i * std_j)

    Args:
        positions: List of Position objects.
        default_corr: Assumed correlation between same-sector positions.

    Returns:
        Correlation-adjusted total risk in USD.
    """
    if not positions:
        return 0.0

    # Group by sector
    sectors: dict = {}
    for p in positions:
        if p.sector not in sectors:
            sectors[p.sector] = []
        sectors[p.sector].append(p.total_risk)

    total_variance = 0.0

    for sector_risks in sectors.values():
        n = len(sector_risks)
        # Variance of each position's risk (treat risk as std dev proxy)
        for risk in sector_risks:
            total_variance += risk ** 2

        # Cross-terms for correlated positions
        for i in range(n):
            for j in range(i + 1, n):
                total_variance += 2 * default_corr * sector_risks[i] * sector_risks[j]

    return math.sqrt(total_variance)


def calculate_available_budget(
    account_size: float,
    positions: list,
    risk_pct_per_trade: float = DEFAULT_RISK_PCT,
) -> dict:
    """Calculate available risk budget for new positions.

    Args:
        account_size: Total account value.
        positions: Current positions.
        risk_pct_per_trade: Risk percentage for new trade.

    Returns:
        Dictionary with budget metrics and recommended size.
    """
    metrics = calculate_portfolio_metrics(positions, account_size)
    sectors = calculate_sector_exposure(positions, account_size)

    # Remaining exposure capacity
    max_exposure = account_size * MAX_TOTAL_EXPOSURE_PCT
    remaining_exposure = max(0, max_exposure - metrics["total_value"])

    # Max single position
    max_single = account_size * MAX_SINGLE_POSITION_PCT

    # Effective max for new position
    max_new_position = min(remaining_exposure, max_single)

    # Risk budget
    risk_for_new_trade = account_size * risk_pct_per_trade

    # Sector limits
    sector_room: dict = {}
    max_sector_value = account_size * MAX_CORRELATED_PCT
    for sector, data in sectors.items():
        room = max(0, max_sector_value - data["total_value"])
        sector_room[sector] = room

    return {
        "remaining_exposure": remaining_exposure,
        "max_single_position": max_single,
        "max_new_position": max_new_position,
        "risk_budget": risk_for_new_trade,
        "sector_room": sector_room,
        "can_add_position": remaining_exposure > 0,
    }


# ── Report Formatting ──────────────────────────────────────────────

def fmt(val: float, decimals: int = 2) -> str:
    """Format a number with commas."""
    return f"{val:,.{decimals}f}"


def print_header(title: str) -> None:
    """Print a section header."""
    width = 68
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def print_portfolio_report(
    positions: list,
    account_size: float,
) -> None:
    """Print the complete portfolio risk dashboard.

    Args:
        positions: List of Position objects.
        account_size: Total account value.
    """
    metrics = calculate_portfolio_metrics(positions, account_size)
    sectors = calculate_sector_exposure(positions, account_size)
    corr_risk = calculate_correlation_adjusted_risk(positions)
    budget = calculate_available_budget(account_size, positions)

    # ── Account Overview ────────────────────────────────────────
    print_header("PORTFOLIO RISK DASHBOARD")
    print(f"  Account Size:          ${fmt(account_size)}")
    print(f"  Total Invested:        ${fmt(metrics['total_value'])} ({metrics['exposure_pct']:.1f}%)")
    print(f"  Cash Available:        ${fmt(metrics['cash'])} ({metrics['cash_pct']:.1f}%)")
    print(f"  Unrealized P&L:        ${fmt(metrics['total_pnl'])} ({metrics['total_pnl'] / account_size * 100:+.2f}%)")
    print(f"  Active Positions:      {metrics['num_positions']}")

    # ── Per-Position Breakdown ──────────────────────────────────
    print_header("POSITION BREAKDOWN")
    header = f"  {'Symbol':<8} {'Value':>10} {'% Acct':>8} {'P&L':>10} {'P&L%':>8} {'Risk$':>10} {'Risk%':>8} {'Sector':<10}"
    print(header)
    print(f"  {'-' * 74}")

    for p in sorted(positions, key=lambda x: x.position_value, reverse=True):
        pct_acct = (p.position_value / account_size) * 100
        risk_pct_acct = (p.total_risk / account_size) * 100
        print(
            f"  {p.symbol:<8} "
            f"${fmt(p.position_value):>9} "
            f"{pct_acct:>7.1f}% "
            f"${fmt(p.unrealized_pnl):>9} "
            f"{p.unrealized_pnl_pct:>+7.1f}% "
            f"${fmt(p.total_risk):>9} "
            f"{risk_pct_acct:>7.1f}% "
            f"{p.sector:<10}"
        )

    print(f"  {'-' * 74}")
    total_risk_pct = (metrics['total_risk'] / account_size) * 100
    print(
        f"  {'TOTAL':<8} "
        f"${fmt(metrics['total_value']):>9} "
        f"{metrics['exposure_pct']:>7.1f}% "
        f"${fmt(metrics['total_pnl']):>9} "
        f"{'':>8} "
        f"${fmt(metrics['total_risk']):>9} "
        f"{total_risk_pct:>7.1f}% "
    )

    # ── Risk Analysis ───────────────────────────────────────────
    print_header("RISK ANALYSIS")
    print(f"  Simple Total Risk:          ${fmt(metrics['total_risk'])} ({total_risk_pct:.1f}% of account)")
    print(f"  Correlation-Adjusted Risk:  ${fmt(corr_risk)} ({corr_risk / account_size * 100:.1f}% of account)")
    print(f"  Diversification Benefit:    ${fmt(metrics['total_risk'] - corr_risk)} saved by diversification")

    if metrics["total_risk"] > 0:
        div_ratio = corr_risk / metrics["total_risk"]
        print(f"  Diversification Ratio:      {div_ratio:.2f} (1.0 = no benefit, lower = better)")

    # ── Sector Exposure ─────────────────────────────────────────
    print_header("SECTOR EXPOSURE")
    print(f"  {'Sector':<12} {'Positions':<20} {'Value':>10} {'% Acct':>8} {'Risk$':>10} {'Limit':>10}")
    print(f"  {'-' * 70}")

    max_sector = account_size * MAX_CORRELATED_PCT
    for sector, data in sorted(sectors.items(), key=lambda x: x[1]["total_value"], reverse=True):
        pos_str = ", ".join(data["positions"])
        over = " OVER" if data["total_value"] > max_sector else ""
        print(
            f"  {sector:<12} "
            f"{pos_str:<20} "
            f"${fmt(data['total_value']):>9} "
            f"{data['exposure_pct']:>7.1f}% "
            f"${fmt(data['total_risk']):>9} "
            f"${fmt(max_sector):>9}{over}"
        )

    # ── Portfolio Limit Checks ──────────────────────────────────
    print_header("LIMIT CHECKS")

    checks = [
        (
            "Total exposure < 70%",
            metrics["exposure_pct"] <= MAX_TOTAL_EXPOSURE_PCT * 100,
            f"{metrics['exposure_pct']:.1f}%",
        ),
        (
            "Each position < 10%",
            all((p.position_value / account_size) * 100 <= MAX_SINGLE_POSITION_PCT * 100 for p in positions),
            f"max {max((p.position_value / account_size) * 100 for p in positions):.1f}%" if positions else "N/A",
        ),
    ]

    # Check each sector
    for sector, data in sectors.items():
        ok = data["exposure_pct"] <= MAX_CORRELATED_PCT * 100
        checks.append((
            f"{sector} sector < 25%",
            ok,
            f"{data['exposure_pct']:.1f}%",
        ))

    for label, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {label:<35} ({detail})")

    # ── Available Budget ────────────────────────────────────────
    print_header("AVAILABLE BUDGET FOR NEXT TRADE")
    print(f"  Remaining exposure capacity:    ${fmt(budget['remaining_exposure'])}")
    print(f"  Max single position:            ${fmt(budget['max_single_position'])}")
    print(f"  Max new position value:         ${fmt(budget['max_new_position'])}")
    print(f"  Risk budget (2% of account):    ${fmt(budget['risk_budget'])}")

    if budget["can_add_position"]:
        print(f"\n  You can open a new position up to ${fmt(budget['max_new_position'])} in value.")
        print(f"  With 2% risk ({fmt(budget['risk_budget'])} USD), and a 10% stop,")
        print(f"  that allows ~${fmt(budget['risk_budget'] / 0.10)} notional position.")
    else:
        print("\n  Portfolio is at maximum exposure. Close or reduce a position before adding new ones.")

    if budget["sector_room"]:
        print("\n  Room by sector before hitting 25% limit:")
        for sector, room in sorted(budget["sector_room"].items(), key=lambda x: x[1]):
            print(f"    {sector:<12} ${fmt(room)} remaining")


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Run the portfolio sizer with demo or configured data."""
    positions = get_demo_positions()

    if ACCOUNT_SIZE <= 0:
        print("Error: ACCOUNT_SIZE must be positive")
        sys.exit(1)

    print("Using demo portfolio (5 positions)")
    print(f"Account size: ${fmt(ACCOUNT_SIZE)} (set ACCOUNT_SIZE env var to change)")

    print_portfolio_report(positions, ACCOUNT_SIZE)


if __name__ == "__main__":
    main()
