#!/usr/bin/env python3
"""Monitor pre-execution transactions via Shyft RabbitStream.

RabbitStream uses the same Yellowstone gRPC protocol but delivers transactions
from the shred level — before execution. This script connects to RabbitStream,
filters for DEX-related transactions, and prints early trading signals.

The key advantage: same code as standard Yellowstone gRPC, just a different
endpoint. No infrastructure to run.

Usage:
    python scripts/rabbitstream_monitor.py

Dependencies:
    uv pip install grpcio grpcio-tools protobuf base58 python-dotenv

Environment Variables:
    RABBITSTREAM_ENDPOINT: RabbitStream endpoint (default: rabbitstream.ny.shyft.to)
    GRPC_TOKEN: Your Shyft x-token (same token as regular gRPC)
    TARGET_PROGRAMS: Comma-separated program IDs to filter (optional)

Setup:
    Generate Yellowstone protobuf stubs first (same as yellowstone-grpc skill):

    git clone https://github.com/rpcpool/yellowstone-grpc.git
    python -m grpc_tools.protoc \\
      -I./yellowstone-grpc/yellowstone-grpc-proto/proto/ \\
      --python_out=./generated \\
      --pyi_out=./generated \\
      --grpc_python_out=./generated \\
      ./yellowstone-grpc/yellowstone-grpc-proto/proto/*.proto
"""

import os
import sys
import time
import queue
import threading
from datetime import datetime, timezone
from typing import Optional

import base58
import grpc

# ── Configuration ───────────────────────────────────────────────────

RABBITSTREAM_ENDPOINT = os.getenv(
    "RABBITSTREAM_ENDPOINT", "rabbitstream.ny.shyft.to"
)
GRPC_TOKEN = os.getenv("GRPC_TOKEN", "")

if not GRPC_TOKEN:
    print("Set GRPC_TOKEN environment variable (your Shyft x-token)")
    print("  export GRPC_TOKEN='your-shyft-x-token'")
    sys.exit(1)

# Default: watch PumpFun. Override with TARGET_PROGRAMS env var.
DEFAULT_PROGRAMS = [
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # PumpFun
]

TARGET_PROGRAMS_STR = os.getenv("TARGET_PROGRAMS", "")
TARGET_PROGRAMS = (
    [p.strip() for p in TARGET_PROGRAMS_STR.split(",") if p.strip()]
    if TARGET_PROGRAMS_STR
    else DEFAULT_PROGRAMS
)

MAX_QUEUE_SIZE = 10_000
MAX_RECONNECT_DELAY = 60.0

# Program labels for display
PROGRAM_LABELS = {
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "PumpFun",
    "PSwapMdSai8tjrEXcxFeQth87xC4rRsa4VA5mhGhXkP": "PumpSwap",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium-AMM",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium-CLMM",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "Raydium-CPMM",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora-DLMM",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter-V6",
}

# ── Stub Import ─────────────────────────────────────────────────────

try:
    from generated import geyser_pb2, geyser_pb2_grpc  # type: ignore
except ImportError:
    print("ERROR: Yellowstone protobuf stubs not found.")
    print("Generate them first (see docstring for instructions).")
    sys.exit(1)


# ── Connection ──────────────────────────────────────────────────────


def create_channel(endpoint: str, token: str) -> grpc.Channel:
    """Create authenticated TLS channel for RabbitStream.

    Args:
        endpoint: RabbitStream endpoint (without https://).
        token: Shyft x-token.

    Returns:
        Configured gRPC channel.
    """
    clean = endpoint.replace("https://", "").replace("http://", "")
    auth = grpc.metadata_call_credentials(
        lambda ctx, cb: cb((("x-token", token),), None)
    )
    return grpc.secure_channel(
        clean,
        grpc.composite_channel_credentials(grpc.ssl_channel_credentials(), auth),
        options=[("grpc.max_receive_message_length", 64 * 1024 * 1024)],
    )


# ── Transaction Parsing (Pre-Execution) ────────────────────────────


def parse_pre_exec_tx(tx_update) -> Optional[dict]:
    """Parse a RabbitStream transaction update.

    RabbitStream transactions have the same structure as Yellowstone, but the
    meta field is empty (no execution results). We extract what's available:
    signature, signer, programs called, and instruction discriminators.

    Args:
        tx_update: SubscribeUpdateTransaction from RabbitStream.

    Returns:
        Dict with pre-execution transaction details, or None on error.
    """
    try:
        info = tx_update.transaction
        sig = base58.b58encode(info.signature).decode()
        slot = tx_update.slot

        msg = info.transaction.message
        account_keys = [base58.b58encode(k).decode() for k in msg.account_keys]
        signer = account_keys[0] if account_keys else "unknown"

        programs_called = []
        instructions = []

        for ix in msg.instructions:
            program_id = account_keys[ix.program_id_index]
            label = PROGRAM_LABELS.get(program_id, program_id[:12] + "...")
            programs_called.append(label)

            disc = ix.data[:8].hex() if len(ix.data) >= 8 else ix.data.hex()
            instructions.append({
                "program": program_id,
                "label": label,
                "discriminator": disc,
                "data_len": len(ix.data),
                "num_accounts": len(ix.accounts),
            })

        # Note: meta fields are empty for pre-execution data
        # No balance changes, no logs, no inner instructions

        return {
            "signature": sig,
            "slot": slot,
            "signer": signer,
            "programs": list(dict.fromkeys(programs_called)),  # deduplicate
            "instructions": instructions,
            "is_pre_execution": True,
            "received_at": time.time(),
        }
    except Exception as e:
        return None


