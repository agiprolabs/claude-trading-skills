#!/usr/bin/env python3
"""Stream and parse Solana transactions in real-time via Yellowstone gRPC.

Connects to a Yellowstone gRPC provider, subscribes to transactions for a
specified program ID (default: PumpFun), and prints parsed transaction data
including signatures, involved accounts, instruction data, and token balance
changes.

Usage:
    python scripts/subscribe_transactions.py

Dependencies:
    uv pip install grpcio grpcio-tools protobuf base58 python-dotenv

Environment Variables:
    GRPC_ENDPOINT: Your Yellowstone gRPC endpoint (e.g., https://grpc.ny.shyft.to)
    GRPC_TOKEN: Your x-token for authentication

Setup:
    Before first run, generate Python stubs from proto files:

    git clone https://github.com/rpcpool/yellowstone-grpc.git
    python -m grpc_tools.protoc \\
      -I./yellowstone-grpc/yellowstone-grpc-proto/proto/ \\
      --python_out=./generated \\
      --pyi_out=./generated \\
      --grpc_python_out=./generated \\
      ./yellowstone-grpc/yellowstone-grpc-proto/proto/*.proto

    Then set PYTHONPATH to include the generated directory, or copy the
    generated files into your project.
"""

import os
import sys
import time
import queue
import threading
from typing import Optional

import base58
import grpc

# ── Configuration ───────────────────────────────────────────────────

GRPC_ENDPOINT = os.getenv("GRPC_ENDPOINT", "")
GRPC_TOKEN = os.getenv("GRPC_TOKEN", "")

if not GRPC_ENDPOINT or not GRPC_TOKEN:
    print("Set GRPC_ENDPOINT and GRPC_TOKEN environment variables")
    print("  export GRPC_ENDPOINT='https://grpc.ny.shyft.to'")
    print("  export GRPC_TOKEN='your-x-token'")
    sys.exit(1)

# Program to filter (default: PumpFun)
TARGET_PROGRAM = os.getenv(
    "TARGET_PROGRAM", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
)

# Reconnection settings
MAX_RECONNECT_DELAY = 60.0
INITIAL_RECONNECT_DELAY = 0.1
PING_INTERVAL_SECONDS = 15
MAX_QUEUE_SIZE = 10_000

# ── gRPC Setup ──────────────────────────────────────────────────────


def create_channel(endpoint: str, token: str) -> grpc.Channel:
    """Create an authenticated TLS gRPC channel.

    Args:
        endpoint: gRPC endpoint URL (https:// prefix is stripped).
        token: x-token for authentication.

    Returns:
        Configured gRPC secure channel.
    """
    clean_endpoint = endpoint.replace("https://", "").replace("http://", "")

    auth_creds = grpc.metadata_call_credentials(
        lambda context, callback: callback((("x-token", token),), None)
    )
    ssl_creds = grpc.ssl_channel_credentials()
    combined = grpc.composite_channel_credentials(ssl_creds, auth_creds)

    return grpc.secure_channel(
        clean_endpoint,
        combined,
        options=[
            ("grpc.max_receive_message_length", 64 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 10_000),
            ("grpc.keepalive_timeout_ms", 5_000),
        ],
    )


# ── Stub Generation Check ──────────────────────────────────────────

try:
    # Attempt to import generated protobuf stubs
    # Users must generate these from the yellowstone-grpc proto files
    from generated import geyser_pb2, geyser_pb2_grpc  # type: ignore
except ImportError:
    print("ERROR: Generated protobuf stubs not found.")
    print()
    print("Generate them first:")
    print("  git clone https://github.com/rpcpool/yellowstone-grpc.git")
    print("  mkdir -p generated")
    print("  python -m grpc_tools.protoc \\")
    print("    -I./yellowstone-grpc/yellowstone-grpc-proto/proto/ \\")
    print("    --python_out=./generated \\")
    print("    --pyi_out=./generated \\")
    print("    --grpc_python_out=./generated \\")
    print("    ./yellowstone-grpc/yellowstone-grpc-proto/proto/*.proto")
    print()
    print("Then ensure 'generated/' is in your PYTHONPATH or working directory.")
    sys.exit(1)


# ── Transaction Parsing ────────────────────────────────────────────


def parse_transaction(tx_update) -> dict:
    """Parse a SubscribeUpdateTransaction into a readable dict.

    Args:
        tx_update: A SubscribeUpdateTransaction protobuf message.

    Returns:
        Dict with signature, slot, accounts, instructions, and token changes.
    """
    info = tx_update.transaction
    sig = base58.b58encode(info.signature).decode()
    slot = tx_update.slot

    msg = info.transaction.message
    account_keys = [base58.b58encode(k).decode() for k in msg.account_keys]

    # Parse top-level instructions
    instructions = []
    for ix in msg.instructions:
        program_id = account_keys[ix.program_id_index]
        ix_accounts = [account_keys[i] for i in ix.accounts]
        discriminator = ix.data[:8].hex() if len(ix.data) >= 8 else ix.data.hex()
        instructions.append({
            "program": program_id,
            "accounts": ix_accounts,
            "discriminator": discriminator,
            "data_len": len(ix.data),
        })

    # Parse token balance changes
    token_changes = []
    pre_balances = {tb.account_index: tb for tb in info.meta.pre_token_balances}
    for post in info.meta.post_token_balances:
        pre = pre_balances.get(post.account_index)
        pre_amount = float(pre.ui_token_amount.ui_amount) if pre else 0.0
        post_amount = float(post.ui_token_amount.ui_amount)
        delta = post_amount - pre_amount
        if abs(delta) > 0:
            token_changes.append({
                "mint": post.mint,
                "owner": post.owner,
                "delta": delta,
                "post_amount": post_amount,
            })

    return {
        "signature": sig,
        "slot": slot,
        "index": info.index,
        "fee": info.meta.fee,
        "compute_units": info.meta.compute_units_consumed,
        "accounts": account_keys,
        "instructions": instructions,
        "token_changes": token_changes,
        "num_logs": len(info.meta.log_messages),
    }


