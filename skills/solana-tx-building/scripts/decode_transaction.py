#!/usr/bin/env python3
"""Fetch and decode a Solana transaction from the chain.

Retrieves a transaction by its signature, then decodes and displays:
- All instructions with program identification
- Account keys and their roles (signer, writable)
- Compute units consumed and fees paid
- Inner instructions (CPI calls)

In --demo mode, displays a hardcoded transaction structure without
requiring an RPC connection.

Usage:
    python scripts/decode_transaction.py --demo
    python scripts/decode_transaction.py --signature <TX_SIGNATURE>
    python scripts/decode_transaction.py --signature <TX_SIGNATURE> --rpc <RPC_URL>

Dependencies:
    uv pip install httpx

Environment Variables:
    SOLANA_RPC_URL: Solana RPC endpoint (optional)
    HELIUS_API_KEY: Helius API key for enhanced RPC (optional)
"""

import argparse
import json
import os
import sys
from typing import Any, Optional

# ── Configuration ───────────────────────────────────────────────────
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")

# ── Known Programs ──────────────────────────────────────────────────
KNOWN_PROGRAMS: dict[str, str] = {
    "11111111111111111111111111111111": "System Program",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token Program",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "Token-2022 Program",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "Associated Token Account Program",
    "ComputeBudget111111111111111111111111111111": "Compute Budget Program",
    "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": "Memo Program v2",
    "Memo1UhkJBfCR6MNhJeXukzT2hbXzgnQ8e7MY1WDvN8": "Memo Program v1",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter v6",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter v4",
    "JUP2jxvXaqu7NQY1GmNF4m1vodw12LVXYxbFL2uXvfo": "Jupiter v2",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM v4",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca Swap v2",
    "SSwpkEEcbUqx4vtoEByFjSkhKdCT862DNVb52nZg1UZ": "Saber Stable Swap",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora DLMM",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "Meteora Pools",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "Pump.fun",
    "TSWAPaqyCSx2KABk68Shruf4rp7CxcNi8hAsbdwmHbN": "Tensor Swap",
    "M2mx93ekt1fmXSVkTrUL9xVFHkmME8HTUi5Cyc5aF7K": "Magic Eden v2",
    "Auth4MyMPJWFAtBnJFrSdbNWWQ3QrHnQrjPnWPgqurp": "Magic Eden Auth",
    "Vote111111111111111111111111111111111111111": "Vote Program",
    "Stake11111111111111111111111111111111111111": "Stake Program",
    "AddressLookupTab1e1111111111111111111111111": "Address Lookup Table Program",
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s": "Metaplex Token Metadata",
    "So1endDq2YkqhipRh3WViPa8hFvz0XP1SOERDCz3EHQ": "Solend",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter v6",
    "jitotL4nLKSn6RzRJUYS1PGGYkjTCUJAUEcgBNcFimj": "Jito Tip Program",
}


def identify_program(program_id: str) -> str:
    """Identify a program by its address.

    Args:
        program_id: Base58-encoded program public key.

    Returns:
        Human-readable program name, or "Unknown Program" with truncated address.
    """
    if program_id in KNOWN_PROGRAMS:
        return KNOWN_PROGRAMS[program_id]
    return f"Unknown ({program_id[:16]}...)"


# ── RPC Functions ────────────────────────────────────────────────────
def get_rpc_url(override: Optional[str] = None) -> str:
    """Determine the RPC URL to use.

    Priority: CLI arg > SOLANA_RPC_URL env > Helius > default.

    Args:
        override: Optional CLI-provided RPC URL.

    Returns:
        The RPC URL to use.
    """
    if override:
        return override
    if SOLANA_RPC_URL:
        return SOLANA_RPC_URL
    if HELIUS_API_KEY:
        return f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    return DEFAULT_RPC_URL


