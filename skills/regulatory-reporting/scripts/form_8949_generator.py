#!/usr/bin/env python3
"""Basic IRS Form 8949 line-item generator from trade data.

Generates Form 8949-compatible line items from a list of trades,
classifying each as short-term (Part I) or long-term (Part II) and
computing gain/loss per disposition.

WARNING: This is a STUB implementation for informational purposes only.
All output must be reviewed by a qualified tax professional before use
in any actual tax filing. This tool does NOT constitute tax advice.

Usage:
    python scripts/form_8949_generator.py --demo
    python scripts/form_8949_generator.py --csv trades.csv
    python scripts/form_8949_generator.py --help

Dependencies:
    None (standard library only)

Environment Variables:
    None required.
"""

import argparse
import csv
import io
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional


# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class Trade:
    """A single buy or sell event."""

    asset: str
    action: str  # "buy" or "sell"
    quantity: Decimal
    price_usd: Decimal
    fee_usd: Decimal
    trade_date: date
    exchange: str = ""

    @property
    def total_usd(self) -> Decimal:
        """Total cost (buy) or proceeds (sell) including fees."""
        if self.action == "buy":
            return (self.quantity * self.price_usd) + self.fee_usd
        return (self.quantity * self.price_usd) - self.fee_usd


@dataclass
class LotAssignment:
    """Maps a sell to a specific buy lot (FIFO)."""

    asset: str
    quantity: Decimal
    date_acquired: date
    date_sold: date
    proceeds_usd: Decimal
    cost_basis_usd: Decimal
    adjustment_code: str = ""
    adjustment_amount: Decimal = field(default_factory=lambda: Decimal("0"))

    @property
    def gain_loss(self) -> Decimal:
        """Net gain or loss after adjustments."""
        return self.proceeds_usd - self.cost_basis_usd - self.adjustment_amount

    @property
    def holding_period(self) -> str:
        """'short-term' if held 365 days or fewer, else 'long-term'."""
        days_held = (self.date_sold - self.date_acquired).days
        return "short-term" if days_held <= 365 else "long-term"

    @property
    def form_8949_part(self) -> str:
        """Part I (short-term) or Part II (long-term)."""
        return "I" if self.holding_period == "short-term" else "II"

    def to_form_row(self) -> dict:
        """Return a dict matching Form 8949 columns."""
        return {
            "(a) Description": f"{self.quantity} {self.asset}",
            "(b) Date Acquired": self.date_acquired.strftime("%m/%d/%Y"),
            "(c) Date Sold": self.date_sold.strftime("%m/%d/%Y"),
            "(d) Proceeds": f"{self.proceeds_usd:.2f}",
            "(e) Cost Basis": f"{self.cost_basis_usd:.2f}",
            "(f) Adjustment Code": self.adjustment_code,
            "(g) Adjustment Amount": f"{self.adjustment_amount:.2f}",
            "(h) Gain or Loss": f"{self.gain_loss:.2f}",
            "Part": self.form_8949_part,
            "Holding Period": self.holding_period,
        }


@dataclass
class ScheduleDSummary:
    """Aggregated totals for Schedule D."""

    short_term_proceeds: Decimal = field(default_factory=lambda: Decimal("0"))
    short_term_basis: Decimal = field(default_factory=lambda: Decimal("0"))
    short_term_adjustments: Decimal = field(default_factory=lambda: Decimal("0"))
    short_term_gain_loss: Decimal = field(default_factory=lambda: Decimal("0"))
    long_term_proceeds: Decimal = field(default_factory=lambda: Decimal("0"))
    long_term_basis: Decimal = field(default_factory=lambda: Decimal("0"))
    long_term_adjustments: Decimal = field(default_factory=lambda: Decimal("0"))
    long_term_gain_loss: Decimal = field(default_factory=lambda: Decimal("0"))

    @property
    def net_gain_loss(self) -> Decimal:
        return self.short_term_gain_loss + self.long_term_gain_loss

    def add_lot(self, lot: LotAssignment) -> None:
        """Add a lot assignment to the running totals."""
        if lot.holding_period == "short-term":
            self.short_term_proceeds += lot.proceeds_usd
            self.short_term_basis += lot.cost_basis_usd
            self.short_term_adjustments += lot.adjustment_amount
            self.short_term_gain_loss += lot.gain_loss
        else:
            self.long_term_proceeds += lot.proceeds_usd
            self.long_term_basis += lot.cost_basis_usd
            self.long_term_adjustments += lot.adjustment_amount
            self.long_term_gain_loss += lot.gain_loss


