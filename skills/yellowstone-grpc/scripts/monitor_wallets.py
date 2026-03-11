#!/usr/bin/env python3
"""Monitor specific Solana wallets for on-chain activity via Yellowstone gRPC.

Watches a list of wallet addresses for any transaction activity, parses the
transactions to identify what programs were called and what token balances
changed, and logs the activity with timestamps.

Useful for: copy trading signal generation, whale watching, wallet profiling.

Usage:
    python scripts/monitor_wallets.py

    # Watch specific wallets (comma-separated)
    WATCH_WALLETS="addr1,addr2,addr3" python scripts/monitor_wallets.py

Dependencies:
    uv pip install grpcio grpcio-tools protobuf base58 python-dotenv

Environment Variables:
    GRPC_ENDPOINT: Your Yellowstone gRPC endpoint (e.g., https://grpc.ny.shyft.to)
    GRPC_TOKEN: Your x-token for authentication
    WATCH_WALLETS: Comma-separated list of wallet addresses to monitor

Setup:
    Generate protobuf stubs first (see subscribe_transactions.py for instructions).
"""

import os
import sys
import time
import json
import queue
import threading
from datetime import datetime, timezone
from typing import Optional

import base58
import grpc

# ── Configuration ───────────────────────────────────────────────────

GRPC_ENDPOINT = os.getenv("GRPC_ENDPOINT", "")
GRPC_TOKEN = os.getenv("GRPC_TOKEN", "")

if not GRPC_ENDPOINT or not GRPC_TOKEN:
    print("Set GRPC_ENDPOINT and GRPC_TOKEN environment variables")
    sys.exit(1)

# Wallets to watch — comma-separated in env var, or hardcode for testing
WATCH_WALLETS_STR = os.getenv("WATCH_WALLETS", "")
if not WATCH_WALLETS_STR:
    print("Set WATCH_WALLETS environment variable (comma-separated addresses)")
    print("  export WATCH_WALLETS='addr1,addr2,addr3'")
    sys.exit(1)

WATCH_WALLETS = [w.strip() for w in WATCH_WALLETS_STR.split(",") if w.strip()]
if not WATCH_WALLETS:
    print("No valid wallet addresses found in WATCH_WALLETS")
    sys.exit(1)

MAX_RECONNECT_DELAY = 60.0
MAX_QUEUE_SIZE = 10_000

# Known program labels for readable output
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
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "ATA",
}

# ── gRPC Setup ──────────────────────────────────────────────────────


def create_channel(endpoint: str, token: str) -> grpc.Channel:
    """Create an authenticated TLS gRPC channel."""
    clean_endpoint = endpoint.replace("https://", "").replace("http://", "")
    auth_creds = grpc.metadata_call_credentials(
        lambda ctx, cb: cb((("x-token", token),), None)
    )
    return grpc.secure_channel(
        clean_endpoint,
        grpc.composite_channel_credentials(grpc.ssl_channel_credentials(), auth_creds),
        options=[("grpc.max_receive_message_length", 64 * 1024 * 1024)],
    )


try:
    from generated import geyser_pb2, geyser_pb2_grpc  # type: ignore
except ImportError:
    print("ERROR: Generated protobuf stubs not found.")
    print("See subscribe_transactions.py for setup instructions.")
    sys.exit(1)


# ── Wallet Activity Parsing ────────────────────────────────────────


def identify_programs(tx_info) -> list[str]:
    """Identify which known programs a transaction interacted with.

    Args:
        tx_info: SubscribeUpdateTransactionInfo protobuf.

    Returns:
        List of program labels (e.g., ["PumpFun", "Token"]).
    """
    msg = tx_info.transaction.message
    account_keys = [base58.b58encode(k).decode() for k in msg.account_keys]

    programs = set()
    for ix in msg.instructions:
        program_id = account_keys[ix.program_id_index]
        label = KNOWN_PROGRAMS.get(program_id, None)
        if label and label not in ("System", "ComputeBudget", "Token", "ATA"):
            programs.add(label)

    # Also check inner instructions (CPI calls)
    for inner in tx_info.meta.inner_instructions:
        for ix in inner.instructions:
            if ix.program_id_index < len(account_keys):
                program_id = account_keys[ix.program_id_index]
                label = KNOWN_PROGRAMS.get(program_id, None)
                if label and label not in ("System", "ComputeBudget", "Token", "ATA"):
                    programs.add(label)

    return sorted(programs) if programs else ["Unknown"]


def extract_sol_change(tx_info, wallet: str) -> float:
    """Calculate SOL balance change for a specific wallet.

    Args:
        tx_info: SubscribeUpdateTransactionInfo protobuf.
        wallet: Base58 wallet address.

    Returns:
        SOL change in lamports (positive = received, negative = spent).
    """
    msg = tx_info.transaction.message
    account_keys = [base58.b58encode(k).decode() for k in msg.account_keys]

    try:
        idx = account_keys.index(wallet)
    except ValueError:
        return 0.0

    pre = tx_info.meta.pre_balances[idx] if idx < len(tx_info.meta.pre_balances) else 0
    post = tx_info.meta.post_balances[idx] if idx < len(tx_info.meta.post_balances) else 0
    return (post - pre) / 1e9  # Convert lamports to SOL


