#!/usr/bin/env python3
"""Build and inspect a SOL transfer transaction (simulation only).

This script demonstrates Solana transaction construction from scratch:
- Building System Program transfer instructions
- Adding compute budget instructions (unit limit + priority fee)
- Calculating transaction size
- Simulating via RPC (if available)
- Printing a full transaction breakdown

SAFETY: This script NEVER signs or submits real transactions.
It operates in demo/simulation mode only.

Usage:
    python scripts/build_transfer.py
    python scripts/build_transfer.py --sender <PUBKEY> --recipient <PUBKEY> --amount 0.01
    python scripts/build_transfer.py --demo

Dependencies:
    uv pip install httpx

Environment Variables:
    SOLANA_RPC_URL: Solana RPC endpoint (optional, uses devnet by default)
"""

import argparse
import base64
import hashlib
import json
import os
import struct
import sys
from typing import Optional

# ── Configuration ───────────────────────────────────────────────────
DEFAULT_RPC_URL = "https://api.devnet.solana.com"
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", DEFAULT_RPC_URL)

# Well-known program IDs
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"
COMPUTE_BUDGET_PROGRAM_ID = "ComputeBudget111111111111111111111111111111"

# Demo keypairs (NOT real keys — for structure demonstration only)
DEMO_SENDER = "11111111111111111111111111111112"
DEMO_RECIPIENT = "11111111111111111111111111111113"

LAMPORTS_PER_SOL = 1_000_000_000