# ── FIFO Lot Matching ───────────────────────────────────────────────


def match_lots_fifo(trades: list[Trade]) -> list[LotAssignment]:
    """Match sells to buys using FIFO (First In, First Out).

    Args:
        trades: List of Trade objects sorted by date.

    Returns:
        List of LotAssignment objects, one per disposition.

    Raises:
        ValueError: If a sell has insufficient buy lots to cover it.
    """
    # Separate and sort buys by date (FIFO order)
    buy_lots: dict[str, list[tuple[date, Decimal, Decimal]]] = {}
    assignments: list[LotAssignment] = []

    # Sort all trades by date
    sorted_trades = sorted(trades, key=lambda t: t.trade_date)

    for trade in sorted_trades:
        asset = trade.asset.upper()

        if trade.action == "buy":
            if asset not in buy_lots:
                buy_lots[asset] = []
            cost_per_unit = trade.total_usd / trade.quantity
            buy_lots[asset].append([
                trade.trade_date,
                trade.quantity,
                cost_per_unit,
            ])

        elif trade.action == "sell":
            if asset not in buy_lots or not buy_lots[asset]:
                raise ValueError(
                    f"No buy lots available for {trade.quantity} {asset} "
                    f"sold on {trade.trade_date}"
                )

            sell_remaining = trade.quantity
            sell_price_per_unit = trade.total_usd / trade.quantity

            while sell_remaining > Decimal("0"):
                if not buy_lots[asset]:
                    raise ValueError(
                        f"Insufficient buy lots for {asset}: "
                        f"{sell_remaining} units unmatched on {trade.trade_date}"
                    )

                lot = buy_lots[asset][0]
                lot_date, lot_qty, lot_cost = lot[0], lot[1], lot[2]

                if lot_qty <= sell_remaining:
                    # Consume entire lot
                    matched_qty = lot_qty
                    buy_lots[asset].pop(0)
                else:
                    # Partial lot consumption
                    matched_qty = sell_remaining
                    lot[1] = lot_qty - sell_remaining

                proceeds = matched_qty * sell_price_per_unit
                basis = matched_qty * lot_cost

                assignments.append(LotAssignment(
                    asset=asset,
                    quantity=matched_qty,
                    date_acquired=lot_date,
                    date_sold=trade.trade_date,
                    proceeds_usd=proceeds.quantize(Decimal("0.01")),
                    cost_basis_usd=basis.quantize(Decimal("0.01")),
                ))

                sell_remaining -= matched_qty

    return assignments


# ── CSV Parsing ─────────────────────────────────────────────────────


def parse_csv(csv_path: str) -> list[Trade]:
    """Parse trades from a CSV file.

    Expected columns: asset, action, quantity, price_usd, fee_usd,
    trade_date, exchange (optional).

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of Trade objects.
    """
    trades: list[Trade] = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                trade = Trade(
                    asset=row["asset"].strip().upper(),
                    action=row["action"].strip().lower(),
                    quantity=Decimal(row["quantity"].strip()),
                    price_usd=Decimal(row["price_usd"].strip()),
                    fee_usd=Decimal(row.get("fee_usd", "0").strip() or "0"),
                    trade_date=datetime.strptime(
                        row["trade_date"].strip(), "%Y-%m-%d"
                    ).date(),
                    exchange=row.get("exchange", "").strip(),
                )
                if trade.action not in ("buy", "sell"):
                    print(f"Warning: skipping row with action '{trade.action}'")
                    continue
                trades.append(trade)
            except (KeyError, InvalidOperation, ValueError) as e:
                print(f"Warning: skipping malformed row: {e}")
                continue
    return trades