def fetch_transaction(rpc_url: str, signature: str) -> Optional[dict]:
    """Fetch a transaction from the Solana RPC.

    Args:
        rpc_url: Solana RPC endpoint URL.
        signature: Transaction signature (base58).

    Returns:
        Parsed transaction data, or None on error.
    """
    try:
        import httpx
    except ImportError:
        print("Error: httpx is required. Install with: uv pip install httpx")
        return None

    try:
        resp = httpx.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "maxSupportedTransactionVersion": 0,
                    },
                ],
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            print(f"RPC error: {data['error']}")
            return None

        if data.get("result") is None:
            print(f"Transaction not found: {signature}")
            print("The transaction may not exist or the RPC may not have historical data.")
            return None

        return data["result"]

    except Exception as e:
        print(f"Failed to fetch transaction: {e}")
        return None


# ── Transaction Decoder ─────────────────────────────────────────────
def decode_and_display(tx_data: dict, signature: str = "N/A") -> None:
    """Decode and display a transaction in human-readable format.

    Args:
        tx_data: Parsed transaction data from getTransaction RPC call.
        signature: Transaction signature for display.
    """
    print("=" * 70)
    print("TRANSACTION DECODER")
    print("=" * 70)
    print()

    # Basic info
    print(f"Signature: {signature}")
    slot = tx_data.get("slot", "N/A")
    print(f"Slot:      {slot}")
    block_time = tx_data.get("blockTime")
    if block_time:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(block_time, tz=timezone.utc)
        print(f"Time:      {dt.isoformat()}")
    print()

    # Transaction status
    meta = tx_data.get("meta", {})
    err = meta.get("err")
    if err:
        print(f"STATUS: FAILED — {err}")
    else:
        print("STATUS: SUCCESS")
    print()

    # Version
    version = tx_data.get("version", "legacy")
    print(f"Version: {version}")
    print()

    # Fees
    fee = meta.get("fee", 0)
    print("─" * 70)
    print("FEES")
    print("─" * 70)
    print(f"Transaction fee: {fee} lamports ({fee / 1_000_000_000:.9f} SOL)")

    compute_consumed = meta.get("computeUnitsConsumed")
    if compute_consumed is not None:
        print(f"Compute units:   {compute_consumed:,}")
        if fee > 5000 and compute_consumed > 0:
            priority_fee = fee - 5000  # subtract base fee
            micro_lamports_per_cu = (priority_fee * 1_000_000) / compute_consumed
            print(f"Priority fee:    ~{priority_fee} lamports ({micro_lamports_per_cu:.0f} micro-lamports/CU)")
    print()

    # Account keys
    transaction = tx_data.get("transaction", {})
    message = transaction.get("message", {})
    account_keys = message.get("accountKeys", [])

    print("─" * 70)
    print(f"ACCOUNTS ({len(account_keys)})")
    print("─" * 70)

    for i, acc in enumerate(account_keys):
        if isinstance(acc, dict):
            pubkey = acc.get("pubkey", "?")
            is_signer = acc.get("signer", False)
            is_writable = acc.get("writable", False)
            source = acc.get("source", "transaction")
        else:
            pubkey = acc
            is_signer = False
            is_writable = False
            source = "transaction"

        roles = []
        if is_signer:
            roles.append("signer")
        if is_writable:
            roles.append("writable")
        if source == "lookupTable":
            roles.append("ALT")

        role_str = f" ({', '.join(roles)})" if roles else ""

        # Check if this is a known program
        program_name = KNOWN_PROGRAMS.get(pubkey, "")
        label = f" ← {program_name}" if program_name else ""

        print(f"  [{i:2d}] {pubkey}{role_str}{label}")
    print()

    # Instructions
    instructions = message.get("instructions", [])
    print("─" * 70)
    print(f"INSTRUCTIONS ({len(instructions)})")
    print("─" * 70)

    for i, ix in enumerate(instructions):
        _display_instruction(ix, i, account_keys)
    print()

    # Inner instructions (CPI calls)
    inner_instructions = meta.get("innerInstructions", [])
    if inner_instructions:
        print("─" * 70)
        print("INNER INSTRUCTIONS (CPI calls)")
        print("─" * 70)

        for inner_group in inner_instructions:
            ix_index = inner_group.get("index", "?")
            inner_ixs = inner_group.get("instructions", [])
            print(f"\n  Triggered by instruction [{ix_index}]:")
            for j, inner_ix in enumerate(inner_ixs):
                _display_instruction(inner_ix, j, account_keys, indent="    ")
        print()

    # Balance changes
    pre_balances = meta.get("preBalances", [])
    post_balances = meta.get("postBalances", [])
    if pre_balances and post_balances:
        print("─" * 70)
        print("SOL BALANCE CHANGES")
        print("─" * 70)

        for i, (pre, post) in enumerate(zip(pre_balances, post_balances)):
            diff = post - pre
            if diff != 0:
                pubkey = _get_pubkey(account_keys, i)
                direction = "+" if diff > 0 else ""
                print(f"  {pubkey[:24]}...  {direction}{diff / 1_000_000_000:.9f} SOL")
        print()

    # Token balance changes
    pre_token = meta.get("preTokenBalances", [])
    post_token = meta.get("postTokenBalances", [])
    if pre_token or post_token:
        print("─" * 70)
        print("TOKEN BALANCE CHANGES")
        print("─" * 70)
        _display_token_changes(pre_token, post_token, account_keys)
        print()

    # Log messages (truncated)
    logs = meta.get("logMessages", [])
    if logs:
        print("─" * 70)
        print(f"LOG MESSAGES ({len(logs)} lines, showing first 20)")
        print("─" * 70)
        for log_line in logs[:20]:
            print(f"  {log_line}")
        if len(logs) > 20:
            print(f"  ... and {len(logs) - 20} more lines")
        print()

    print("=" * 70)