def extract_token_changes(tx_info, wallet: str) -> list[dict]:
    """Extract token balance changes for a specific wallet.

    Args:
        tx_info: SubscribeUpdateTransactionInfo protobuf.
        wallet: Base58 wallet address.

    Returns:
        List of dicts with mint, delta, and post_amount for each changed token.
    """
    changes = []
    pre_map = {}
    for tb in tx_info.meta.pre_token_balances:
        if tb.owner == wallet:
            pre_map[tb.mint] = float(tb.ui_token_amount.ui_amount)

    for tb in tx_info.meta.post_token_balances:
        if tb.owner == wallet:
            post_amount = float(tb.ui_token_amount.ui_amount)
            pre_amount = pre_map.get(tb.mint, 0.0)
            delta = post_amount - pre_amount
            if abs(delta) > 0:
                changes.append({
                    "mint": tb.mint,
                    "delta": delta,
                    "post_amount": post_amount,
                })

    return changes


def parse_wallet_activity(tx_update, wallets: list[str]) -> Optional[dict]:
    """Parse a transaction update for wallet-relevant activity.

    Args:
        tx_update: SubscribeUpdateTransaction protobuf.
        wallets: List of watched wallet addresses.

    Returns:
        Activity dict if a watched wallet was involved, None otherwise.
    """
    info = tx_update.transaction
    sig = base58.b58encode(info.signature).decode()
    slot = tx_update.slot

    msg = info.transaction.message
    account_keys = [base58.b58encode(k).decode() for k in msg.account_keys]

    # Find which watched wallets are involved
    involved = [w for w in wallets if w in account_keys]
    if not involved:
        return None

    # Is this wallet the signer (initiator)?
    signer = account_keys[0] if account_keys else None

    programs = identify_programs(info)

    activity = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signature": sig,
        "slot": slot,
        "programs": programs,
        "wallets": [],
    }

    for wallet in involved:
        sol_change = extract_sol_change(info, wallet)
        token_changes = extract_token_changes(info, wallet)
        is_signer = wallet == signer

        activity["wallets"].append({
            "address": wallet,
            "is_signer": is_signer,
            "sol_change": sol_change,
            "token_changes": token_changes,
        })

    return activity


# ── Streaming ───────────────────────────────────────────────────────


def stream_wallet_activity(
    endpoint: str,
    token: str,
    wallets: list[str],
    msg_queue: queue.Queue,
) -> None:
    """Stream transactions for watched wallets with reconnection."""
    delay = 0.1
    last_slot: Optional[int] = None

    while True:
        try:
            channel = create_channel(endpoint, token)
            stub = geyser_pb2_grpc.GeyserStub(channel)

            request = geyser_pb2.SubscribeRequest(
                transactions={
                    "wallets": geyser_pb2.SubscribeRequestFilterTransactions(
                        account_include=wallets,
                        vote=False,
                        failed=False,
                    )
                },
                commitment=geyser_pb2.CommitmentLevel.CONFIRMED,
            )
            if last_slot:
                request.from_slot = last_slot - 32

            print(f"Connecting to {endpoint}...")
            stream = stub.Subscribe(iter([request]))
            delay = 0.1
            print(f"Monitoring {len(wallets)} wallets...\n")

            for update in stream:
                if update.HasField("transaction"):
                    last_slot = update.transaction.slot
                    try:
                        msg_queue.put_nowait(update.transaction)
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


# ── Main ────────────────────────────────────────────────────────────


def format_activity(activity: dict) -> str:
    """Format a wallet activity event for display.

    Args:
        activity: Parsed activity dict from parse_wallet_activity.

    Returns:
        Formatted string for terminal output.
    """
    lines = []
    ts = activity["timestamp"][:19]
    programs = ", ".join(activity["programs"])
    sig = activity["signature"][:20]
    lines.append(f"[{ts}] {sig}... | {programs}")

    for w in activity["wallets"]:
        addr = w["address"][:12] + "..."
        role = "SIGNER" if w["is_signer"] else "participant"
        sol = w["sol_change"]
        sol_str = f"{sol:+.6f} SOL" if abs(sol) > 0.000001 else ""
        lines.append(f"  {addr} ({role}) {sol_str}")

        for tc in w["token_changes"]:
            mint = tc["mint"][:12] + "..."
            lines.append(f"    Token {mint}: {tc['delta']:+.6f}")

    return "\n".join(lines)


def main() -> None:
    """Entry point: monitor wallets and print activity."""
    print(f"Wallet Monitor — watching {len(WATCH_WALLETS)} addresses")
    for w in WATCH_WALLETS:
        print(f"  {w}")
    print()

    msg_queue: queue.Queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
    seen_sigs: set = set()
    event_count = 0

    reader = threading.Thread(
        target=stream_wallet_activity,
        args=(GRPC_ENDPOINT, GRPC_TOKEN, WATCH_WALLETS, msg_queue),
        daemon=True,
    )
    reader.start()

    try:
        while True:
            try:
                tx_update = msg_queue.get(timeout=60.0)
            except queue.Empty:
                print(f"[{datetime.now(timezone.utc).isoformat()[:19]}] No activity (60s)")
                continue

            activity = parse_wallet_activity(tx_update, WATCH_WALLETS)
            if not activity:
                continue

            if activity["signature"] in seen_sigs:
                continue
            seen_sigs.add(activity["signature"])
            if len(seen_sigs) > 50_000:
                seen_sigs.clear()

            event_count += 1
            print(format_activity(activity))
            print()

    except KeyboardInterrupt:
        print(f"\nMonitored {event_count} events. Shutting down.")


if __name__ == "__main__":
    main()
