#!/usr/bin/env python3
"""Crypto tax export demo: generate sample trades and export to multiple CSV formats.

Demonstrates exporting trade history to Koinly CSV and IRS Form 8949 CSV formats.
Includes sample Solana transaction types: swaps, staking rewards, airdrops,
LP operations, and failed transactions.

Usage:
    python scripts/tax_exporter.py --demo
    python scripts/tax_exporter.py --demo --format koinly
    python scripts/tax_exporter.py --demo --format form8949
    python scripts/tax_exporter.py --demo --format all

Dependencies:
    None (uses Python stdlib only: csv, json, datetime, argparse)

Environment Variables:
    None required for demo mode.
"""

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from io import StringIO
from typing import Optional


# ── Enums & Data Models ─────────────────────────────────────────────


class TxType(Enum):
    """Solana transaction type classification for tax purposes."""
    SWAP = "swap"
    STAKING_REWARD = "staking"
    AIRDROP = "airdrop"
    LP_DEPOSIT = "liquidity_in"
    LP_WITHDRAWAL = "liquidity_out"
    MIGRATION = "migration"
    FAILED = "failed"


class CostBasisMethod(Enum):
    """Supported cost basis calculation methods."""
    FIFO = "fifo"
    LIFO = "lifo"
    HIFO = "hifo"
    SPEC_ID = "spec_id"


@dataclass
class TaxableEvent:
    """A single taxable event derived from a trade or transaction.

    Attributes:
        timestamp: When the event occurred (UTC).
        tx_type: Classification of the transaction.
        sent_amount: Quantity of asset sent (0 for income events).
        sent_currency: Ticker of asset sent.
        received_amount: Quantity of asset received (0 for disposal-only).
        received_currency: Ticker of asset received.
        fee_amount: Transaction fee amount.
        fee_currency: Transaction fee currency.
        usd_proceeds: USD value of the disposal side.
        usd_cost_basis: USD cost basis of the asset disposed.
        date_acquired: When the disposed asset was originally acquired.
        tx_hash: On-chain transaction signature.
        exchange: Source platform or wallet label.
        description: Human-readable note.
        is_failed: Whether the transaction failed on-chain.
    """
    timestamp: datetime
    tx_type: TxType
    sent_amount: float = 0.0
    sent_currency: str = ""
    received_amount: float = 0.0
    received_currency: str = ""
    fee_amount: float = 0.0
    fee_currency: str = "SOL"
    usd_proceeds: float = 0.0
    usd_cost_basis: float = 0.0
    date_acquired: Optional[datetime] = None
    tx_hash: str = ""
    exchange: str = "Jupiter"
    description: str = ""
    is_failed: bool = False

    @property
    def holding_days(self) -> Optional[int]:
        """Number of days the asset was held before disposal."""
        if self.date_acquired is None:
            return None
        return (self.timestamp - self.date_acquired).days

    @property
    def is_long_term(self) -> Optional[bool]:
        """Whether this is a long-term holding (> 365 days)."""
        days = self.holding_days
        if days is None:
            return None
        return days > 365

    @property
    def gain_or_loss(self) -> float:
        """Compute gain or loss (Form 8949 column h)."""
        return self.usd_proceeds - self.usd_cost_basis


# ── Demo Data Generation ────────────────────────────────────────────