# ── Demo Data ───────────────────────────────────────────────────────


def generate_demo_trades() -> list[Trade]:
    """Generate sample trades for demonstration purposes.

    Returns:
        List of demo Trade objects covering various scenarios.
    """
    return [
        # Buy SOL in January 2025
        Trade("SOL", "buy", Decimal("50"), Decimal("95.00"),
              Decimal("2.50"), date(2025, 1, 10), "Coinbase"),
        # Buy more SOL in March 2025
        Trade("SOL", "buy", Decimal("30"), Decimal("140.00"),
              Decimal("1.80"), date(2025, 3, 15), "Coinbase"),
        # Sell some SOL in June 2025 (short-term, matches Jan lot via FIFO)
        Trade("SOL", "sell", Decimal("40"), Decimal("180.00"),
              Decimal("3.60"), date(2025, 6, 20), "Coinbase"),
        # Buy BTC in February 2025
        Trade("BTC", "buy", Decimal("0.5"), Decimal("42000.00"),
              Decimal("10.00"), date(2025, 2, 1), "Kraken"),
        # Sell BTC in September 2025 (short-term)
        Trade("BTC", "sell", Decimal("0.3"), Decimal("58000.00"),
              Decimal("8.70"), date(2025, 9, 10), "Kraken"),
        # Buy ETH in January 2024 (for long-term example)
        Trade("ETH", "buy", Decimal("5"), Decimal("2200.00"),
              Decimal("5.50"), date(2024, 1, 5), "Coinbase"),
        # Sell ETH in March 2025 (long-term, held > 1 year)
        Trade("ETH", "sell", Decimal("3"), Decimal("3500.00"),
              Decimal("5.25"), date(2025, 3, 20), "Coinbase"),
    ]


# ── Report Formatting ──────────────────────────────────────────────


def print_form_8949(assignments: list[LotAssignment]) -> None:
    """Print Form 8949 line items to stdout.

    Args:
        assignments: List of LotAssignment objects from FIFO matching.
    """
    part_i = [a for a in assignments if a.form_8949_part == "I"]
    part_ii = [a for a in assignments if a.form_8949_part == "II"]

    header = (
        f"{'Description':<20} {'Acquired':<12} {'Sold':<12} "
        f"{'Proceeds':>12} {'Basis':>12} {'Adj Code':>9} "
        f"{'Adj Amt':>10} {'Gain/Loss':>12}"
    )
    separator = "-" * len(header)

    if part_i:
        print("\n" + "=" * len(header))
        print("FORM 8949 — PART I: Short-Term (held one year or less)")
        print("Box C: Basis NOT reported to IRS; no Form 1099-B received")
        print("=" * len(header))
        print(header)
        print(separator)
        for lot in part_i:
            row = lot.to_form_row()
            print(
                f"{row['(a) Description']:<20} "
                f"{row['(b) Date Acquired']:<12} "
                f"{row['(c) Date Sold']:<12} "
                f"${row['(d) Proceeds']:>11} "
                f"${row['(e) Cost Basis']:>11} "
                f"{row['(f) Adjustment Code']:>9} "
                f"${row['(g) Adjustment Amount']:>9} "
                f"${row['(h) Gain or Loss']:>11}"
            )

    if part_ii:
        print("\n" + "=" * len(header))
        print("FORM 8949 — PART II: Long-Term (held more than one year)")
        print("Box F: Basis NOT reported to IRS; no Form 1099-B received")
        print("=" * len(header))
        print(header)
        print(separator)
        for lot in part_ii:
            row = lot.to_form_row()
            print(
                f"{row['(a) Description']:<20} "
                f"{row['(b) Date Acquired']:<12} "
                f"{row['(c) Date Sold']:<12} "
                f"${row['(d) Proceeds']:>11} "
                f"${row['(e) Cost Basis']:>11} "
                f"{row['(f) Adjustment Code']:>9} "
                f"${row['(g) Adjustment Amount']:>9} "
                f"${row['(h) Gain or Loss']:>11}"
            )