def _display_instruction(
    ix: dict,
    index: int,
    account_keys: list,
    indent: str = "  ",
) -> None:
    """Display a single instruction.

    Args:
        ix: Instruction data dict.
        index: Instruction index for display.
        account_keys: Full account keys list for resolving indices.
        indent: Indentation prefix.
    """
    # jsonParsed format has "parsed" field for known programs
    if "parsed" in ix:
        parsed = ix["parsed"]
        program = ix.get("program", "unknown")
        program_id = ix.get("programId", "?")
        program_name = identify_program(program_id)

        if isinstance(parsed, dict):
            ix_type = parsed.get("type", "?")
            info = parsed.get("info", {})
            print(f"{indent}[{index}] {program_name}: {ix_type}")

            # Display key info fields
            for key, value in info.items():
                if isinstance(value, (str, int, float)):
                    print(f"{indent}     {key}: {value}")
                elif isinstance(value, dict) and len(value) <= 3:
                    for k, v in value.items():
                        print(f"{indent}     {key}.{k}: {v}")
        else:
            print(f"{indent}[{index}] {program_name}: {parsed}")
        return

    # Raw format
    program_id_index = ix.get("programIdIndex")
    if program_id_index is not None:
        program_id = _get_pubkey(account_keys, program_id_index)
    else:
        program_id = ix.get("programId", "?")

    program_name = identify_program(program_id)
    print(f"{indent}[{index}] {program_name}")

    # Account indices
    acc_indices = ix.get("accounts", [])
    if acc_indices and len(acc_indices) <= 8:
        acc_strs = []
        for ai in acc_indices:
            if isinstance(ai, int):
                pk = _get_pubkey(account_keys, ai)
                acc_strs.append(f"{pk[:12]}...")
            else:
                acc_strs.append(str(ai)[:12] + "...")
        print(f"{indent}     accounts: [{', '.join(acc_strs)}]")
    elif acc_indices:
        print(f"{indent}     accounts: [{len(acc_indices)} accounts]")

    # Data
    data = ix.get("data", "")
    if data and len(data) <= 40:
        print(f"{indent}     data: {data}")
    elif data:
        print(f"{indent}     data: {data[:40]}... ({len(data)} chars)")


