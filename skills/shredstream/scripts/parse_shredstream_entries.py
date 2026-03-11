#!/usr/bin/env python3
"""Parse and analyze entries from Jito ShredStream gRPC proxy.

Connects to a locally-running ShredStream proxy's gRPC endpoint, receives
decoded entries containing pre-execution transactions, and prints analysis
including program identification, signer detection, and transaction counts.

This demonstrates how to consume ShredStream data for early signal detection.

Usage:
    python scripts/parse_shredstream_entries.py

Dependencies:
    uv pip install grpcio grpcio-tools protobuf base58 solders

Environment Variables:
    SHREDSTREAM_GRPC_URL: ShredStream proxy gRPC endpoint (default: localhost:7777)

Setup:
    1. Run jito-shredstream-proxy with --grpc-service-port 7777
    2. Generate Python stubs from jito-labs/mev-protos:
       git clone https://github.com/jito-labs/mev-protos.git
       python -m grpc_tools.protoc \\
         -I./mev-protos/ \\
         --python_out=./generated \\
         --pyi_out=./generated \\
         --grpc_python_out=./generated \\
         ./mev-protos/shredstream.proto ./mev-protos/shared.proto

    Note: If you don't have a ShredStream proxy running, this script will
    demonstrate the parsing logic with mock data when run with --demo flag.
"""

import os
import sys
import time
import struct
from typing import Optional
from dataclasses import dataclass, field

import base58

# ── Configuration ───────────────────────────────────────────────────

SHREDSTREAM_URL = os.getenv("SHREDSTREAM_GRPC_URL", "localhost:7777")
DEMO_MODE = "--demo" in sys.argv

# Known Solana program IDs for identification
KNOWN_PROGRAMS = {
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "PumpFun",
    "PSwapMdSai8tjrEXcxFeQth87xC4rRsa4VA5mhGhXkP": "PumpSwap",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium-AMM",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium-CLMM",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "Raydium-CPMM",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora-DLMM",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter-V6",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token",
    "11111111111111111111111111111111": "System",
    "ComputeBudget111111111111111111111111111111": "ComputeBudget",
    "Vote111111111111111111111111111111111111111": "Vote",
}

# Programs we care about for trading signals
TRADING_PROGRAMS = {
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # PumpFun
    "PSwapMdSai8tjrEXcxFeQth87xC4rRsa4VA5mhGhXkP",  # PumpSwap
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",  # Raydium CLMM
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",  # Orca
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",  # Meteora
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",  # Jupiter
}


# ── Data Structures ────────────────────────────────────────────────


@dataclass
class PreExecTransaction:
    """A pre-execution transaction parsed from ShredStream."""

    signature: str
    slot: int
    signer: str
    programs: list[str]
    instruction_count: int
    has_trading_program: bool
    raw_instructions: list[dict] = field(default_factory=list)


@dataclass
class SlotStats:
    """Aggregated stats for a single slot."""

    slot: int
    entry_count: int = 0
    tx_count: int = 0
    trading_tx_count: int = 0
    programs_seen: dict = field(default_factory=dict)
    first_seen: float = 0.0
    last_seen: float = 0.0


# ── Transaction Parsing ────────────────────────────────────────────


def parse_transaction_from_bytes(
    tx_bytes: bytes, slot: int
) -> Optional[PreExecTransaction]:
    """Parse a serialized VersionedTransaction into a PreExecTransaction.

    This is a simplified parser that handles the common case of legacy
    transactions. Full v0 transaction parsing with ALT resolution requires
    the solders library.

    Args:
        tx_bytes: Serialized VersionedTransaction bytes.
        slot: The slot this transaction belongs to.

    Returns:
        Parsed PreExecTransaction, or None if parsing fails.
    """
    try:
        from solders.transaction import VersionedTransaction as SoldersVersionedTx

        tx = SoldersVersionedTx.from_bytes(tx_bytes)
        sig = str(tx.signatures[0])
        msg = tx.message
        account_keys = [str(k) for k in msg.account_keys()]

        programs = []
        instructions = []
        has_trading = False

        for ix in msg.instructions():
            program_id = account_keys[ix.program_id_index]
            label = KNOWN_PROGRAMS.get(program_id, program_id[:12] + "...")
            programs.append(label)

            if program_id in TRADING_PROGRAMS:
                has_trading = True

            disc = ix.data[:8].hex() if len(ix.data) >= 8 else ix.data.hex()
            instructions.append({
                "program": program_id,
                "label": label,
                "discriminator": disc,
                "data_len": len(ix.data),
                "account_count": len(ix.accounts),
            })

        signer = account_keys[0] if account_keys else "unknown"

        return PreExecTransaction(
            signature=sig,
            slot=slot,
            signer=signer,
            programs=list(set(programs)),
            instruction_count=len(instructions),
            has_trading_program=has_trading,
            raw_instructions=instructions,
        )
    except Exception as e:
        return None


