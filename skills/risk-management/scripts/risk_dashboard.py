#!/usr/bin/env python3
"""Portfolio risk dashboard with limit checking and color-coded status.

Analyzes a portfolio of positions against configurable risk limits and
displays a comprehensive dashboard showing exposure, concentration,
drawdown, and circuit breaker status.

Usage:
    python scripts/risk_dashboard.py --demo
    python scripts/risk_dashboard.py --positions positions.json

Dependencies:
    None (pure Python, no external packages required)

Environment Variables:
    ACCOUNT_SIZE: Total account size in SOL (default: 100)
"""

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Optional


# ── Configuration ───────────────────────────────────────────────────
ACCOUNT_SIZE = float(os.getenv("ACCOUNT_SIZE", "100"))

# Risk limits (configurable)
LIMITS = {
    "max_single_position_pct": 0.10,      # 10% of account
    "max_total_exposure_pct": 0.80,        # 80% of account
    "max_daily_loss_pct": 0.03,            # 3% daily loss
    "max_drawdown_warning_pct": 0.10,      # 10% drawdown warning
    "max_drawdown_critical_pct": 0.15,     # 15% drawdown critical
    "max_drawdown_halt_pct": 0.20,         # 20% drawdown halt
    "max_consecutive_losses": 3,           # consecutive loss warning
    "max_sector_concentration_pct": 0.30,  # 30% per sector
    "max_concurrent_positions": 10,        # maximum open positions
}


# ── Data Models ─────────────────────────────────────────────────────
@dataclass
class Position:
    """A single portfolio position."""
    token: str
    entry_price: float
    current_price: float
    size_sol: float
    stop_loss: Optional[float] = None
    sector: str = "unknown"
    token_type: str = "mid-cap"  # blue-chip, mid-cap, small-cap, micro, pumpfun

    @property
    def pnl_sol(self) -> float:
        """Unrealized P&L in SOL."""
        if self.entry_price == 0:
            return 0.0
        return self.size_sol * (self.current_price / self.entry_price - 1.0)

    @property
    def pnl_pct(self) -> float:
        """Unrealized P&L as percentage."""
        if self.entry_price == 0:
            return 0.0
        return (self.current_price / self.entry_price - 1.0) * 100

    @property
    def risk_to_stop(self) -> float:
        """Risk in SOL if stop loss is hit."""
        if self.stop_loss is None or self.entry_price == 0:
            return self.size_sol  # Assume 100% loss if no stop
        loss_pct = (self.entry_price - self.stop_loss) / self.entry_price
        return self.size_sol * max(0.0, loss_pct)

    @property
    def current_value(self) -> float:
        """Current position value in SOL."""
        if self.entry_price == 0:
            return 0.0
        return self.size_sol * (self.current_price / self.entry_price)


@dataclass
class PortfolioState:
    """Aggregate portfolio state for risk assessment."""
    account_size: float
    positions: list[Position]
    realized_pnl_today: float = 0.0
    equity_peak: float = 0.0
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    trade_history: list[float] = field(default_factory=list)


# ── Status Helpers ──────────────────────────────────────────────────
class Status:
    """Color-coded status indicators."""
    OK = "OK"
    WARNING = "WARNING"
    BREACH = "BREACH"


def colorize(text: str, status: str) -> str:
    """Add ANSI color codes based on status."""
    colors = {
        Status.OK: "\033[92m",       # Green
        Status.WARNING: "\033[93m",  # Yellow
        Status.BREACH: "\033[91m",   # Red
    }
    reset = "\033[0m"
    color = colors.get(status, "")
    return f"{color}{text}{reset}"


def status_icon(status: str) -> str:
    """Return a text icon for the status."""
    icons = {
        Status.OK: "[OK]",
        Status.WARNING: "[WARN]",
        Status.BREACH: "[BREACH]",
    }
    return icons.get(status, "[??]")


# ── Risk Calculations ───────────────────────────────────────────────
def calculate_total_exposure(positions: list[Position], account_size: float) -> tuple[float, float]:
    """Calculate total deployed capital.

    Returns:
        Tuple of (total_sol, percentage_of_account).
    """
    total = sum(p.size_sol for p in positions)
    pct = total / account_size if account_size > 0 else 0.0
    return total, pct