def generate_demo_trades() -> list[TaxableEvent]:
    """Generate a realistic set of demo Solana trades for export testing.

    Returns:
        List of TaxableEvent objects covering various transaction types.
    """
    base = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    trades: list[TaxableEvent] = []

    # 1. Buy SOL with USDC (swap)
    trades.append(TaxableEvent(
        timestamp=base,
        tx_type=TxType.SWAP,
        sent_amount=500.00,
        sent_currency="USDC",
        received_amount=3.33,
        received_currency="SOL",
        fee_amount=0.000005,
        fee_currency="SOL",
        usd_proceeds=500.00,
        usd_cost_basis=500.00,
        date_acquired=base,
        tx_hash="4xKm9rTPqGn2b7VfZ8jHdR1nQwEsXpYcLmA3kF5vG6t",
        description="Buy SOL with USDC via Jupiter",
    ))

    # 2. Swap SOL for BONK (short-term, 30 days later)
    t2 = base + timedelta(days=30)
    trades.append(TaxableEvent(
        timestamp=t2,
        tx_type=TxType.SWAP,
        sent_amount=1.0,
        sent_currency="SOL",
        received_amount=1500000,
        received_currency="BONK",
        fee_amount=0.000005,
        fee_currency="SOL",
        usd_proceeds=165.00,
        usd_cost_basis=150.15,
        date_acquired=base,
        tx_hash="5yLn0sUPrHo3c8WgA9kIeS2oRxFtYqDmB4nC6lG7wH8u",
        description="Swap SOL for BONK (multi-hop via USDC)",
    ))

    # 3. Staking reward received
    t3 = base + timedelta(days=45)
    trades.append(TaxableEvent(
        timestamp=t3,
        tx_type=TxType.STAKING_REWARD,
        received_amount=0.05,
        received_currency="SOL",
        usd_proceeds=8.25,
        usd_cost_basis=8.25,
        date_acquired=t3,
        tx_hash="6zMo1tVQsIp4d9XhB0lJfT3pSyGuZrEnC5oD7mH8xI9v",
        exchange="Marinade",
        description="Staking reward from Marinade mSOL",
    ))

    # 4. Airdrop received
    t4 = base + timedelta(days=60)
    trades.append(TaxableEvent(
        timestamp=t4,
        tx_type=TxType.AIRDROP,
        received_amount=1000,
        received_currency="JUP",
        usd_proceeds=850.00,
        usd_cost_basis=850.00,
        date_acquired=t4,
        tx_hash="7aNp2uWRtJq5e0YiC1mKgU4qTzHvAsF0D6pE8nI9yJ0w",
        exchange="Jupiter",
        description="JUP airdrop Season 2",
    ))

    # 5. LP deposit (Raydium SOL-USDC)
    t5 = base + timedelta(days=90)
    trades.append(TaxableEvent(
        timestamp=t5,
        tx_type=TxType.LP_DEPOSIT,
        sent_amount=1.0,
        sent_currency="SOL",
        received_amount=1,
        received_currency="SOL-USDC-LP",
        fee_amount=0.000005,
        fee_currency="SOL",
        usd_proceeds=175.00,
        usd_cost_basis=150.15,
        date_acquired=base,
        tx_hash="8bOq3vXStKr6f1ZjD2nLhV5rUaIwBtG1E7qF9oJ0zK1x",
        exchange="Raydium",
        description="Add liquidity to SOL-USDC pool",
    ))

    # 6. LP withdrawal (120 days after deposit)
    t6 = t5 + timedelta(days=120)
    trades.append(TaxableEvent(
        timestamp=t6,
        tx_type=TxType.LP_WITHDRAWAL,
        sent_amount=1,
        sent_currency="SOL-USDC-LP",
        received_amount=1.05,
        received_currency="SOL",
        fee_amount=0.000005,
        fee_currency="SOL",
        usd_proceeds=199.50,
        usd_cost_basis=175.00,
        date_acquired=t5,
        tx_hash="9cPr4wYTuLs7g2AkE3oMiW6sVbJxCuH2F8rG0pK1aL2y",
        exchange="Raydium",
        description="Remove liquidity from SOL-USDC pool",
    ))

    # 7. Sell BONK for USDC (short-term)
    t7 = base + timedelta(days=180)
    trades.append(TaxableEvent(
        timestamp=t7,
        tx_type=TxType.SWAP,
        sent_amount=1500000,
        sent_currency="BONK",
        received_amount=200.00,
        received_currency="USDC",
        fee_amount=0.000005,
        fee_currency="SOL",
        usd_proceeds=200.00,
        usd_cost_basis=165.00,
        date_acquired=t2,
        tx_hash="0dQs5xZUvMt8h3BlF4pNjX7tWcKyDvI3G9sH1qL2bM3z",
        description="Sell BONK for USDC via Jupiter",
    ))

    # 8. Sell JUP for SOL (long-term, > 365 days after airdrop)
    t8 = t4 + timedelta(days=400)
    trades.append(TaxableEvent(
        timestamp=t8,
        tx_type=TxType.SWAP,
        sent_amount=1000,
        sent_currency="JUP",
        received_amount=5.5,
        received_currency="SOL",
        fee_amount=0.000005,
        fee_currency="SOL",
        usd_proceeds=1100.00,
        usd_cost_basis=850.00,
        date_acquired=t4,
        tx_hash="1eRt6yAVwNu9i4CmG5qOkY8uXdLzEwJ4H0tI2rM3cN4a",
        description="Sell JUP for SOL (long-term holding)",
    ))

    # 9. Failed transaction (not taxable, but fee spent)
    t9 = base + timedelta(days=200)
    trades.append(TaxableEvent(
        timestamp=t9,
        tx_type=TxType.FAILED,
        sent_amount=2.0,
        sent_currency="SOL",
        received_amount=0,
        received_currency="",
        fee_amount=0.000005,
        fee_currency="SOL",
        usd_proceeds=0,
        usd_cost_basis=0,
        tx_hash="2fSu7zBWxOv0j5DnH6rPlZ9vYeMAFxK5I1uJ3sN4dO5b",
        description="Failed swap — slippage exceeded (NOT taxable)",
        is_failed=True,
    ))

    # 10. Token migration (non-taxable)
    t10 = base + timedelta(days=250)
    trades.append(TaxableEvent(
        timestamp=t10,
        tx_type=TxType.MIGRATION,
        sent_amount=100,
        sent_currency="TOKEN_V1",
        received_amount=100,
        received_currency="TOKEN_V2",
        fee_amount=0.000005,
        fee_currency="SOL",
        usd_proceeds=0,
        usd_cost_basis=0,
        date_acquired=base,
        tx_hash="3gTv8aCXyPw1k6EoI7sPmA0wZfNBGyL6J2vK4tO5eP6c",
        description="Token migration v1->v2 (non-taxable, basis carries over)",
        is_failed=False,
    ))

    return trades