def parse_entry_batch(entries_bytes: bytes, slot: int) -> list[PreExecTransaction]:
    """Parse a batch of entries from ShredStream.

    The entries field is bincode-serialized Vec<Entry>. Each Entry contains
    a list of VersionedTransactions. This function uses solders for
    deserialization.

    Args:
        entries_bytes: Raw bytes from the Entry.entries field.
        slot: The slot number for context.

    Returns:
        List of parsed PreExecTransactions.
    """
    try:
        from solders.entry import Entry as SoldersEntry

        entries = SoldersEntry.from_bytes_vec(entries_bytes)
        transactions = []
        for entry in entries:
            for tx in entry.transactions:
                parsed = parse_transaction_from_bytes(bytes(tx), slot)
                if parsed:
                    transactions.append(parsed)
        return transactions
    except ImportError:
        print("WARNING: solders not installed. Install with: uv pip install solders")
        print("Falling back to raw byte analysis.")
        return []
    except Exception as e:
        print(f"Entry parse error: {e}")
        return []


# ── Statistics Tracking ─────────────────────────────────────────────


class StreamAnalyzer:
    """Tracks and reports statistics from the ShredStream."""

    def __init__(self) -> None:
        self.total_entries = 0
        self.total_txs = 0
        self.total_trading_txs = 0
        self.program_counts: dict[str, int] = {}
        self.slots_seen: dict[int, SlotStats] = {}
        self.start_time = time.time()

    def process_slot_entry(
        self, slot: int, transactions: list[PreExecTransaction]
    ) -> SlotStats:
        """Process a batch of transactions from a slot entry.

        Args:
            slot: The slot number.
            transactions: Parsed pre-execution transactions.

        Returns:
            Updated SlotStats for this slot.
        """
        now = time.time()

        if slot not in self.slots_seen:
            self.slots_seen[slot] = SlotStats(slot=slot, first_seen=now)

        stats = self.slots_seen[slot]
        stats.entry_count += 1
        stats.last_seen = now

        for tx in transactions:
            stats.tx_count += 1
            self.total_txs += 1

            if tx.has_trading_program:
                stats.trading_tx_count += 1
                self.total_trading_txs += 1

            for prog in tx.programs:
                self.program_counts[prog] = self.program_counts.get(prog, 0) + 1
                stats.programs_seen[prog] = stats.programs_seen.get(prog, 0) + 1

        self.total_entries += 1

        # Prune old slots (keep last 100)
        if len(self.slots_seen) > 100:
            oldest = sorted(self.slots_seen.keys())[:-100]
            for s in oldest:
                del self.slots_seen[s]

        return stats

    def summary(self) -> str:
        """Generate a summary of stream statistics."""
        elapsed = time.time() - self.start_time
        tps = self.total_txs / elapsed if elapsed > 0 else 0
        trading_pct = (
            self.total_trading_txs / self.total_txs * 100
            if self.total_txs > 0
            else 0
        )

        lines = [
            f"\n{'='*60}",
            f"ShredStream Analysis Summary",
            f"{'='*60}",
            f"Duration:     {elapsed:.1f}s",
            f"Entries:      {self.total_entries}",
            f"Transactions: {self.total_txs} ({tps:.1f}/s)",
            f"Trading TXs:  {self.total_trading_txs} ({trading_pct:.1f}%)",
            f"Slots seen:   {len(self.slots_seen)}",
            f"\nTop Programs:",
        ]
        for prog, count in sorted(
            self.program_counts.items(), key=lambda x: -x[1]
        )[:10]:
            lines.append(f"  {prog}: {count}")

        return "\n".join(lines)