def calculate_total_risk(positions: list[Position], account_size: float) -> tuple[float, float]:
    """Calculate total portfolio risk (distance to stops).

    Returns:
        Tuple of (total_risk_sol, percentage_of_account).
    """
    total = sum(p.risk_to_stop for p in positions)
    pct = total / account_size if account_size > 0 else 0.0
    return total, pct


def calculate_largest_position(positions: list[Position], account_size: float) -> tuple[str, float, float]:
    """Find the largest single position.

    Returns:
        Tuple of (token_name, size_sol, percentage_of_account).
    """
    if not positions:
        return ("none", 0.0, 0.0)
    largest = max(positions, key=lambda p: p.size_sol)
    pct = largest.size_sol / account_size if account_size > 0 else 0.0
    return (largest.token, largest.size_sol, pct)


def calculate_hhi(positions: list[Position]) -> float:
    """Calculate Herfindahl-Hirschman Index for position concentration.

    Returns:
        HHI value between 0 and 10000.
        - 10000: single position (maximum concentration)
        - <1500: well diversified
        - 1500-2500: moderate concentration
        - >2500: high concentration
    """
    if not positions:
        return 0.0
    total = sum(p.size_sol for p in positions)
    if total == 0:
        return 0.0
    shares = [(p.size_sol / total) * 100 for p in positions]
    return sum(s * s for s in shares)


def calculate_daily_pnl(
    positions: list[Position], realized_pnl: float, account_size: float
) -> tuple[float, float]:
    """Calculate total daily P&L (realized + unrealized).

    Returns:
        Tuple of (total_pnl_sol, percentage_of_account).
    """
    unrealized = sum(p.pnl_sol for p in positions)
    total = realized_pnl + unrealized
    pct = total / account_size if account_size > 0 else 0.0
    return total, pct


def calculate_drawdown(current_equity: float, equity_peak: float) -> float:
    """Calculate current drawdown from peak.

    Returns:
        Drawdown as a positive fraction (0.10 = 10% drawdown).
    """
    if equity_peak <= 0:
        return 0.0
    return max(0.0, (equity_peak - current_equity) / equity_peak)


def calculate_sector_concentration(
    positions: list[Position], account_size: float
) -> dict[str, float]:
    """Calculate allocation percentage per sector.

    Returns:
        Dict mapping sector name to percentage of account.
    """
    sectors: dict[str, float] = {}
    for p in positions:
        sectors[p.sector] = sectors.get(p.sector, 0.0) + p.size_sol
    return {s: v / account_size for s, v in sectors.items()} if account_size > 0 else {}


def recovery_needed(drawdown: float) -> float:
    """Calculate the gain needed to recover from a drawdown.

    Args:
        drawdown: Drawdown as a positive fraction (e.g., 0.20 for 20%).

    Returns:
        Required gain as a positive fraction.
    """
    if drawdown >= 1.0:
        return float("inf")
    if drawdown <= 0.0:
        return 0.0
    return drawdown / (1.0 - drawdown)


def drawdown_response_level(drawdown: float) -> tuple[str, str]:
    """Determine drawdown response level and recommendation.

    Returns:
        Tuple of (level_name, recommendation).
    """
    if drawdown < 0.05:
        return ("Normal", "Continue trading at full size")
    elif drawdown < 0.10:
        return ("Caution", "Reduce position sizes by 25-50%")
    elif drawdown < 0.15:
        return ("Warning", "Minimum position sizes only")
    elif drawdown < 0.20:
        return ("Critical", "Halt new trades, manage existing only")
    else:
        return ("Emergency", "Full stop, review everything before resuming")


# ── Dashboard Output ────────────────────────────────────────────────
def print_separator(char: str = "=", width: int = 70) -> None:
    """Print a separator line."""
    print(char * width)


def print_header(title: str) -> None:
    """Print a section header."""
    print()
    print_separator()
    print(f"  {title}")
    print_separator()


def print_metric(
    label: str, value: str, status: str, limit_desc: str = ""
) -> None:
    """Print a single metric line with status."""
    icon = colorize(status_icon(status), status)
    limit_text = f"  (limit: {limit_desc})" if limit_desc else ""
    print(f"  {icon}  {label:<35s} {value:<20s}{limit_text}")