# ── Export Functions ─────────────────────────────────────────────────


def _filter_taxable(trades: list[TaxableEvent]) -> list[TaxableEvent]:
    """Exclude failed and migration transactions from taxable output.

    Args:
        trades: All trade events including non-taxable.

    Returns:
        Filtered list containing only taxable events.
    """
    excluded = {TxType.FAILED, TxType.MIGRATION}
    return [t for t in trades if t.tx_type not in excluded]


def _fmt_date_iso(dt: Optional[datetime]) -> str:
    """Format datetime as YYYY-MM-DD HH:MM:SS UTC."""
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_date_us(dt: Optional[datetime]) -> str:
    """Format datetime as MM/DD/YYYY for US tax forms."""
    if dt is None:
        return ""
    return dt.strftime("%m/%d/%Y")


def _fmt_amount(value: float) -> str:
    """Format a numeric amount, returning empty string for zero."""
    if value == 0.0:
        return ""
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _fmt_usd(value: float) -> str:
    """Format a USD amount to 2 decimal places."""
    return f"{value:.2f}"


def export_koinly_csv(
    trades: list[TaxableEvent],
    output_path: Optional[str] = None,
) -> str:
    """Export trades to Koinly universal CSV format.

    Args:
        trades: List of taxable events to export.
        output_path: File path to write CSV. If None, returns CSV string.

    Returns:
        CSV content as a string.
    """
    taxable = _filter_taxable(trades)

    headers = [
        "Date", "Sent Amount", "Sent Currency",
        "Received Amount", "Received Currency",
        "Fee Amount", "Fee Currency",
        "Net Worth Amount", "Net Worth Currency",
        "Label", "Description", "TxHash",
    ]

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)

    for t in taxable:
        label = t.tx_type.value
        net_worth = t.usd_proceeds if t.usd_proceeds > 0 else ""
        net_worth_currency = "USD" if net_worth else ""

        writer.writerow([
            _fmt_date_iso(t.timestamp),
            _fmt_amount(t.sent_amount),
            t.sent_currency,
            _fmt_amount(t.received_amount),
            t.received_currency,
            _fmt_amount(t.fee_amount),
            t.fee_currency,
            net_worth,
            net_worth_currency,
            label,
            t.description,
            t.tx_hash,
        ])

    content = buf.getvalue()

    if output_path:
        with open(output_path, "w", newline="") as f:
            f.write(content)
        print(f"Koinly CSV written to {output_path} ({len(taxable)} events)")

    return content