def _get_pubkey(account_keys: list, index: int) -> str:
    """Get a pubkey string from account keys by index.

    Args:
        account_keys: List of account keys (str or dict).
        index: Index into the list.

    Returns:
        Public key string, or "?" if index is out of range.
    """
    if index >= len(account_keys):
        return "?"
    acc = account_keys[index]
    if isinstance(acc, dict):
        return acc.get("pubkey", "?")
    return str(acc)


def _display_token_changes(
    pre: list[dict],
    post: list[dict],
    account_keys: list,
) -> None:
    """Display token balance changes between pre and post states.

    Args:
        pre: Pre-transaction token balances.
        post: Post-transaction token balances.
        account_keys: Full account keys list.
    """
    # Build lookup of pre-balances by account index
    pre_map: dict[int, dict] = {}
    for entry in pre:
        idx = entry.get("accountIndex", -1)
        pre_map[idx] = entry

    post_map: dict[int, dict] = {}
    for entry in post:
        idx = entry.get("accountIndex", -1)
        post_map[idx] = entry

    all_indices = set(pre_map.keys()) | set(post_map.keys())

    for idx in sorted(all_indices):
        pre_entry = pre_map.get(idx, {})
        post_entry = post_map.get(idx, {})

        mint = (
            post_entry.get("mint")
            or pre_entry.get("mint")
            or "?"
        )
        owner = (
            post_entry.get("owner")
            or pre_entry.get("owner")
            or "?"
        )

        pre_amount_str = (
            pre_entry.get("uiTokenAmount", {}).get("uiAmountString", "0")
        )
        post_amount_str = (
            post_entry.get("uiTokenAmount", {}).get("uiAmountString", "0")
        )

        try:
            pre_amount = float(pre_amount_str) if pre_amount_str else 0.0
            post_amount = float(post_amount_str) if post_amount_str else 0.0
        except ValueError:
            pre_amount = 0.0
            post_amount = 0.0

        diff = post_amount - pre_amount
        if abs(diff) > 0:
            direction = "+" if diff > 0 else ""
            print(f"  Owner: {owner[:20]}...")
            print(f"  Mint:  {mint[:20]}...")
            print(f"  Change: {direction}{diff}")
            print()