# ── Demo Mode ───────────────────────────────────────────────────────


def run_demo() -> None:
    """Run a demonstration with synthetic data to show parsing logic."""
    print("Running in DEMO mode (no live ShredStream connection)")
    print("This demonstrates the parsing and analysis logic.\n")

    analyzer = StreamAnalyzer()

    # Simulate some pre-execution transactions
    demo_txs = [
        PreExecTransaction(
            signature="5wHu1" + "A" * 83,
            slot=300_000_000,
            signer="Whale1" + "1" * 38,
            programs=["PumpFun", "Token", "System"],
            instruction_count=4,
            has_trading_program=True,
        ),
        PreExecTransaction(
            signature="3kXp2" + "B" * 83,
            slot=300_000_000,
            signer="Trader" + "2" * 38,
            programs=["Jupiter-V6", "Raydium-AMM", "Token"],
            instruction_count=7,
            has_trading_program=True,
        ),
        PreExecTransaction(
            signature="7mNq4" + "C" * 83,
            slot=300_000_000,
            signer="User33" + "3" * 38,
            programs=["System"],
            instruction_count=1,
            has_trading_program=False,
        ),
    ]

    stats = analyzer.process_slot_entry(300_000_000, demo_txs)

    print(f"Slot {stats.slot}: {stats.tx_count} txs, {stats.trading_tx_count} trading")
    for tx in demo_txs:
        marker = " [TRADE]" if tx.has_trading_program else ""
        print(f"  {tx.signature[:12]}... | {tx.signer[:12]}... | {', '.join(tx.programs)}{marker}")

    print(analyzer.summary())
    print("\nTo run against a live ShredStream proxy:")
    print("  1. Start jito-shredstream-proxy with --grpc-service-port 7777")
    print("  2. Run this script without --demo flag")


# ── Live Mode ───────────────────────────────────────────────────────


def run_live() -> None:
    """Connect to ShredStream proxy and process live entries."""
    try:
        import grpc
        from generated import shredstream_pb2, shredstream_pb2_grpc  # type: ignore
    except ImportError:
        print("ERROR: Generated protobuf stubs not found.")
        print("Generate from jito-labs/mev-protos (see docstring for instructions).")
        print("\nOr run with --demo flag to see parsing logic without live data.")
        sys.exit(1)

    print(f"Connecting to ShredStream proxy at {SHREDSTREAM_URL}...")
    channel = grpc.insecure_channel(
        SHREDSTREAM_URL,
        options=[("grpc.max_receive_message_length", 64 * 1024 * 1024)],
    )
    stub = shredstream_pb2_grpc.ShredstreamProxyStub(channel)

    analyzer = StreamAnalyzer()
    entry_count = 0

    try:
        request = shredstream_pb2.SubscribeEntriesRequest()
        stream = stub.SubscribeEntries(request)
        print("Connected. Receiving entries...\n")

        for entry_msg in stream:
            slot = entry_msg.slot
            transactions = parse_entry_batch(entry_msg.entries, slot)
            stats = analyzer.process_slot_entry(slot, transactions)

            # Print trading transactions immediately
            for tx in transactions:
                if tx.has_trading_program:
                    programs = ", ".join(tx.programs)
                    print(
                        f"[{slot}] {tx.signature[:16]}... "
                        f"| {tx.signer[:12]}... "
                        f"| {programs}"
                    )

            entry_count += 1
            if entry_count % 1000 == 0:
                elapsed = time.time() - analyzer.start_time
                print(
                    f"\n--- {entry_count} entries, "
                    f"{analyzer.total_txs} txs, "
                    f"{analyzer.total_trading_txs} trading, "
                    f"{elapsed:.0f}s ---\n"
                )

    except grpc.RpcError as e:
        print(f"\ngRPC error: {e}")
    except KeyboardInterrupt:
        pass
    finally:
        print(analyzer.summary())


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if DEMO_MODE:
        run_demo()
    else:
        run_live()