# ── Streaming ───────────────────────────────────────────────────────


def stream_rabbitstream(
    endpoint: str,
    token: str,
    programs: list[str],
    msg_queue: queue.Queue,
) -> None:
    """Stream pre-execution transactions from RabbitStream.

    Args:
        endpoint: RabbitStream endpoint.
        token: Shyft x-token.
        programs: Program IDs to filter.
        msg_queue: Queue for parsed transaction dicts.
    """
    delay = 0.1
    last_slot: Optional[int] = None

    while True:
        try:
            channel = create_channel(endpoint, token)
            stub = geyser_pb2_grpc.GeyserStub(channel)

            # Same subscription format as Yellowstone — that's the beauty
            request = geyser_pb2.SubscribeRequest(
                transactions={
                    "target": geyser_pb2.SubscribeRequestFilterTransactions(
                        account_include=programs,
                        vote=False,
                        failed=False,
                    )
                },
                commitment=geyser_pb2.CommitmentLevel.PROCESSED,
            )
            if last_slot:
                request.from_slot = last_slot - 32

            labels = [PROGRAM_LABELS.get(p, p[:12]) for p in programs]
            print(f"Connecting to RabbitStream ({endpoint})...")
            print(f"Filtering: {', '.join(labels)}")

            stream = stub.Subscribe(iter([request]))
            delay = 0.1
            print("Connected. Streaming pre-execution transactions...\n")

            for update in stream:
                if update.HasField("transaction"):
                    last_slot = update.transaction.slot
                    parsed = parse_pre_exec_tx(update.transaction)
                    if parsed:
                        try:
                            msg_queue.put_nowait(parsed)
                        except queue.Full:
                            pass

        except grpc.RpcError as e:
            status = e.code() if hasattr(e, "code") else "UNKNOWN"
            print(f"\nDisconnected: {status}. Reconnecting in {delay:.1f}s...")
            time.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY)

        except KeyboardInterrupt:
            return

        except Exception as e:
            print(f"\nError: {e}. Reconnecting in {delay:.1f}s...")
            time.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY)


# ── Display ─────────────────────────────────────────────────────────


def format_pre_exec_signal(tx: dict) -> str:
    """Format a pre-execution transaction as a readable signal.

    Args:
        tx: Parsed transaction dict from parse_pre_exec_tx.

    Returns:
        Formatted string for terminal display.
    """
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
    sig = tx["signature"][:16]
    signer = tx["signer"][:12]
    programs = ", ".join(p for p in tx["programs"]
                        if p not in ("System", "ComputeBudget", "Token", "ATA"))

    lines = [f"[{ts}] PRE-EXEC | Slot {tx['slot']} | {sig}..."]
    lines.append(f"  Signer: {signer}... | Programs: {programs}")

    # Show instruction details for trading programs
    for ix in tx["instructions"]:
        if ix["program"] in PROGRAM_LABELS:
            lines.append(
                f"  -> {ix['label']}: disc={ix['discriminator']} "
                f"({ix['data_len']}B, {ix['num_accounts']} accounts)"
            )

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point: stream pre-execution transactions and display signals."""
    print("=" * 60)
    print("RabbitStream Pre-Execution Monitor")
    print("=" * 60)
    print(f"Endpoint: {RABBITSTREAM_ENDPOINT}")
    print(f"Programs: {len(TARGET_PROGRAMS)}")
    for p in TARGET_PROGRAMS:
        label = PROGRAM_LABELS.get(p, "Unknown")
        print(f"  {label}: {p}")
    print()
    print("NOTE: These are PRE-EXECUTION signals. Transactions may")
    print("ultimately fail. Use Yellowstone gRPC for confirmation.")
    print("=" * 60)
    print()

    msg_queue: queue.Queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
    seen: set = set()
    count = 0
    start = time.time()

    reader = threading.Thread(
        target=stream_rabbitstream,
        args=(RABBITSTREAM_ENDPOINT, GRPC_TOKEN, TARGET_PROGRAMS, msg_queue),
        daemon=True,
    )
    reader.start()

    try:
        while True:
            try:
                tx = msg_queue.get(timeout=30.0)
            except queue.Empty:
                elapsed = time.time() - start
                print(f"[{elapsed:.0f}s] No signals in 30s. Total: {count}")
                continue

            if tx["signature"] in seen:
                continue
            seen.add(tx["signature"])
            if len(seen) > 50_000:
                seen.clear()

            count += 1
            print(format_pre_exec_signal(tx))
            print()

    except KeyboardInterrupt:
        elapsed = time.time() - start
        rate = count / elapsed if elapsed > 0 else 0
        print(f"\n{count} pre-execution signals in {elapsed:.1f}s ({rate:.1f}/s)")


if __name__ == "__main__":
    main()