def run_dashboard(state: PortfolioState) -> dict[str, str]:
    """Run the risk dashboard and print results.

    Args:
        state: Current portfolio state.

    Returns:
        Dict of check names to status values for programmatic use.
    """
    results: dict[str, str] = {}
    limits = LIMITS

    print_header("PORTFOLIO RISK DASHBOARD")
    print(f"  Account Size: {state.account_size:.2f} SOL")
    print(f"  Open Positions: {len(state.positions)}")
    print(f"  Equity Peak: {state.equity_peak:.2f} SOL")

    # ── Exposure ────────────────────────────────────────────────
    print_header("EXPOSURE")

    total_sol, total_pct = calculate_total_exposure(state.positions, state.account_size)
    exp_status = (
        Status.BREACH if total_pct > limits["max_total_exposure_pct"]
        else Status.WARNING if total_pct > limits["max_total_exposure_pct"] * 0.8
        else Status.OK
    )
    print_metric(
        "Total Exposure",
        f"{total_sol:.2f} SOL ({total_pct:.1%})",
        exp_status,
        f"{limits['max_total_exposure_pct']:.0%}",
    )
    results["total_exposure"] = exp_status

    cash = state.account_size - total_sol
    cash_pct = cash / state.account_size if state.account_size > 0 else 0
    cash_status = Status.OK if cash_pct >= 0.20 else Status.WARNING if cash_pct >= 0.10 else Status.BREACH
    print_metric("Cash Reserve", f"{cash:.2f} SOL ({cash_pct:.1%})", cash_status, ">= 20%")
    results["cash_reserve"] = cash_status

    pos_count_status = (
        Status.BREACH if len(state.positions) > limits["max_concurrent_positions"]
        else Status.WARNING if len(state.positions) > limits["max_concurrent_positions"] * 0.8
        else Status.OK
    )
    print_metric(
        "Concurrent Positions",
        f"{len(state.positions)}",
        pos_count_status,
        f"<= {limits['max_concurrent_positions']}",
    )
    results["concurrent_positions"] = pos_count_status

    # ── Concentration ───────────────────────────────────────────
    print_header("CONCENTRATION")

    token_name, token_sol, token_pct = calculate_largest_position(state.positions, state.account_size)
    pos_status = (
        Status.BREACH if token_pct > limits["max_single_position_pct"]
        else Status.WARNING if token_pct > limits["max_single_position_pct"] * 0.8
        else Status.OK
    )
    print_metric(
        f"Largest Position ({token_name})",
        f"{token_sol:.2f} SOL ({token_pct:.1%})",
        pos_status,
        f"{limits['max_single_position_pct']:.0%}",
    )
    results["largest_position"] = pos_status

    hhi = calculate_hhi(state.positions)
    hhi_status = Status.OK if hhi < 1500 else Status.WARNING if hhi < 2500 else Status.BREACH
    hhi_label = "Low" if hhi < 1500 else "Moderate" if hhi < 2500 else "High"
    print_metric("Concentration (HHI)", f"{hhi:.0f} ({hhi_label})", hhi_status, "< 2500")
    results["hhi"] = hhi_status

    sectors = calculate_sector_concentration(state.positions, state.account_size)
    for sector, pct in sorted(sectors.items(), key=lambda x: -x[1]):
        sec_status = (
            Status.BREACH if pct > limits["max_sector_concentration_pct"]
            else Status.WARNING if pct > limits["max_sector_concentration_pct"] * 0.8
            else Status.OK
        )
        print_metric(
            f"  Sector: {sector}",
            f"{pct:.1%}",
            sec_status,
            f"{limits['max_sector_concentration_pct']:.0%}",
        )
        results[f"sector_{sector}"] = sec_status

    # ── Risk ────────────────────────────────────────────────────
    print_header("RISK")

    risk_sol, risk_pct = calculate_total_risk(state.positions, state.account_size)
    risk_status = Status.OK if risk_pct < 0.05 else Status.WARNING if risk_pct < 0.10 else Status.BREACH
    print_metric("Portfolio Risk (to stops)", f"{risk_sol:.2f} SOL ({risk_pct:.1%})", risk_status, "< 10%")
    results["portfolio_risk"] = risk_status

    # ── Daily P&L ───────────────────────────────────────────────
    print_header("DAILY P&L")

    daily_sol, daily_pct = calculate_daily_pnl(
        state.positions, state.realized_pnl_today, state.account_size
    )
    daily_status = (
        Status.BREACH if daily_pct < -limits["max_daily_loss_pct"]
        else Status.WARNING if daily_pct < -limits["max_daily_loss_pct"] * 0.5
        else Status.OK
    )
    pnl_sign = "+" if daily_sol >= 0 else ""
    print_metric(
        "Daily P&L",
        f"{pnl_sign}{daily_sol:.2f} SOL ({pnl_sign}{daily_pct:.1%})",
        daily_status,
        f"> -{limits['max_daily_loss_pct']:.0%}",
    )
    results["daily_pnl"] = daily_status

    # ── Drawdown ────────────────────────────────────────────────
    print_header("DRAWDOWN")

    current_equity = state.account_size + sum(p.pnl_sol for p in state.positions) + state.realized_pnl_today
    dd = calculate_drawdown(current_equity, state.equity_peak) if state.equity_peak > 0 else 0.0
    dd_level, dd_rec = drawdown_response_level(dd)
    dd_status = (
        Status.BREACH if dd >= limits["max_drawdown_critical_pct"]
        else Status.WARNING if dd >= limits["max_drawdown_warning_pct"]
        else Status.OK
    )
    print_metric("Current Drawdown", f"{dd:.1%} ({dd_level})", dd_status, f"< {limits['max_drawdown_warning_pct']:.0%}")
    results["drawdown"] = dd_status

    if dd > 0:
        rec = recovery_needed(dd)
        print_metric("Recovery Needed", f"+{rec:.1%}", Status.WARNING if dd >= 0.10 else Status.OK)
        print(f"         Recommendation: {dd_rec}")

    # ── Streaks ─────────────────────────────────────────────────
    print_header("STREAKS & CIRCUIT BREAKERS")

    if state.consecutive_losses > 0:
        streak_status = (
            Status.BREACH if state.consecutive_losses >= 5
            else Status.WARNING if state.consecutive_losses >= limits["max_consecutive_losses"]
            else Status.OK
        )
        print_metric(
            "Consecutive Losses",
            f"{state.consecutive_losses}",
            streak_status,
            f"< {limits['max_consecutive_losses']}",
        )
        results["consecutive_losses"] = streak_status

        if state.consecutive_losses >= 7:
            print(f"         ACTION: Halt trading for 24 hours, full review required")
        elif state.consecutive_losses >= 5:
            print(f"         ACTION: Minimum position sizes only")
        elif state.consecutive_losses >= 3:
            print(f"         ACTION: Reduce position sizes by 50%")
    else:
        print_metric("Consecutive Losses", "0", Status.OK, f"< {limits['max_consecutive_losses']}")
        results["consecutive_losses"] = Status.OK

    if state.consecutive_wins > 0:
        print_metric("Consecutive Wins", f"{state.consecutive_wins}", Status.OK)

    # ── Positions Detail ────────────────────────────────────────
    if state.positions:
        print_header("POSITION DETAILS")
        print(f"  {'Token':<12s} {'Size':>8s} {'Entry':>10s} {'Current':>10s} {'P&L':>10s} {'P&L%':>8s} {'Risk':>8s}")
        print("  " + "-" * 68)
        for p in sorted(state.positions, key=lambda x: -x.size_sol):
            pnl_sign = "+" if p.pnl_sol >= 0 else ""
            print(
                f"  {p.token:<12s} {p.size_sol:>7.2f}S {p.entry_price:>10.6f} "
                f"{p.current_price:>10.6f} {pnl_sign}{p.pnl_sol:>8.2f}S "
                f"{pnl_sign}{p.pnl_pct:>6.1f}% {p.risk_to_stop:>7.2f}S"
            )

    # ── Summary ─────────────────────────────────────────────────
    print_header("SUMMARY")

    breaches = [k for k, v in results.items() if v == Status.BREACH]
    warnings = [k for k, v in results.items() if v == Status.WARNING]

    if breaches:
        print(colorize(f"  BREACHES ({len(breaches)}):", Status.BREACH))
        for b in breaches:
            print(colorize(f"    - {b}", Status.BREACH))
    if warnings:
        print(colorize(f"  WARNINGS ({len(warnings)}):", Status.WARNING))
        for w in warnings:
            print(colorize(f"    - {w}", Status.WARNING))
    if not breaches and not warnings:
        print(colorize("  All checks passed. Portfolio within risk limits.", Status.OK))

    print()
    return results


