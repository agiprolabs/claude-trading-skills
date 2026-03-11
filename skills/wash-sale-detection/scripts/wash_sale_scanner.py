#!/usr/bin/env python3
"""Wash sale scanner for cryptocurrency trades under 2025 US tax rules.

Loads a trade history, identifies wash sales within the 61-day window,
computes disallowed losses and basis adjustments, and shows safe re-entry
countdowns for tokens sold at a loss.

Usage:
    python scripts/wash_sale_scanner.py --demo
    python scripts/wash_sale_scanner.py --csv trades.csv

Dependencies:
    None (Python 3.10+ standard library only)

Environment Variables:
    None required.

DISCLAIMER: This tool is for informational purposes only and does NOT
constitute tax advice. Consult a qualified tax professional for guidance
on your specific tax situation.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


# ── Data Models ─────────────────────────────────────────────────────

WASH_SALE_WINDOW_DAYS = 30


@dataclass
class Trade:
    """A single trade record."""

    date: date
    action: str  # "buy" or "sell"
    token: str
    qty: float
    price: float
    trade_id: int = 0

    @property
    def total(self) -> float:
        return self.qty * self.price

    def __str__(self) -> str:
        return (
            f"[{self.trade_id:>3}] {self.date}  {self.action.upper():>4}  "
            f"{self.qty:>10.4f} {self.token:<6} @ ${self.price:>10.2f}  "
            f"= ${self.total:>12.2f}"
        )


@dataclass
class WashSale:
    """A detected wash sale event."""

    token: str
    sale_date: date
    sale_qty: float
    sale_price: float
    sale_basis_per_unit: float
    replacement_date: date
    replacement_qty: float
    replacement_price: float
    matched_qty: float
    disallowed_loss: float
    adjusted_basis: float
    sale_trade_id: int = 0
    replacement_trade_id: int = 0

    def __str__(self) -> str:
        return (
            f"  WASH SALE: {self.token}\n"
            f"    Sale:        {self.sale_date} — {self.matched_qty:.4f} units "
            f"@ ${self.sale_price:.2f} (basis ${self.sale_basis_per_unit:.2f})\n"
            f"    Replacement: {self.replacement_date} — {self.replacement_qty:.4f} units "
            f"@ ${self.replacement_price:.2f}\n"
            f"    Disallowed loss:  ${self.disallowed_loss:.2f}\n"
            f"    Adjusted basis:   ${self.adjusted_basis:.2f} "
            f"(${self.adjusted_basis / self.matched_qty:.2f}/unit)"
        )


@dataclass
class Countdown:
    """Safe re-entry countdown for a token sold at a loss."""

    token: str
    sale_date: date
    loss_amount: float
    window_close: date
    as_of: date

    @property
    def days_remaining(self) -> int:
        delta = (self.window_close - self.as_of).days
        return max(0, delta)

    @property
    def is_safe(self) -> bool:
        return self.days_remaining == 0

    @property
    def status(self) -> str:
        if self.is_safe:
            return "SAFE to re-enter"
        return f"DO NOT BUY — {self.days_remaining} days remaining"

    def __str__(self) -> str:
        return (
            f"  {self.token:<8} | Sale: {self.sale_date} | "
            f"Loss: ${self.loss_amount:>10.2f} | "
            f"Window closes: {self.window_close} | {self.status}"
        )


@dataclass
class ScanResults:
    """Complete results from a wash sale scan."""

    trades: list[Trade] = field(default_factory=list)
    wash_sales: list[WashSale] = field(default_factory=list)
    countdowns: list[Countdown] = field(default_factory=list)
    total_disallowed: float = 0.0
    total_deductible: float = 0.0
    total_realized_losses: float = 0.0


# ── Scanner ─────────────────────────────────────────────────────────

class WashSaleScanner:
    """Scans a trade history for wash sales under the 61-day window rule.

    Args:
        trades: List of trade dictionaries or Trade objects.
        as_of: Date for countdown calculations (defaults to today).
    """

    def __init__(
        self,
        trades: list[dict | Trade],
        as_of: Optional[date] = None,
    ) -> None:
        self.as_of = as_of or date.today()
        self.trades = self._normalize_trades(trades)

    def _normalize_trades(self, raw_trades: list[dict | Trade]) -> list[Trade]:
        """Convert input trades to Trade objects and assign IDs."""
        trades: list[Trade] = []
        for i, t in enumerate(raw_trades):
            if isinstance(t, Trade):
                t.trade_id = i + 1
                trades.append(t)
            elif isinstance(t, dict):
                trade_date = t["date"]
                if isinstance(trade_date, str):
                    trade_date = date.fromisoformat(trade_date)
                trades.append(Trade(
                    date=trade_date,
                    action=t["action"].lower(),
                    token=t["token"].upper(),
                    qty=float(t["qty"]),
                    price=float(t["price"]),
                    trade_id=i + 1,
                ))
            else:
                raise TypeError(f"Unsupported trade type: {type(t)}")
        trades.sort(key=lambda x: (x.date, x.trade_id))
        return trades

    def scan(self) -> ScanResults:
        """Run the wash sale scan across all trades.

        Returns:
            ScanResults with detected wash sales, countdowns, and totals.
        """
        results = ScanResults(trades=list(self.trades))
        tokens = {t.token for t in self.trades}

        for token in sorted(tokens):
            self._scan_token(token, results)

        results.total_disallowed = sum(ws.disallowed_loss for ws in results.wash_sales)
        results.total_realized_losses = (
            results.total_disallowed + results.total_deductible
        )
        return results

    def _scan_token(self, token: str, results: ScanResults) -> None:
        """Scan a single token for wash sales."""
        token_trades = [t for t in self.trades if t.token == token]
        sells = [t for t in token_trades if t.action == "sell"]
        buys = [t for t in token_trades if t.action == "buy"]

        # Track cost basis per buy lot (simple: use buy price as basis)
        # In production, this would use FIFO/LIFO/specific identification
        buy_basis: dict[int, float] = {b.trade_id: b.price for b in buys}

        for sell in sells:
            # Determine cost basis for this sale using earliest unmatched buys (FIFO)
            basis_per_unit = self._get_basis_for_sale(sell, buys, buy_basis)
            loss_per_unit = basis_per_unit - sell.price

            if loss_per_unit <= 0:
                # No loss — no wash sale possible
                continue

            total_loss = loss_per_unit * sell.qty
            remaining_qty = sell.qty

            # Find replacement purchases within the 61-day window
            window_start = sell.date - timedelta(days=WASH_SALE_WINDOW_DAYS)
            window_end = sell.date + timedelta(days=WASH_SALE_WINDOW_DAYS)

            replacements = [
                b for b in buys
                if window_start <= b.date <= window_end
                and b.date != sell.date
                and b.trade_id != sell.trade_id
            ]
            # Also include same-day buys that occur after the sell (by trade_id)
            same_day_buys = [
                b for b in buys
                if b.date == sell.date and b.trade_id > sell.trade_id
            ]
            replacements = sorted(
                replacements + same_day_buys,
                key=lambda x: (x.date, x.trade_id),
            )

            matched_any = False
            for replacement in replacements:
                if remaining_qty <= 0:
                    break

                matched_qty = min(remaining_qty, replacement.qty)
                disallowed = loss_per_unit * matched_qty
                original_cost = replacement.price * matched_qty
                adjusted = original_cost + disallowed

                ws = WashSale(
                    token=token,
                    sale_date=sell.date,
                    sale_qty=sell.qty,
                    sale_price=sell.price,
                    sale_basis_per_unit=basis_per_unit,
                    replacement_date=replacement.date,
                    replacement_qty=replacement.qty,
                    replacement_price=replacement.price,
                    matched_qty=matched_qty,
                    disallowed_loss=disallowed,
                    adjusted_basis=adjusted,
                    sale_trade_id=sell.trade_id,
                    replacement_trade_id=replacement.trade_id,
                )
                results.wash_sales.append(ws)
                remaining_qty -= matched_qty
                matched_any = True

            # Deductible portion = unmatched quantity
            deductible = loss_per_unit * remaining_qty
            results.total_deductible += deductible

            # Add countdown for this loss sale
            window_close = sell.date + timedelta(days=WASH_SALE_WINDOW_DAYS + 1)
            results.countdowns.append(Countdown(
                token=token,
                sale_date=sell.date,
                loss_amount=total_loss,
                window_close=window_close,
                as_of=self.as_of,
            ))

    def _get_basis_for_sale(
        self,
        sell: Trade,
        buys: list[Trade],
        buy_basis: dict[int, float],
    ) -> float:
        """Get the cost basis per unit for a sell trade (simplified FIFO).

        In a production system this would track lot-level consumption.
        Here we use the average basis of prior buys as a simplification.
        """
        prior_buys = [b for b in buys if b.date <= sell.date]
        if not prior_buys:
            return sell.price  # No basis info, assume breakeven

        total_cost = sum(b.qty * buy_basis[b.trade_id] for b in prior_buys)
        total_qty = sum(b.qty for b in prior_buys)
        if total_qty == 0:
            return sell.price
        return total_cost / total_qty


# ── CSV Loader ──────────────────────────────────────────────────────

def load_trades_from_csv(filepath: str) -> list[dict]:
    """Load trades from a CSV file.

    Expected columns: date, action, token, qty, price
    Date format: YYYY-MM-DD

    Args:
        filepath: Path to the CSV file.

    Returns:
        List of trade dictionaries.
    """
    trades: list[dict] = []
    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trades.append({
                    "date": row["date"],
                    "action": row["action"],
                    "token": row["token"],
                    "qty": float(row["qty"]),
                    "price": float(row["price"]),
                })
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    except KeyError as e:
        print(f"Error: Missing column in CSV: {e}")
        print("Expected columns: date, action, token, qty, price")
        sys.exit(1)
    return trades


# ── Demo Data ───────────────────────────────────────────────────────

def get_demo_trades() -> list[dict]:
    """Return demo trade data illustrating wash sale scenarios.

    Scenarios covered:
    1. Simple wash sale: sell SOL at loss, rebuy within 15 days
    2. No wash sale: sell ETH at loss, wait 35 days to rebuy
    3. Partial match: sell BONK at loss, rebuy smaller quantity
    4. Pre-sale trigger: buy JUP, then sell existing JUP at loss within 30 days
    5. Chained wash sale: repeated sell-at-loss and rebuy on RAY
    """
    return [
        # === Scenario 1: Simple wash sale (SOL) ===
        {"date": "2025-01-10", "action": "buy",  "token": "SOL",  "qty": 10,    "price": 200.00},
        {"date": "2025-02-05", "action": "sell", "token": "SOL",  "qty": 10,    "price": 150.00},
        {"date": "2025-02-20", "action": "buy",  "token": "SOL",  "qty": 10,    "price": 160.00},

        # === Scenario 2: No wash sale — waited > 30 days (ETH) ===
        {"date": "2025-01-15", "action": "buy",  "token": "ETH",  "qty": 2,     "price": 3200.00},
        {"date": "2025-02-10", "action": "sell", "token": "ETH",  "qty": 2,     "price": 2800.00},
        {"date": "2025-03-20", "action": "buy",  "token": "ETH",  "qty": 2,     "price": 2900.00},

        # === Scenario 3: Partial match (BONK) ===
        {"date": "2025-02-01", "action": "buy",  "token": "BONK", "qty": 1000000, "price": 0.00003},
        {"date": "2025-03-01", "action": "sell", "token": "BONK", "qty": 1000000, "price": 0.00002},
        {"date": "2025-03-15", "action": "buy",  "token": "BONK", "qty": 400000,  "price": 0.000022},

        # === Scenario 4: Pre-sale window trigger (JUP) ===
        {"date": "2025-01-05", "action": "buy",  "token": "JUP",  "qty": 500,   "price": 1.20},
        {"date": "2025-02-01", "action": "buy",  "token": "JUP",  "qty": 200,   "price": 0.90},
        {"date": "2025-02-15", "action": "sell", "token": "JUP",  "qty": 500,   "price": 0.85},

        # === Scenario 5: Chained wash sales (RAY) ===
        {"date": "2025-01-20", "action": "buy",  "token": "RAY",  "qty": 100,   "price": 5.00},
        {"date": "2025-02-10", "action": "sell", "token": "RAY",  "qty": 100,   "price": 4.00},
        {"date": "2025-02-25", "action": "buy",  "token": "RAY",  "qty": 100,   "price": 4.20},
        {"date": "2025-03-15", "action": "sell", "token": "RAY",  "qty": 100,   "price": 3.80},
        {"date": "2025-03-28", "action": "buy",  "token": "RAY",  "qty": 100,   "price": 3.90},
    ]


# ── Report Formatting ──────────────────────────────────────────────

def print_report(results: ScanResults) -> None:
    """Print a formatted wash sale report to stdout."""
    sep = "=" * 78

    print()
    print(sep)
    print("  WASH SALE DETECTION REPORT")
    print(sep)

    # Trade summary
    print(f"\n  Total trades analyzed: {len(results.trades)}")
    tokens = sorted({t.token for t in results.trades})
    print(f"  Tokens: {', '.join(tokens)}")

    # All trades
    print(f"\n{'─' * 78}")
    print("  TRADE HISTORY")
    print(f"{'─' * 78}")
    for trade in results.trades:
        print(f"  {trade}")

    # Wash sales
    print(f"\n{'─' * 78}")
    print("  WASH SALES DETECTED")
    print(f"{'─' * 78}")
    if results.wash_sales:
        for i, ws in enumerate(results.wash_sales, 1):
            print(f"\n  #{i}")
            print(ws)
    else:
        print("  None detected.")

    # Summary
    print(f"\n{'─' * 78}")
    print("  LOSS SUMMARY")
    print(f"{'─' * 78}")
    print(f"  Total realized losses:   ${results.total_realized_losses:>12.2f}")
    print(f"  Disallowed (wash sale):  ${results.total_disallowed:>12.2f}")
    print(f"  Deductible:              ${results.total_deductible:>12.2f}")

    # Countdowns
    print(f"\n{'─' * 78}")
    print("  SAFE RE-ENTRY COUNTDOWNS")
    print(f"{'─' * 78}")
    if results.countdowns:
        for cd in results.countdowns:
            print(cd)
    else:
        print("  No active loss windows.")

    # Disclaimer
    print(f"\n{'─' * 78}")
    print("  DISCLAIMER: This report is for informational purposes only.")
    print("  It does NOT constitute tax advice. Consult a qualified tax")
    print("  professional for guidance on your specific tax situation.")
    print(sep)
    print()


# ── CLI ─────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Wash sale scanner for cryptocurrency trades (2025 US rules)",
        epilog="DISCLAIMER: Not tax advice. Consult a qualified tax professional.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with built-in demo trade data showing wash sale scenarios",
    )
    parser.add_argument(
        "--csv",
        type=str,
        help="Path to CSV file with columns: date, action, token, qty, price",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Date for countdown calculations (YYYY-MM-DD, default: today)",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the wash sale scanner CLI."""
    args = parse_args()

    if not args.demo and not args.csv:
        print("Error: Specify --demo or --csv <file>")
        print("Run with --help for usage information.")
        sys.exit(1)

    as_of: Optional[date] = None
    if args.as_of:
        try:
            as_of = date.fromisoformat(args.as_of)
        except ValueError:
            print(f"Error: Invalid date format: {args.as_of} (expected YYYY-MM-DD)")
            sys.exit(1)

    if args.demo:
        trades = get_demo_trades()
        # Use a fixed date for demo so output is deterministic
        if as_of is None:
            as_of = date(2025, 4, 15)
    else:
        trades = load_trades_from_csv(args.csv)

    scanner = WashSaleScanner(trades, as_of=as_of)
    results = scanner.scan()
    print_report(results)


if __name__ == "__main__":
    main()