def print_schedule_d(summary: ScheduleDSummary) -> None:
    """Print Schedule D summary totals.

    Args:
        summary: Aggregated ScheduleDSummary object.
    """
    print("\n" + "=" * 60)
    print("SCHEDULE D SUMMARY — Capital Gains and Losses")
    print("=" * 60)
    print(f"\nShort-Term Capital Gains/Losses (Part I):")
    print(f"  Total Proceeds:    ${summary.short_term_proceeds:>12,.2f}")
    print(f"  Total Cost Basis:  ${summary.short_term_basis:>12,.2f}")
    print(f"  Total Adjustments: ${summary.short_term_adjustments:>12,.2f}")
    print(f"  Net Short-Term:    ${summary.short_term_gain_loss:>12,.2f}")
    print(f"\nLong-Term Capital Gains/Losses (Part II):")
    print(f"  Total Proceeds:    ${summary.long_term_proceeds:>12,.2f}")
    print(f"  Total Cost Basis:  ${summary.long_term_basis:>12,.2f}")
    print(f"  Total Adjustments: ${summary.long_term_adjustments:>12,.2f}")
    print(f"  Net Long-Term:     ${summary.long_term_gain_loss:>12,.2f}")
    print(f"\nCombined Net Gain/(Loss): ${summary.net_gain_loss:>12,.2f}")
    if summary.net_gain_loss < 0:
        deductible = max(summary.net_gain_loss, Decimal("-3000"))
        carryforward = summary.net_gain_loss - deductible
        print(f"  Deductible this year:   ${deductible:>12,.2f}")
        if carryforward < 0:
            print(f"  Carryforward to next:   ${carryforward:>12,.2f}")


def export_json(assignments: list[LotAssignment]) -> str:
    """Export lot assignments as JSON.

    Args:
        assignments: List of LotAssignment objects.

    Returns:
        JSON string of form 8949 rows.
    """
    rows = [a.to_form_row() for a in assignments]
    return json.dumps(rows, indent=2)


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point: parse arguments and generate Form 8949 report."""
    parser = argparse.ArgumentParser(
        description="Generate IRS Form 8949 line items from trade data. "
        "WARNING: Output must be reviewed by a tax professional.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "DISCLAIMER: This tool is for informational purposes only and "
            "does NOT constitute tax advice. Consult a qualified tax "
            "professional before using any output for tax filings."
        ),
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run with built-in sample trade data",
    )
    parser.add_argument(
        "--csv", type=str, default="",
        help="Path to CSV file with columns: asset, action, quantity, "
        "price_usd, fee_usd, trade_date, exchange",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON instead of formatted text",
    )
    args = parser.parse_args()

    if not args.demo and not args.csv:
        parser.print_help()
        print("\nError: specify --demo or --csv <file>")
        sys.exit(1)

    # Load trades
    if args.demo:
        print("=" * 60)
        print("DEMO MODE — Using sample trade data")
        print("This is NOT real financial data")
        print("=" * 60)
        trades = generate_demo_trades()
    else:
        trades = parse_csv(args.csv)
        if not trades:
            print("No valid trades found in CSV file.")
            sys.exit(1)

    # Match lots via FIFO
    try:
        assignments = match_lots_fifo(trades)
    except ValueError as e:
        print(f"Error matching lots: {e}")
        sys.exit(1)

    if not assignments:
        print("No dispositions found (no sells matched to buys).")
        sys.exit(0)

    # Output
    if args.json:
        print(export_json(assignments))
    else:
        print_form_8949(assignments)

        # Schedule D summary
        summary = ScheduleDSummary()
        for lot in assignments:
            summary.add_lot(lot)
        print_schedule_d(summary)

    print("\n" + "-" * 60)
    print("WARNING: This output is for informational purposes only.")
    print("Consult a qualified tax professional before filing.")
    print("-" * 60)


if __name__ == "__main__":
    main()