# ── Demo Data ───────────────────────────────────────────────────────
def create_demo_portfolio() -> PortfolioState:
    """Create a realistic demo portfolio for dashboard demonstration."""
    positions = [
        Position(
            token="SOL",
            entry_price=145.00,
            current_price=142.50,
            size_sol=8.0,
            stop_loss=135.00,
            sector="infrastructure",
            token_type="blue-chip",
        ),
        Position(
            token="JUP",
            entry_price=0.85,
            current_price=0.92,
            size_sol=5.0,
            stop_loss=0.75,
            sector="defi",
            token_type="large-cap",
        ),
        Position(
            token="RAY",
            entry_price=2.10,
            current_price=1.95,
            size_sol=4.0,
            stop_loss=1.80,
            sector="defi",
            token_type="large-cap",
        ),
        Position(
            token="BONK",
            entry_price=0.00002,
            current_price=0.000025,
            size_sol=3.0,
            stop_loss=0.000015,
            sector="meme",
            token_type="mid-cap",
        ),
        Position(
            token="WIF",
            entry_price=1.80,
            current_price=1.65,
            size_sol=2.5,
            stop_loss=1.50,
            sector="meme",
            token_type="mid-cap",
        ),
        Position(
            token="NEWMEME",
            entry_price=0.001,
            current_price=0.0008,
            size_sol=0.5,
            stop_loss=None,  # No stop on PumpFun
            sector="meme",
            token_type="pumpfun",
        ),
        Position(
            token="ORCA",
            entry_price=3.50,
            current_price=3.60,
            size_sol=3.0,
            stop_loss=3.10,
            sector="defi",
            token_type="large-cap",
        ),
    ]

    return PortfolioState(
        account_size=ACCOUNT_SIZE,
        positions=positions,
        realized_pnl_today=-0.8,
        equity_peak=ACCOUNT_SIZE * 1.05,  # Was 5% higher at peak
        consecutive_losses=2,
        consecutive_wins=0,
    )