def export_form_8949_csv(
    trades: list[TaxableEvent],
    output_path: Optional[str] = None,
    cost_basis_method: CostBasisMethod = CostBasisMethod.FIFO,
) -> str:
    """Export trades to IRS Form 8949 CSV format.

    Separates short-term (Part I) and long-term (Part II) disposals.
    Only includes events where an asset was disposed (sent_amount > 0
    and has a cost basis).

    Args:
        trades: List of taxable events to export.
        output_path: File path to write CSV. If None, returns CSV string.
        cost_basis_method: Cost basis method label for reporting.

    Returns:
        CSV content as a string.
    """
    taxable = _filter_taxable(trades)
    # Only disposals with cost basis info qualify for Form 8949
    disposals = [
        t for t in taxable
        if t.sent_amount > 0
        and t.date_acquired is not None
        and t.tx_type == TxType.SWAP
    ]

    headers = [
        "(a) Description of Property",
        "(b) Date Acquired",
        "(c) Date Sold",
        "(d) Proceeds",
        "(e) Cost Basis",
        "(f) Code",
        "(g) Adjustment",
        "(h) Gain or Loss",
        "Holding Period",
        "Check Box",
    ]

    short_term = [t for t in disposals if not t.is_long_term]
    long_term = [t for t in disposals if t.is_long_term]

    buf = StringIO()
    writer = csv.writer(buf)

    # Part I — Short-Term
    writer.writerow(["--- Part I: Short-Term Capital Gains and Losses ---"])
    writer.writerow(headers)
    for t in short_term:
        writer.writerow([
            f"{_fmt_amount(t.sent_amount)} {t.sent_currency}",
            _fmt_date_us(t.date_acquired),
            _fmt_date_us(t.timestamp),
            _fmt_usd(t.usd_proceeds),
            _fmt_usd(t.usd_cost_basis),
            "",
            "0.00",
            _fmt_usd(t.gain_or_loss),
            f"{t.holding_days} days",
            "(B)",
        ])

    writer.writerow([])

    # Part II — Long-Term
    writer.writerow(["--- Part II: Long-Term Capital Gains and Losses ---"])
    writer.writerow(headers)
    for t in long_term:
        writer.writerow([
            f"{_fmt_amount(t.sent_amount)} {t.sent_currency}",
            _fmt_date_us(t.date_acquired),
            _fmt_date_us(t.timestamp),
            _fmt_usd(t.usd_proceeds),
            _fmt_usd(t.usd_cost_basis),
            "",
            "0.00",
            _fmt_usd(t.gain_or_loss),
            f"{t.holding_days} days",
            "(B)",
        ])

    # Summary
    writer.writerow([])
    total_st_gain = sum(t.gain_or_loss for t in short_term)
    total_lt_gain = sum(t.gain_or_loss for t in long_term)
    writer.writerow(["Summary"])
    writer.writerow([f"Short-term transactions: {len(short_term)}"])
    writer.writerow([f"Short-term net gain/loss: ${total_st_gain:.2f}"])
    writer.writerow([f"Long-term transactions: {len(long_term)}"])
    writer.writerow([f"Long-term net gain/loss: ${total_lt_gain:.2f}"])
    writer.writerow([f"Total net gain/loss: ${total_st_gain + total_lt_gain:.2f}"])
    writer.writerow([f"Cost basis method: {cost_basis_method.value.upper()}"])

    content = buf.getvalue()

    if output_path:
        with open(output_path, "w", newline="") as f:
            f.write(content)
        print(f"Form 8949 CSV written to {output_path} "
              f"({len(short_term)} short-term, {len(long_term)} long-term)")

    return content