# ── Streaming Logic ────────────────────────────────────────────────


def build_subscribe_request(
    program_id: str, from_slot: Optional[int] = None
) -> geyser_pb2.SubscribeRequest:
    """Build a subscription request for a specific program.

    Args:
        program_id: Base58 program address to filter transactions.
        from_slot: Optional slot to replay from (for reconnection).

    Returns:
        Configured SubscribeRequest.
    """
    request = geyser_pb2.SubscribeRequest(
        transactions={
            "target": geyser_pb2.SubscribeRequestFilterTransactions(
                account_include=[program_id],
                vote=False,
                failed=False,
            )
        },
        commitment=geyser_pb2.CommitmentLevel.PROCESSED,
    )
    if from_slot is not None:
        request.from_slot = from_slot
    return request


def stream_with_reconnection(
    endpoint: str,
    token: str,
    program_id: str,
    msg_queue: queue.Queue,
) -> None:
    """Connect to gRPC and stream messages with automatic reconnection.

    Args:
        endpoint: gRPC endpoint URL.
        token: Authentication token.
        program_id: Program to filter.
        msg_queue: Queue to push parsed updates into.
    """
    delay = INITIAL_RECONNECT_DELAY
    last_slot: Optional[int] = None

    while True:
        try:
            channel = create_channel(endpoint, token)
            stub = geyser_pb2_grpc.GeyserStub(channel)

            from_slot = (last_slot - 32) if last_slot else None
            request = build_subscribe_request(program_id, from_slot)

            print(f"Connecting to {endpoint}...")
            print(f"Filtering program: {program_id}")
            if from_slot:
                print(f"Replaying from slot: {from_slot}")

            stream = stub.Subscribe(iter([request]))
            delay = INITIAL_RECONNECT_DELAY  # reset on successful connect
            print("Connected. Streaming transactions...\n")

            for update in stream:
                if update.HasField("transaction"):
                    tx = update.transaction
                    last_slot = tx.slot
                    try:
                        msg_queue.put_nowait(tx)
                    except queue.Full:
                        pass  # drop oldest if queue is full

                elif update.HasField("ping"):
                    pass  # server ping, connection is alive

        except grpc.RpcError as e:
            status = e.code() if hasattr(e, "code") else "UNKNOWN"
            print(f"\nDisconnected: {status}. Reconnecting in {delay:.1f}s...")
            time.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY)

        except KeyboardInterrupt:
            print("\nShutting down...")
            return

        except Exception as e:
            print(f"\nUnexpected error: {e}. Reconnecting in {delay:.1f}s...")
            time.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY)


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point: start streaming and print parsed transactions."""
    msg_queue: queue.Queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
    seen_sigs: set = set()
    tx_count = 0
    start_time = time.time()

    # Start gRPC reader in background thread
    reader_thread = threading.Thread(
        target=stream_with_reconnection,
        args=(GRPC_ENDPOINT, GRPC_TOKEN, TARGET_PROGRAM, msg_queue),
        daemon=True,
    )
    reader_thread.start()

    # Process messages in main thread
    try:
        while True:
            try:
                tx_update = msg_queue.get(timeout=30.0)
            except queue.Empty:
                elapsed = time.time() - start_time
                print(f"No updates in 30s. Total: {tx_count} txs in {elapsed:.0f}s")
                continue

            parsed = parse_transaction(tx_update)

            # Deduplicate (from_slot replay can produce duplicates)
            if parsed["signature"] in seen_sigs:
                continue
            seen_sigs.add(parsed["signature"])

            # Keep seen_sigs bounded
            if len(seen_sigs) > 100_000:
                seen_sigs.clear()

            tx_count += 1

            # Print summary
            print(f"[{parsed['slot']}] {parsed['signature'][:20]}...")
            print(f"  Fee: {parsed['fee']} lamports | CU: {parsed['compute_units']}")
            print(f"  Instructions: {len(parsed['instructions'])}")
            for ix in parsed["instructions"]:
                prog_short = ix["program"][:8] + "..."
                print(f"    {prog_short} disc={ix['discriminator']} ({ix['data_len']}B)")
            if parsed["token_changes"]:
                print(f"  Token changes:")
                for tc in parsed["token_changes"]:
                    mint_short = tc["mint"][:8] + "..."
                    print(f"    {mint_short}: {tc['delta']:+.6f}")
            print()

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        rate = tx_count / elapsed if elapsed > 0 else 0
        print(f"\nProcessed {tx_count} transactions in {elapsed:.1f}s ({rate:.1f} tx/s)")


if __name__ == "__main__":
    main()