# ── Base58 Encoding ─────────────────────────────────────────────────
ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58_decode(s: str) -> bytes:
    """Decode a base58-encoded string to bytes.

    Args:
        s: Base58-encoded string.

    Returns:
        Decoded bytes.
    """
    n = 0
    for char in s:
        n = n * 58 + ALPHABET.index(char.encode())
    result = n.to_bytes(max(1, (n.bit_length() + 7) // 8), "big")
    # Handle leading '1's (zero bytes in base58)
    pad = 0
    for char in s:
        if char == "1":
            pad += 1
        else:
            break
    return b"\x00" * pad + result


def base58_encode(data: bytes) -> str:
    """Encode bytes to a base58 string.

    Args:
        data: Raw bytes to encode.

    Returns:
        Base58-encoded string.
    """
    n = int.from_bytes(data, "big")
    result = ""
    while n > 0:
        n, remainder = divmod(n, 58)
        result = ALPHABET[remainder:remainder + 1].decode() + result
    # Handle leading zero bytes
    for byte in data:
        if byte == 0:
            result = "1" + result
        else:
            break
    return result or "1"


# ── Compact Array Encoding ──────────────────────────────────────────
def encode_compact_u16(value: int) -> bytes:
    """Encode an integer as a Solana compact-u16.

    Args:
        value: Integer to encode (0-65535).

    Returns:
        Encoded bytes (1-3 bytes).
    """
    if value < 0x80:
        return bytes([value])
    elif value < 0x4000:
        return bytes([
            (value & 0x7F) | 0x80,
            (value >> 7) & 0x7F,
        ])
    else:
        return bytes([
            (value & 0x7F) | 0x80,
            ((value >> 7) & 0x7F) | 0x80,
            (value >> 14) & 0x03,
        ])


# ── Instruction Builders ────────────────────────────────────────────
def build_system_transfer_data(lamports: int) -> bytes:
    """Build instruction data for a System Program transfer.

    Args:
        lamports: Amount to transfer in lamports.

    Returns:
        Encoded instruction data bytes.
    """
    # Instruction index 2 = Transfer, then amount as u64 LE
    return struct.pack("<I", 2) + struct.pack("<Q", lamports)


def build_compute_unit_limit_data(units: int) -> bytes:
    """Build instruction data to set compute unit limit.

    Args:
        units: Maximum compute units for the transaction.

    Returns:
        Encoded instruction data bytes.
    """
    return bytes([0x02]) + struct.pack("<I", units)


def build_compute_unit_price_data(micro_lamports: int) -> bytes:
    """Build instruction data to set compute unit price (priority fee).

    Args:
        micro_lamports: Price per compute unit in micro-lamports.

    Returns:
        Encoded instruction data bytes.
    """
    return bytes([0x03]) + struct.pack("<Q", micro_lamports)


# ── Transaction Message Builder ──────────────────────────────────────
class TransactionBuilder:
    """Builds a Solana transaction message (legacy format).

    This builder collects instructions and their account references,
    deduplicates accounts, sorts them by role, and serializes the
    complete message.

    Attributes:
        fee_payer: The pubkey (bytes) of the fee payer.
        instructions: List of (program_id_bytes, accounts_list, data_bytes).
    """

    def __init__(self, fee_payer: bytes) -> None:
        """Initialize the builder with a fee payer.

        Args:
            fee_payer: 32-byte public key of the fee payer.
        """
        self.fee_payer: bytes = fee_payer
        self.instructions: list[tuple[bytes, list[tuple[bytes, bool, bool]], bytes]] = []

    def add_instruction(
        self,
        program_id: bytes,
        accounts: list[tuple[bytes, bool, bool]],
        data: bytes,
    ) -> "TransactionBuilder":
        """Add an instruction to the transaction.

        Args:
            program_id: 32-byte program public key.
            accounts: List of (pubkey, is_signer, is_writable) tuples.
            data: Instruction data bytes.

        Returns:
            Self for chaining.
        """
        self.instructions.append((program_id, accounts, data))
        return self

    def _collect_accounts(self) -> list[tuple[bytes, bool, bool]]:
        """Collect and deduplicate all accounts across instructions.

        Returns:
            Sorted list of (pubkey, is_signer, is_writable) with deduplication.
        """
        account_map: dict[bytes, tuple[bool, bool]] = {}

        # Fee payer is always signer + writable
        account_map[self.fee_payer] = (True, True)

        for program_id, accounts, _ in self.instructions:
            # Program ID is read-only, non-signer
            if program_id not in account_map:
                account_map[program_id] = (False, False)

            for pubkey, is_signer, is_writable in accounts:
                if pubkey in account_map:
                    existing_signer, existing_writable = account_map[pubkey]
                    account_map[pubkey] = (
                        existing_signer or is_signer,
                        existing_writable or is_writable,
                    )
                else:
                    account_map[pubkey] = (is_signer, is_writable)

        # Sort: writable signers first, then readonly signers,
        # then writable non-signers, then readonly non-signers
        # Fee payer must be first
        result: list[tuple[bytes, bool, bool]] = []
        for pubkey, (is_signer, is_writable) in account_map.items():
            result.append((pubkey, is_signer, is_writable))

        def sort_key(item: tuple[bytes, bool, bool]) -> tuple[int, int, bytes]:
            pubkey, is_signer, is_writable = item
            if pubkey == self.fee_payer:
                return (0, 0, pubkey)
            if is_signer and is_writable:
                return (1, 0, pubkey)
            if is_signer and not is_writable:
                return (1, 1, pubkey)
            if not is_signer and is_writable:
                return (2, 0, pubkey)
            return (2, 1, pubkey)

        result.sort(key=sort_key)
        return result

    def build_message(self, recent_blockhash: bytes) -> bytes:
        """Serialize the transaction message.

        Args:
            recent_blockhash: 32-byte recent blockhash.

        Returns:
            Serialized message bytes.
        """
        accounts = self._collect_accounts()
        pubkey_to_index = {acc[0]: i for i, acc in enumerate(accounts)}

        # Count header values
        num_signers = sum(1 for _, s, _ in accounts if s)
        num_readonly_signed = sum(1 for _, s, w in accounts if s and not w)
        num_readonly_unsigned = sum(1 for _, s, w in accounts if not s and not w)

        # Header
        header = bytes([num_signers, num_readonly_signed, num_readonly_unsigned])

        # Account keys
        account_keys = b"".join(acc[0] for acc in accounts)

        # Compile instructions
        compiled_instructions = b""
        for program_id, inst_accounts, data in self.instructions:
            prog_index = pubkey_to_index[program_id]
            acc_indices = bytes([pubkey_to_index[a[0]] for a in inst_accounts])
            compiled_instructions += (
                bytes([prog_index])
                + encode_compact_u16(len(acc_indices))
                + acc_indices
                + encode_compact_u16(len(data))
                + data
            )

        # Assemble message
        message = (
            header
            + encode_compact_u16(len(accounts))
            + account_keys
            + recent_blockhash
            + encode_compact_u16(len(self.instructions))
            + compiled_instructions
        )
        return message

    def get_info(self, recent_blockhash: bytes) -> dict:
        """Get transaction information without signing.

        Args:
            recent_blockhash: 32-byte recent blockhash.

        Returns:
            Dict with transaction details: size, accounts, instructions.
        """
        accounts = self._collect_accounts()
        message = self.build_message(recent_blockhash)
        num_signers = sum(1 for _, s, _ in accounts if s)

        # Transaction size = compact(num_signatures) + signatures + message
        sig_size = 1 + (num_signers * 64)  # compact-u16(1) + 64 bytes per sig
        total_size = sig_size + len(message)

        return {
            "message_size": len(message),
            "total_size_with_signatures": total_size,
            "num_accounts": len(accounts),
            "num_signers": num_signers,
            "num_instructions": len(self.instructions),
            "size_limit": 1232,
            "bytes_remaining": 1232 - total_size,
            "accounts": [
                {
                    "index": i,
                    "pubkey": base58_encode(acc[0]),
                    "is_signer": acc[1],
                    "is_writable": acc[2],
                }
                for i, acc in enumerate(accounts)
            ],
        }


# ── RPC Helpers ──────────────────────────────────────────────────────
def get_latest_blockhash(rpc_url: str) -> Optional[dict]:
    """Fetch the latest blockhash from an RPC endpoint.

    Args:
        rpc_url: Solana RPC URL.

    Returns:
        Dict with 'blockhash' and 'lastValidBlockHeight', or None on error.
    """
    try:
        import httpx

        resp = httpx.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getLatestBlockhash",
                "params": [{"commitment": "finalized"}],
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            print(f"RPC error: {data['error']}")
            return None
        return data["result"]["value"]
    except ImportError:
        print("httpx not installed. Install with: uv pip install httpx")
        return None
    except Exception as e:
        print(f"Failed to fetch blockhash: {e}")
        return None


def simulate_transaction(rpc_url: str, message_base64: str) -> Optional[dict]:
    """Simulate a transaction via RPC.

    Args:
        rpc_url: Solana RPC URL.
        message_base64: Base64-encoded transaction message.

    Returns:
        Simulation result dict, or None on error.
    """
    try:
        import httpx

        resp = httpx.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "simulateTransaction",
                "params": [
                    message_base64,
                    {
                        "encoding": "base64",
                        "sigVerify": False,
                        "replaceRecentBlockhash": True,
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
        return data["result"]["value"]
    except ImportError:
        print("httpx not installed. Install with: uv pip install httpx")
        return None
    except Exception as e:
        print(f"Simulation request failed: {e}")
        return None


# ── Demo Mode ────────────────────────────────────────────────────────
def run_demo() -> None:
    """Run a demonstration build of a SOL transfer transaction.

    Builds the transaction structure, prints the breakdown,
    and optionally simulates if an RPC endpoint is available.
    NEVER signs or submits the transaction.
    """
    print("=" * 60)
    print("SOLANA TRANSACTION BUILDER — DEMO MODE")
    print("=" * 60)
    print()
    print("WARNING: This is a demonstration only.")
    print("No transactions will be signed or submitted.")
    print()

    # Use demo pubkeys (32 zero-padded bytes)
    sender = base58_decode(DEMO_SENDER)
    recipient = base58_decode(DEMO_RECIPIENT)

    amount_sol = 0.01
    amount_lamports = int(amount_sol * LAMPORTS_PER_SOL)

    print(f"Sender:    {DEMO_SENDER}")
    print(f"Recipient: {DEMO_RECIPIENT}")
    print(f"Amount:    {amount_sol} SOL ({amount_lamports} lamports)")
    print()

    # Build compute budget program ID
    compute_budget_id = base58_decode(COMPUTE_BUDGET_PROGRAM_ID)
    system_program_id = base58_decode(SYSTEM_PROGRAM_ID)

    # Build transaction
    builder = TransactionBuilder(fee_payer=sender)

    # Instruction 1: Set compute unit limit
    cu_limit = 200_000
    builder.add_instruction(
        program_id=compute_budget_id,
        accounts=[],
        data=build_compute_unit_limit_data(cu_limit),
    )

    # Instruction 2: Set priority fee
    priority_fee_micro_lamports = 1_000  # 1000 micro-lamports per CU
    builder.add_instruction(
        program_id=compute_budget_id,
        accounts=[],
        data=build_compute_unit_price_data(priority_fee_micro_lamports),
    )

    # Instruction 3: SOL transfer
    builder.add_instruction(
        program_id=system_program_id,
        accounts=[
            (sender, True, True),      # Source: signer, writable
            (recipient, False, True),   # Destination: writable
        ],
        data=build_system_transfer_data(amount_lamports),
    )

    # Use a dummy blockhash for demo
    dummy_blockhash = b"\x00" * 32

    # Get transaction info
    info = builder.get_info(dummy_blockhash)

    print("─" * 60)
    print("TRANSACTION BREAKDOWN")
    print("─" * 60)
    print(f"Instructions:    {info['num_instructions']}")
    print(f"Accounts:        {info['num_accounts']}")
    print(f"Signers:         {info['num_signers']}")
    print(f"Message size:    {info['message_size']} bytes")
    print(f"Total size:      {info['total_size_with_signatures']} bytes")
    print(f"Size limit:      {info['size_limit']} bytes")
    print(f"Bytes remaining: {info['bytes_remaining']} bytes")
    print()

    print("ACCOUNTS:")
    for acc in info["accounts"]:
        role_parts = []
        if acc["is_signer"]:
            role_parts.append("signer")
        if acc["is_writable"]:
            role_parts.append("writable")
        role = ", ".join(role_parts) if role_parts else "read-only"
        pubkey_short = acc["pubkey"][:16] + "..."
        print(f"  [{acc['index']}] {pubkey_short}  ({role})")
    print()

    print("INSTRUCTIONS:")
    instruction_names = [
        "SetComputeUnitLimit (200,000 CUs)",
        f"SetComputeUnitPrice ({priority_fee_micro_lamports} micro-lamports/CU)",
        f"SystemProgram.Transfer ({amount_sol} SOL)",
    ]
    for i, name in enumerate(instruction_names):
        print(f"  [{i}] {name}")
    print()

    # Calculate priority fee
    priority_fee = cu_limit * priority_fee_micro_lamports / 1_000_000
    base_fee = 5_000  # lamports per signature
    total_fee = base_fee + priority_fee
    print("FEE BREAKDOWN:")
    print(f"  Base fee:     {base_fee} lamports ({base_fee / LAMPORTS_PER_SOL:.9f} SOL)")
    print(f"  Priority fee: {priority_fee:.0f} lamports ({priority_fee / LAMPORTS_PER_SOL:.9f} SOL)")
    print(f"  Total fee:    {total_fee:.0f} lamports ({total_fee / LAMPORTS_PER_SOL:.9f} SOL)")
    print()

    # Build the message for serialization demo
    message = builder.build_message(dummy_blockhash)

    # Create a mock transaction (with zero signatures for demo)
    num_signers = info["num_signers"]
    mock_tx = (
        encode_compact_u16(num_signers)
        + (b"\x00" * 64 * num_signers)  # zero signatures (unsigned)
        + message
    )
    tx_base64 = base64.b64encode(mock_tx).decode()

    print("SERIALIZED (base64, unsigned — for inspection only):")
    print(f"  {tx_base64[:80]}...")
    print(f"  Length: {len(mock_tx)} bytes")
    print()

    # Attempt RPC simulation if available
    print("─" * 60)
    print("SIMULATION")
    print("─" * 60)

    if SOLANA_RPC_URL == DEFAULT_RPC_URL:
        print(f"Using default devnet RPC: {DEFAULT_RPC_URL}")
        print("Set SOLANA_RPC_URL for a custom endpoint.")
    else:
        print(f"Using RPC: {SOLANA_RPC_URL}")
    print()

    print("Attempting simulation (this will likely fail with demo addresses)...")
    sim_result = simulate_transaction(SOLANA_RPC_URL, tx_base64)

    if sim_result is not None:
        if sim_result.get("err"):
            print(f"Simulation error (expected with demo data): {sim_result['err']}")
            if sim_result.get("logs"):
                print("Logs:")
                for log_line in sim_result["logs"][:10]:
                    print(f"  {log_line}")
        else:
            cu_used = sim_result.get("unitsConsumed", 0)
            print(f"Simulation succeeded — {cu_used} compute units consumed")
    else:
        print("Simulation unavailable (no RPC connection or httpx not installed)")

    print()
    print("=" * 60)
    print("DEMO COMPLETE — No transaction was signed or submitted.")
    print("=" * 60)


def run_custom(sender: str, recipient: str, amount_sol: float) -> None:
    """Build a custom SOL transfer transaction (still never signs/sends).

    Args:
        sender: Base58-encoded sender public key.
        recipient: Base58-encoded recipient public key.
        amount_sol: Amount to transfer in SOL.
    """
    print("=" * 60)
    print("SOLANA TRANSACTION BUILDER — CUSTOM BUILD")
    print("=" * 60)
    print()
    print("WARNING: This builds a transaction structure for inspection.")
    print("No transaction will be signed or submitted.")
    print()

    sender_bytes = base58_decode(sender)
    recipient_bytes = base58_decode(recipient)
    amount_lamports = int(amount_sol * LAMPORTS_PER_SOL)

    compute_budget_id = base58_decode(COMPUTE_BUDGET_PROGRAM_ID)
    system_program_id = base58_decode(SYSTEM_PROGRAM_ID)

    builder = TransactionBuilder(fee_payer=sender_bytes)

    # Compute budget instructions
    cu_limit = 200_000
    cu_price = 1_000
    builder.add_instruction(
        program_id=compute_budget_id,
        accounts=[],
        data=build_compute_unit_limit_data(cu_limit),
    )
    builder.add_instruction(
        program_id=compute_budget_id,
        accounts=[],
        data=build_compute_unit_price_data(cu_price),
    )

    # Transfer instruction
    builder.add_instruction(
        program_id=system_program_id,
        accounts=[
            (sender_bytes, True, True),
            (recipient_bytes, False, True),
        ],
        data=build_system_transfer_data(amount_lamports),
    )

    # Try to get real blockhash
    print("Fetching latest blockhash...")
    bh_result = get_latest_blockhash(SOLANA_RPC_URL)
    if bh_result:
        blockhash = base58_decode(bh_result["blockhash"])
        print(f"Blockhash: {bh_result['blockhash']}")
        print(f"Last valid block height: {bh_result['lastValidBlockHeight']}")
    else:
        blockhash = b"\x00" * 32
        print("Using dummy blockhash (RPC unavailable)")
    print()

    info = builder.get_info(blockhash)

    print(f"Sender:    {sender}")
    print(f"Recipient: {recipient}")
    print(f"Amount:    {amount_sol} SOL ({amount_lamports} lamports)")
    print()
    print(f"Total transaction size: {info['total_size_with_signatures']} / {info['size_limit']} bytes")
    print(f"Accounts: {info['num_accounts']} | Signers: {info['num_signers']} | Instructions: {info['num_instructions']}")
    print()

    for acc in info["accounts"]:
        role = []
        if acc["is_signer"]:
            role.append("signer")
        if acc["is_writable"]:
            role.append("writable")
        print(f"  Account [{acc['index']}]: {acc['pubkey'][:20]}... ({', '.join(role) or 'read-only'})")

    print()
    print("Transaction built successfully (NOT signed, NOT submitted).")
    print("=" * 60)


# ── Main ─────────────────────────────────────────────────────────────
def main() -> None:
    """Parse arguments and run the appropriate mode."""
    parser = argparse.ArgumentParser(
        description="Build a SOL transfer transaction for inspection (never signs/sends)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=True,
        help="Run in demo mode with placeholder addresses (default)",
    )
    parser.add_argument("--sender", type=str, help="Sender public key (base58)")
    parser.add_argument("--recipient", type=str, help="Recipient public key (base58)")
    parser.add_argument(
        "--amount",
        type=float,
        default=0.01,
        help="Amount in SOL (default: 0.01)",
    )

    args = parser.parse_args()

    if args.sender and args.recipient:
        run_custom(args.sender, args.recipient, args.amount)
    else:
        run_demo()


if __name__ == "__main__":
    main()