def export_cointracker_csv(
    trades: list[TaxableEvent],
    output_path: Optional[str] = None,
) -> str:
    """Export trades to CoinTracker CSV format.

    Args:
        trades: List of taxable events to export.
        output_path: File path to write CSV. If None, returns CSV string.

    Returns:
        CSV content as a string.
    """
    taxable = _filter_taxable(trades)

    tag_map = {
        TxType.SWAP: "trade",
        TxType.STAKING_REWARD: "staking_reward",
        TxType.AIRDROP: "airdrop",
        TxType.LP_DEPOSIT: "lp_deposit",
        TxType.LP_WITHDRAWAL: "lp_withdrawal",
    }

    headers = [
        "Date", "Received Quantity", "Received Currency",
        "Sent Quantity", "Sent Currency",
        "Fee Amount", "Fee Currency", "Tag",
    ]

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)

    for t in taxable:
        # CoinTracker uses MM/DD/YYYY HH:MM:SS
        date_str = t.timestamp.strftime("%m/%d/%Y %H:%M:%S")
        writer.writerow([
            date_str,
            _fmt_amount(t.received_amount),
            t.received_currency,
            _fmt_amount(t.sent_amount),
            t.sent_currency,
            _fmt_amount(t.fee_amount),
            t.fee_currency,
            tag_map.get(t.tx_type, "trade"),
        ])

    content = buf.getvalue()

    if output_path:
        with open(output_path, "w", newline="") as f:
            f.write(content)
        print(f"CoinTracker CSV written to {output_path} ({len(taxable)} events)")

    return content


# ── Display & Comparison ────────────────────────────────────────────


def print_format_comparison(trades: list[TaxableEvent]) -> None:
    """Print a side-by-side comparison showing how formats differ.

    Args:
        trades: List of taxable events.
    """
    print("\n" + "=" * 70)
    print("FORMAT COMPARISON — Same trades, different CSV structures")
    print("=" * 70)

    # Show one swap trade in each format
    swap_trades = [t for t in trades if t.tx_type == TxType.SWAP and not t.is_failed]
    if not swap_trades:
        print("No swap trades to compare.")
        return

    sample = swap_trades[0]

    print(f"\nSample trade: {sample.description}")
    print(f"  Sent: {sample.sent_amount} {sample.sent_currency}")
    print(f"  Received: {sample.received_amount} {sample.received_currency}")
    print(f"  Date: {_fmt_date_iso(sample.timestamp)}")

    # Koinly row
    print("\n--- Koinly CSV row ---")
    print("Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"
          "Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,"
          "Label,Description,TxHash")
    print(f"{_fmt_date_iso(sample.timestamp)},{_fmt_amount(sample.sent_amount)},"
          f"{sample.sent_currency},{_fmt_amount(sample.received_amount)},"
          f"{sample.received_currency},{_fmt_amount(sample.fee_amount)},"
          f"{sample.fee_currency},{sample.usd_proceeds},USD,swap,"
          f"{sample.description},{sample.tx_hash}")

    # Form 8949 row
    if sample.date_acquired:
        period = "Short-term" if not sample.is_long_term else "Long-term"
        print(f"\n--- Form 8949 row ({period}) ---")
        print("(a) Description,(b) Acquired,(c) Sold,(d) Proceeds,"
              "(e) Cost Basis,(f) Code,(g) Adjustment,(h) Gain/Loss")
        print(f"{_fmt_amount(sample.sent_amount)} {sample.sent_currency},"
              f"{_fmt_date_us(sample.date_acquired)},"
              f"{_fmt_date_us(sample.timestamp)},"
              f"{_fmt_usd(sample.usd_proceeds)},"
              f"{_fmt_usd(sample.usd_cost_basis)},,0.00,"
              f"{_fmt_usd(sample.gain_or_loss)}")

    # CoinTracker row
    print("\n--- CoinTracker CSV row ---")
    print("Date,Received Quantity,Received Currency,Sent Quantity,"
          "Sent Currency,Fee Amount,Fee Currency,Tag")
    ct_date = sample.timestamp.strftime("%m/%d/%Y %H:%M:%S")
    print(f"{ct_date},{_fmt_amount(sample.received_amount)},"
          f"{sample.received_currency},{_fmt_amount(sample.sent_amount)},"
          f"{sample.sent_currency},{_fmt_amount(sample.fee_amount)},"
          f"{sample.fee_currency},trade")

    print()