# ── Demo Mode ────────────────────────────────────────────────────────
DEMO_TRANSACTION: dict[str, Any] = {
    "slot": 250000000,
    "blockTime": 1709251200,
    "version": 0,
    "transaction": {
        "message": {
            "accountKeys": [
                {"pubkey": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "signer": True, "writable": True, "source": "transaction"},
                {"pubkey": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "signer": False, "writable": True, "source": "transaction"},
                {"pubkey": "So11111111111111111111111111111111111111112", "signer": False, "writable": True, "source": "transaction"},
                {"pubkey": "ComputeBudget111111111111111111111111111111", "signer": False, "writable": False, "source": "transaction"},
                {"pubkey": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", "signer": False, "writable": False, "source": "transaction"},
                {"pubkey": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "signer": False, "writable": False, "source": "transaction"},
                {"pubkey": "11111111111111111111111111111111", "signer": False, "writable": False, "source": "transaction"},
                {"pubkey": "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "signer": False, "writable": False, "source": "transaction"},
                {"pubkey": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", "signer": False, "writable": False, "source": "transaction"},
                {"pubkey": "D8cy77BBepLMngZx6ZukaTff5hCt1HrWyKk3Hnd9oitf", "signer": False, "writable": True, "source": "lookupTable"},
                {"pubkey": "3NxDBWt55PEoCWCiH5t2KpGNzEb8Bhi5XAYyxEPCFm7T", "signer": False, "writable": True, "source": "lookupTable"},
            ],
            "instructions": [
                {
                    "programId": "ComputeBudget111111111111111111111111111111",
                    "parsed": {"type": "setComputeUnitLimit", "info": {"units": 300000}},
                    "program": "computeBudget",
                },
                {
                    "programId": "ComputeBudget111111111111111111111111111111",
                    "parsed": {"type": "setComputeUnitPrice", "info": {"microLamports": 5000}},
                    "program": "computeBudget",
                },
                {
                    "programId": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
                    "parsed": {"type": "route", "info": {"inputMint": "So11111111111111111111111111111111111111112", "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "inAmount": "1000000000", "slippageBps": 50}},
                    "program": "jupiter",
                },
            ],
        },
    },
    "meta": {
        "err": None,
        "fee": 6500,
        "computeUnitsConsumed": 185432,
        "preBalances": [2500000000, 0, 1000000000, 1, 1, 1, 1, 1, 1, 500000000, 300000000],
        "postBalances": [1499993500, 0, 0, 1, 1, 1, 1, 1, 1, 500000000, 300000000],
        "preTokenBalances": [
            {"accountIndex": 1, "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "owner": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "uiTokenAmount": {"uiAmountString": "0", "decimals": 6}},
        ],
        "postTokenBalances": [
            {"accountIndex": 1, "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "owner": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "uiTokenAmount": {"uiAmountString": "150.5", "decimals": 6}},
        ],
        "innerInstructions": [
            {
                "index": 2,
                "instructions": [
                    {
                        "programId": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
                        "parsed": {"type": "swap", "info": {"amountIn": "1000000000", "amountOut": "150500000"}},
                        "program": "whirlpool",
                    },
                    {
                        "programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                        "parsed": {"type": "transfer", "info": {"amount": "1000000000", "source": "So11...", "destination": "D8cy..."}},
                        "program": "spl-token",
                    },
                    {
                        "programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                        "parsed": {"type": "transfer", "info": {"amount": "150500000", "source": "3Nxd...", "destination": "EPjF..."}},
                        "program": "spl-token",
                    },
                ],
            }
        ],
        "logMessages": [
            "Program ComputeBudget111111111111111111111111111111 invoke [1]",
            "Program ComputeBudget111111111111111111111111111111 success",
            "Program ComputeBudget111111111111111111111111111111 invoke [1]",
            "Program ComputeBudget111111111111111111111111111111 success",
            "Program JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 invoke [1]",
            "Program log: Instruction: Route",
            "Program whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc invoke [2]",
            "Program log: Instruction: Swap",
            "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA invoke [3]",
            "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA success",
            "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA invoke [3]",
            "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA success",
            "Program whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc success",
            "Program JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 success",
        ],
    },
}


def run_demo() -> None:
    """Run demo mode with a hardcoded transaction structure."""
    print("Running in DEMO mode with a simulated Jupiter swap transaction.")
    print("(SOL → USDC via Orca Whirlpool, routed through Jupiter v6)")
    print()
    decode_and_display(
        DEMO_TRANSACTION,
        signature="5demo...ExampleSignatureNotReal...xyz",
    )


def run_live(signature: str, rpc_override: Optional[str] = None) -> None:
    """Fetch and decode a live transaction from the chain.

    Args:
        signature: Transaction signature to look up.
        rpc_override: Optional RPC URL override.
    """
    rpc_url = get_rpc_url(rpc_override)
    print(f"Fetching transaction from: {rpc_url[:50]}...")
    print(f"Signature: {signature}")
    print()

    tx_data = fetch_transaction(rpc_url, signature)
    if tx_data is None:
        print("Could not fetch transaction. Check the signature and RPC endpoint.")
        sys.exit(1)

    decode_and_display(tx_data, signature=signature)


# ── Main ─────────────────────────────────────────────────────────────
def main() -> None:
    """Parse arguments and run the decoder."""
    parser = argparse.ArgumentParser(
        description="Decode and display a Solana transaction"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with a hardcoded demo transaction",
    )
    parser.add_argument(
        "--signature", "-s",
        type=str,
        help="Transaction signature to decode",
    )
    parser.add_argument(
        "--rpc",
        type=str,
        help="RPC URL override",
    )

    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.signature:
        run_live(args.signature, args.rpc)
    else:
        print("No signature provided. Running in demo mode.")
        print("Use --signature <TX_SIG> to decode a real transaction.")
        print()
        run_demo()


if __name__ == "__main__":
    main()