def load_positions_from_file(filepath: str) -> PortfolioState:
    """Load portfolio state from a JSON file.

    Expected format:
    {
        "account_size": 100,
        "equity_peak": 105,
        "realized_pnl_today": -0.5,
        "consecutive_losses": 1,
        "consecutive_wins": 0,
        "positions": [
            {
                "token": "SOL",
                "entry_price": 145.0,
                "current_price": 142.5,
                "size_sol": 8.0,
                "stop_loss": 135.0,
                "sector": "infrastructure",
                "token_type": "blue-chip"
            }
        ]
    }
    """
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading positions file: {e}")
        sys.exit(1)

    positions = []
    for p in data.get("positions", []):
        positions.append(Position(
            token=p["token"],
            entry_price=p["entry_price"],
            current_price=p["current_price"],
            size_sol=p["size_sol"],
            stop_loss=p.get("stop_loss"),
            sector=p.get("sector", "unknown"),
            token_type=p.get("token_type", "mid-cap"),
        ))

    return PortfolioState(
        account_size=data.get("account_size", ACCOUNT_SIZE),
        positions=positions,
        realized_pnl_today=data.get("realized_pnl_today", 0.0),
        equity_peak=data.get("equity_peak", data.get("account_size", ACCOUNT_SIZE)),
        consecutive_losses=data.get("consecutive_losses", 0),
        consecutive_wins=data.get("consecutive_wins", 0),
    )


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Entry point for the risk dashboard."""
    parser = argparse.ArgumentParser(
        description="Portfolio risk dashboard — analyze positions against risk limits"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with demo portfolio data",
    )
    parser.add_argument(
        "--positions",
        type=str,
        help="Path to JSON file with portfolio positions",
    )
    args = parser.parse_args()

    if args.demo:
        state = create_demo_portfolio()
        print("\n  [Running with demo portfolio data]")
    elif args.positions:
        state = load_positions_from_file(args.positions)
    else:
        parser.print_help()
        print("\nProvide --demo or --positions <file.json>")
        sys.exit(1)

    results = run_dashboard(state)

    # Exit with non-zero code if any breaches
    breaches = [k for k, v in results.items() if v == Status.BREACH]
    sys.exit(1 if breaches else 0)


if __name__ == "__main__":
    main()