def print_summary(trades: list[TaxableEvent]) -> None:
    """Print a summary of all generated trades.

    Args:
        trades: List of taxable events.
    """
    print("\n" + "=" * 70)
    print("TRADE SUMMARY")
    print("=" * 70)

    taxable = _filter_taxable(trades)
    non_taxable = [t for t in trades if t.tx_type in {TxType.FAILED, TxType.MIGRATION}]

    print(f"\nTotal events:     {len(trades)}")
    print(f"Taxable events:   {len(taxable)}")
    print(f"Non-taxable:      {len(non_taxable)}")

    by_type: dict[str, int] = {}
    for t in trades:
        label = t.tx_type.value
        if t.is_failed:
            label = "failed"
        by_type[label] = by_type.get(label, 0) + 1

    print("\nBy type:")
    for tx_type, count in sorted(by_type.items()):
        print(f"  {tx_type:20s} {count}")

    disposals = [
        t for t in taxable
        if t.sent_amount > 0
        and t.date_acquired is not None
        and t.tx_type == TxType.SWAP
    ]

    if disposals:
        short_term = [t for t in disposals if not t.is_long_term]
        long_term = [t for t in disposals if t.is_long_term]
        st_gain = sum(t.gain_or_loss for t in short_term)
        lt_gain = sum(t.gain_or_loss for t in long_term)

        print(f"\nDisposals for Form 8949: {len(disposals)}")
        print(f"  Short-term: {len(short_term)} (net: ${st_gain:.2f})")
        print(f"  Long-term:  {len(long_term)} (net: ${lt_gain:.2f})")
        print(f"  Total net:  ${st_gain + lt_gain:.2f}")

    print()


# ── Main ─────────────────────────────────────────────────────────────


def run_demo(fmt: str = "all") -> None:
    """Run the full demo: generate trades and export to selected formats.

    Args:
        fmt: Export format — "koinly", "form8949", "cointracker", or "all".
    """
    print("Crypto Tax Export — Demo Mode")
    print("=" * 70)
    print("Generating sample Solana trades...\n")

    trades = generate_demo_trades()
    print_summary(trades)

    if fmt in ("koinly", "all"):
        print("-" * 70)
        koinly_csv = export_koinly_csv(trades, "demo_koinly_export.csv")
        print("Preview (first 5 lines):")
        for line in koinly_csv.strip().split("\n")[:5]:
            print(f"  {line[:100]}{'...' if len(line) > 100 else ''}")
        print()

    if fmt in ("form8949", "all"):
        print("-" * 70)
        form_csv = export_form_8949_csv(trades, "demo_form_8949.csv")
        print("Preview (first 12 lines):")
        for line in form_csv.strip().split("\n")[:12]:
            print(f"  {line[:100]}{'...' if len(line) > 100 else ''}")
        print()

    if fmt in ("cointracker", "all"):
        print("-" * 70)
        ct_csv = export_cointracker_csv(trades, "demo_cointracker_export.csv")
        print("Preview (first 5 lines):")
        for line in ct_csv.strip().split("\n")[:5]:
            print(f"  {line[:100]}{'...' if len(line) > 100 else ''}")
        print()

    if fmt == "all":
        print_format_comparison(trades)

    print("=" * 70)
    print("Demo complete. Files written:")
    if fmt in ("koinly", "all"):
        print("  - demo_koinly_export.csv")
    if fmt in ("form8949", "all"):
        print("  - demo_form_8949.csv")
    if fmt in ("cointracker", "all"):
        print("  - demo_cointracker_export.csv")
    print()
    print("NOTE: This is demo data only. Not financial or tax advice.")
    print("Consult a qualified tax professional for your specific situation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crypto Tax Export — generate trade CSVs for tax software",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode with sample Solana trades",
    )
    parser.add_argument(
        "--format",
        choices=["koinly", "form8949", "cointracker", "all"],
        default="all",
        help="Export format (default: all)",
    )

    args = parser.parse_args()

    if not args.demo:
        print("Use --demo to run with sample data.")
        print("Usage: python scripts/tax_exporter.py --demo [--format koinly|form8949|cointracker|all]")
        sys.exit(0)

    run_demo(args.format)
