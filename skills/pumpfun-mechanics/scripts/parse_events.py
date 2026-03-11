#!/usr/bin/env python3
"""Parse PumpFun events from Solana transaction data.

Demonstrates parsing CreateEvent, TradeEvent, and CompleteEvent from
raw transaction data. Can fetch and parse live transactions or work
with example data in demo mode.

Usage:
    python scripts/parse_events.py
    python scripts/parse_events.py --demo
    TX_SIGNATURE="5abc..." python scripts/parse_events.py

Dependencies:
    uv pip install httpx

Environment Variables:
    SOLANA_RPC_URL: Solana RPC endpoint
    TX_SIGNATURE: Transaction signature to parse (optional)
"""

import base64
import os
import struct
import sys
import time
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
TX_SIGNATURE = os.getenv("TX_SIGNATURE", "")
DEMO_MODE = "--demo" in sys.argv

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# Event discriminators (hex)
CREATE_DISC = bytes.fromhex("1b72a94ddeeb6376")
TRADE_DISC = bytes.fromhex("bddb7fd34ee661ee")
COMPLETE_DISC = bytes.fromhex("5f72619cd42e9808")

# Instruction discriminators (hex)
BUY_V2_DISC = bytes.fromhex("38fc74089edfcd5f")
SELL_V2_DISC = bytes.fromhex("33e685a4017f83ad")
BUY_V1_DISC = bytes.fromhex("66063d1201daebea")
CREATE_IX_DISC = bytes.fromhex("181ec828051c0777")

TOKEN_DECIMALS = 6

# ── Parsers ─────────────────────────────────────────────────────────


def parse_trade_event(data: bytes) -> Optional[dict]:
    """Parse a PumpFun TradeEvent from raw bytes.

    Args:
        data: Raw bytes starting AFTER the 8-byte discriminator.

    Returns:
        Parsed trade event dict, or None on failure.
    """
    if len(data) < 121:
        return None

    try:
        mint = base64.b64encode(data[0:32]).decode()  # or use base58
        sol_amount = struct.unpack_from("<Q", data, 32)[0]
        token_amount = struct.unpack_from("<Q", data, 40)[0]
        is_buy = bool(data[48])
        user = base64.b64encode(data[49:81]).decode()
        timestamp = struct.unpack_from("<q", data, 81)[0]
        v_sol = struct.unpack_from("<Q", data, 89)[0]
        v_tok = struct.unpack_from("<Q", data, 97)[0]
        r_sol = struct.unpack_from("<Q", data, 105)[0]
        r_tok = struct.unpack_from("<Q", data, 113)[0]

        return {
            "type": "TradeEvent",
            "mint_bytes": data[0:32],
            "sol_amount": sol_amount,
            "token_amount": token_amount,
            "is_buy": is_buy,
            "user_bytes": data[49:81],
            "timestamp": timestamp,
            "virtual_sol": v_sol,
            "virtual_token": v_tok,
            "real_sol": r_sol,
            "real_token": r_tok,
        }
    except (struct.error, IndexError):
        return None


def parse_create_event(data: bytes) -> Optional[dict]:
    """Parse a PumpFun CreateEvent from raw bytes.

    Args:
        data: Raw bytes starting AFTER the 8-byte discriminator.

    Returns:
        Parsed create event dict, or None on failure.
    """
    try:
        offset = 0

        # Parse strings (4-byte LE length prefix + UTF-8 data)
        def read_string(d: bytes, off: int) -> tuple[str, int]:
            length = struct.unpack_from("<I", d, off)[0]
            off += 4
            text = d[off:off + length].decode("utf-8", errors="replace")
            return text, off + length

        name, offset = read_string(data, offset)
        symbol, offset = read_string(data, offset)
        uri, offset = read_string(data, offset)

        if offset + 96 > len(data):
            return None

        mint = data[offset:offset + 32]
        bonding_curve = data[offset + 32:offset + 64]
        creator = data[offset + 64:offset + 96]

        return {
            "type": "CreateEvent",
            "name": name,
            "symbol": symbol,
            "uri": uri,
            "mint_bytes": mint,
            "bonding_curve_bytes": bonding_curve,
            "creator_bytes": creator,
        }
    except (struct.error, IndexError, UnicodeDecodeError):
        return None


def parse_complete_event(data: bytes) -> Optional[dict]:
    """Parse a PumpFun CompleteEvent from raw bytes.

    Args:
        data: Raw bytes starting AFTER the 8-byte discriminator.

    Returns:
        Parsed complete event dict, or None on failure.
    """
    if len(data) < 104:
        return None

    try:
        user = data[0:32]
        mint = data[32:64]
        bonding_curve = data[64:96]
        timestamp = struct.unpack_from("<q", data, 96)[0]

        return {
            "type": "CompleteEvent",
            "user_bytes": user,
            "mint_bytes": mint,
            "bonding_curve_bytes": bonding_curve,
            "timestamp": timestamp,
        }
    except (struct.error, IndexError):
        return None


def find_and_parse_events(data: bytes) -> list[dict]:
    """Search for PumpFun events anywhere in instruction data.

    Events are embedded in CPI inner instructions, so discriminators
    may appear at any offset.

    Args:
        data: Raw instruction data bytes.

    Returns:
        List of parsed event dicts.
    """
    events = []

    # Search for each discriminator
    for disc, parser, name in [
        (TRADE_DISC, parse_trade_event, "TradeEvent"),
        (CREATE_DISC, parse_create_event, "CreateEvent"),
        (COMPLETE_DISC, parse_complete_event, "CompleteEvent"),
    ]:
        idx = 0
        while idx < len(data):
            pos = data.find(disc, idx)
            if pos == -1:
                break
            event_data = data[pos + 8:]
            event = parser(event_data)
            if event:
                events.append(event)
            idx = pos + 1  # continue searching for multiple events

    return events


# ── Transaction Fetching ────────────────────────────────────────────


def fetch_transaction(signature: str) -> Optional[dict]:
    """Fetch and parse a transaction by signature.

    Args:
        signature: Transaction signature.

    Returns:
        Full transaction response, or None.
    """
    payload = {
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
    }

    for attempt in range(3):
        try:
            resp = httpx.post(RPC_URL, json=payload, timeout=30.0)
            if resp.status_code == 429:
                time.sleep(3.0)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data.get("result")
        except Exception:
            if attempt < 2:
                time.sleep(2.0)
                continue
    return None


def extract_inner_instructions(tx: dict) -> list[bytes]:
    """Extract raw instruction data from inner instructions.

    Args:
        tx: Full transaction response.

    Returns:
        List of raw data bytes from inner instructions.
    """
    raw_data_list = []

    meta = tx.get("meta", {})
    inner = meta.get("innerInstructions", [])

    for group in inner:
        for ix in group.get("instructions", []):
            data = ix.get("data")
            if data:
                try:
                    raw = base64.b64decode(data)
                    raw_data_list.append(raw)
                except Exception:
                    # Try base58 decoding (jsonParsed uses base58 for instruction data)
                    try:
                        # Simple base58 check — if it's parseable by base64, use that
                        pass
                    except Exception:
                        pass

    return raw_data_list


# ── Demo Data ───────────────────────────────────────────────────────


def generate_demo_trade_event() -> bytes:
    """Generate a synthetic TradeEvent for demo purposes.

    Returns:
        Raw bytes including discriminator + event data.
    """
    data = bytearray()
    data.extend(TRADE_DISC)

    # mint (32 bytes)
    data.extend(b"\x01" * 32)
    # solAmount (1 SOL)
    data.extend(struct.pack("<Q", 1_000_000_000))
    # tokenAmount (~34M tokens)
    data.extend(struct.pack("<Q", 34_277_831_558_567))
    # isBuy
    data.extend(b"\x01")
    # user (32 bytes)
    data.extend(b"\x02" * 32)
    # timestamp
    data.extend(struct.pack("<q", 1709251200))
    # virtualSolReserves (31 SOL after buy)
    data.extend(struct.pack("<Q", 30_990_000_000))
    # virtualTokenReserves
    data.extend(struct.pack("<Q", 1_038_722_168_441_433))
    # realSolReserves
    data.extend(struct.pack("<Q", 990_000_000))
    # realTokenReserves
    data.extend(struct.pack("<Q", 758_722_168_441_433))

    return bytes(data)


# ── Display ─────────────────────────────────────────────────────────


def display_event(event: dict) -> None:
    """Print a parsed event in human-readable format.

    Args:
        event: Parsed event dict.
    """
    event_type = event.get("type", "Unknown")

    if event_type == "TradeEvent":
        action = "BUY" if event["is_buy"] else "SELL"
        sol = event["sol_amount"] / 1e9
        tokens = event["token_amount"] / 10**TOKEN_DECIMALS
        fill = (event["real_sol"] / 85_000_000_000) * 100

        print(f"\n  [{event_type}] {action}")
        print(f"    SOL:          {sol:.6f}")
        print(f"    Tokens:       {tokens:,.2f}")
        print(f"    V_SOL:        {event['virtual_sol'] / 1e9:.6f}")
        print(f"    V_Token:      {event['virtual_token'] / 10**TOKEN_DECIMALS:,.0f}")
        print(f"    R_SOL:        {event['real_sol'] / 1e9:.6f}")
        print(f"    Fill:         {fill:.2f}%")
        print(f"    Timestamp:    {event['timestamp']}")

    elif event_type == "CreateEvent":
        print(f"\n  [{event_type}]")
        print(f"    Name:         {event['name']}")
        print(f"    Symbol:       {event['symbol']}")
        print(f"    URI:          {event['uri'][:60]}...")

    elif event_type == "CompleteEvent":
        print(f"\n  [{event_type}] — GRADUATION!")
        print(f"    Timestamp:    {event['timestamp']}")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Parse PumpFun events."""
    if DEMO_MODE:
        print("=== DEMO MODE ===")
        print("Generating synthetic PumpFun TradeEvent...")

        demo_data = generate_demo_trade_event()
        events = find_and_parse_events(demo_data)

        print(f"\nFound {len(events)} event(s):")
        for event in events:
            display_event(event)

        print("\n--- Event Data Layout ---")
        print(f"  Total bytes:     {len(demo_data)}")
        print(f"  Discriminator:   {demo_data[:8].hex()}")
        print(f"  Event data:      {len(demo_data) - 8} bytes")

        print()
        return

    if TX_SIGNATURE:
        print(f"Fetching transaction: {TX_SIGNATURE}")
        tx = fetch_transaction(TX_SIGNATURE)

        if not tx:
            print("Could not fetch transaction.")
            sys.exit(1)

        print("Extracting inner instructions...")
        raw_data_list = extract_inner_instructions(tx)

        print(f"Found {len(raw_data_list)} inner instructions")

        all_events = []
        for raw_data in raw_data_list:
            events = find_and_parse_events(raw_data)
            all_events.extend(events)

        if all_events:
            print(f"\nFound {len(all_events)} PumpFun event(s):")
            for event in all_events:
                display_event(event)
        else:
            print("\nNo PumpFun events found in this transaction.")
            print("Make sure the transaction interacts with the PumpFun program.")

    else:
        print("Usage:")
        print("  python scripts/parse_events.py --demo")
        print("  TX_SIGNATURE='5abc...' python scripts/parse_events.py")

    print()


if __name__ == "__main__":
    main()
