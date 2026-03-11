#!/usr/bin/env python3
"""Monitor a Solana wallet for new swap transactions in real time.

Polls for new transactions at a configurable interval, detects swaps,
and prints trade alerts with token details from DexScreener. Includes
a --demo mode that simulates incoming trades.

Usage:
    python scripts/monitor_wallet.py <wallet_address>
    python scripts/monitor_wallet.py --demo

Dependencies:
    uv pip install httpx

Environment Variables:
    WALLET_ADDRESS: Wallet to monitor (optional if passed as argument)
    HELIUS_API_KEY: Helius API key for parsed transaction history
    SOLANA_RPC_URL: Fallback RPC URL if no Helius key (default: public mainnet)
"""

import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Install with: uv pip install httpx")
    sys.exit(1)

# ── Configuration ───────────────────────────────────────────────────
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
SOLANA_RPC_URL = os.getenv(
    "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
)
POLL_INTERVAL_SECONDS = 10
DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"

# Known program IDs for DEX swaps
SWAP_PROGRAMS = {
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter v6",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter v4",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca v1",
    "6MLxLqiXaaSUpkgMnWDTuejNZEz3kE7k2woyHGVFw319": "Meteora",
}

# Graceful shutdown
_running = True


def _handle_signal(signum: int, frame: object) -> None:
    global _running
    _running = False
    print("\nShutting down monitor...")


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Data Structures ────────────────────────────────────────────────
@dataclass
class SwapAlert:
    """A detected swap transaction."""
    signature: str
    timestamp: int
    dex: str
    direction: str  # "BUY" or "SELL"
    token_address: str
    token_symbol: str
    token_name: str
    amount_sol: float
    token_amount: float
    price_usd: Optional[float]
    liquidity_usd: Optional[float]
    market_cap_usd: Optional[float]


# ── API Functions ───────────────────────────────────────────────────
def fetch_recent_signatures(
    wallet: str, limit: int = 5
) -> list[dict]:
    """Fetch recent transaction signatures for a wallet.

    Args:
        wallet: Solana wallet address to monitor.
        limit: Number of recent signatures to fetch.

    Returns:
        List of signature objects with signature, slot, blockTime.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [wallet, {"limit": limit}],
    }

    rpc_url = SOLANA_RPC_URL
    if HELIUS_API_KEY:
        rpc_url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(rpc_url, json=payload)
        resp.raise_for_status()
        result = resp.json().get("result", [])
        return result


def fetch_parsed_transaction(signature: str) -> Optional[dict]:
    """Fetch and parse a transaction using Helius.

    Args:
        signature: Transaction signature to parse.

    Returns:
        Parsed transaction data, or None if parsing fails.
    """
    if not HELIUS_API_KEY:
        return _fetch_transaction_rpc(signature)

    url = f"https://api.helius.xyz/v0/transactions/?api-key={HELIUS_API_KEY}"
    with httpx.Client(timeout=15.0) as client:
        try:
            resp = client.post(url, json={"transactions": [signature]})
            resp.raise_for_status()
            results = resp.json()
            return results[0] if results else None
        except (httpx.HTTPStatusError, IndexError, KeyError):
            return None


def _fetch_transaction_rpc(signature: str) -> Optional[dict]:
    """Fallback: fetch transaction via standard RPC."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
        ],
    }
    with httpx.Client(timeout=15.0) as client:
        try:
            resp = client.post(SOLANA_RPC_URL, json=payload)
            resp.raise_for_status()
            return resp.json().get("result")
        except (httpx.HTTPStatusError, KeyError):
            return None


def fetch_token_info(token_address: str) -> dict:
    """Fetch token info from DexScreener.

    Args:
        token_address: Token mint address.

    Returns:
        Dict with symbol, name, priceUsd, liquidity, marketCap.
    """
    url = f"{DEXSCREENER_BASE}/tokens/{token_address}"
    with httpx.Client(timeout=10.0) as client:
        try:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
            pairs = data.get("pairs", [])
            if pairs:
                pair = pairs[0]
                base = pair.get("baseToken", {})
                return {
                    "symbol": base.get("symbol", "???"),
                    "name": base.get("name", "Unknown"),
                    "priceUsd": pair.get("priceUsd"),
                    "liquidity": pair.get("liquidity", {}).get("usd"),
                    "marketCap": pair.get("marketCap"),
                }
        except (httpx.HTTPStatusError, httpx.RequestError):
            pass
    return {"symbol": "???", "name": "Unknown", "priceUsd": None, "liquidity": None, "marketCap": None}


# ── Transaction Parsing ────────────────────────────────────────────
def detect_swap(tx_data: dict) -> Optional[dict]:
    """Detect if a transaction is a DEX swap.

    Args:
        tx_data: Parsed transaction data (Helius or RPC format).

    Returns:
        Dict with swap details, or None if not a swap.
    """
    if not tx_data:
        return None

    # Helius parsed format
    if "type" in tx_data:
        tx_type = tx_data.get("type", "")
        if tx_type == "SWAP":
            events = tx_data.get("events", {})
            swap = events.get("swap", {})
            if swap:
                token_inputs = swap.get("tokenInputs", [])
                token_outputs = swap.get("tokenOutputs", [])
                native_input = swap.get("nativeInput", {})
                native_output = swap.get("nativeOutput", {})

                # Determine direction
                if native_input and token_outputs:
                    # Spent SOL, got tokens = BUY
                    token = token_outputs[0] if token_outputs else {}
                    return {
                        "direction": "BUY",
                        "token_address": token.get("mint", ""),
                        "amount_sol": native_input.get("amount", 0) / 1e9,
                        "token_amount": token.get("amount", 0),
                        "dex": tx_data.get("source", "Unknown"),
                    }
                elif token_inputs and native_output:
                    # Spent tokens, got SOL = SELL
                    token = token_inputs[0] if token_inputs else {}
                    return {
                        "direction": "SELL",
                        "token_address": token.get("mint", ""),
                        "amount_sol": native_output.get("amount", 0) / 1e9,
                        "token_amount": token.get("amount", 0),
                        "dex": tx_data.get("source", "Unknown"),
                    }

    # RPC parsed format — check for known swap program IDs
    if "transaction" in tx_data:
        msg = tx_data.get("transaction", {}).get("message", {})
        instructions = msg.get("instructions", [])
        for ix in instructions:
            program_id = ix.get("programId", "")
            if program_id in SWAP_PROGRAMS:
                return {
                    "direction": "UNKNOWN",
                    "token_address": "",
                    "amount_sol": 0,
                    "token_amount": 0,
                    "dex": SWAP_PROGRAMS[program_id],
                }

    return None


# ── Alert Display ───────────────────────────────────────────────────
def print_alert(alert: SwapAlert) -> None:
    """Print a formatted swap alert."""
    sep = "-" * 60
    direction_icon = ">>>" if alert.direction == "BUY" else "<<<"
    print(f"\n{sep}")
    print(f"  {direction_icon} {alert.direction} DETECTED")
    print(f"{sep}")
    print(f"  Token:      {alert.token_symbol} ({alert.token_name})")
    print(f"  Mint:       {alert.token_address[:20]}...")
    print(f"  DEX:        {alert.dex}")
    print(f"  SOL amount: {alert.amount_sol:.4f} SOL")
    if alert.price_usd:
        print(f"  Price:      ${float(alert.price_usd):.8f}")
    if alert.liquidity_usd:
        print(f"  Liquidity:  ${alert.liquidity_usd:,.0f}")
    if alert.market_cap_usd:
        print(f"  Market cap: ${alert.market_cap_usd:,.0f}")
    print(f"  Tx:         {alert.signature[:30]}...")
    print(f"  Time:       {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(alert.timestamp))}")
    print(sep)


# ── Monitor Loop ────────────────────────────────────────────────────
def monitor_wallet(wallet: str) -> None:
    """Poll wallet for new transactions and alert on swaps.

    Args:
        wallet: Solana wallet address to monitor.
    """
    print(f"Monitoring wallet: {wallet}")
    print(f"Poll interval: {POLL_INTERVAL_SECONDS}s")
    print(f"Using: {'Helius API' if HELIUS_API_KEY else 'Public RPC (slower)'}")
    print("Press Ctrl+C to stop.\n")

    # Initialize with current latest signature
    last_seen_sig: Optional[str] = None
    try:
        sigs = fetch_recent_signatures(wallet, limit=1)
        if sigs:
            last_seen_sig = sigs[0]["signature"]
            print(f"Starting from signature: {last_seen_sig[:30]}...")
    except Exception as e:
        print(f"Warning: could not fetch initial signatures: {e}")

    poll_count = 0
    swaps_detected = 0

    while _running:
        poll_count += 1
        try:
            sigs = fetch_recent_signatures(wallet, limit=10)
        except Exception as e:
            print(f"[Poll {poll_count}] Error fetching signatures: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        # Find new signatures since last seen
        new_sigs: list[dict] = []
        for sig_obj in sigs:
            if sig_obj["signature"] == last_seen_sig:
                break
            new_sigs.append(sig_obj)

        if new_sigs:
            # Update last seen
            last_seen_sig = new_sigs[0]["signature"]

            for sig_obj in reversed(new_sigs):  # Process oldest first
                sig = sig_obj["signature"]
                block_time = sig_obj.get("blockTime", int(time.time()))

                # Fetch and parse transaction
                tx_data = fetch_parsed_transaction(sig)
                swap_info = detect_swap(tx_data)

                if swap_info:
                    token_addr = swap_info.get("token_address", "")
                    token_info = fetch_token_info(token_addr) if token_addr else {}

                    alert = SwapAlert(
                        signature=sig,
                        timestamp=block_time,
                        dex=swap_info.get("dex", "Unknown"),
                        direction=swap_info.get("direction", "UNKNOWN"),
                        token_address=token_addr,
                        token_symbol=token_info.get("symbol", "???"),
                        token_name=token_info.get("name", "Unknown"),
                        amount_sol=swap_info.get("amount_sol", 0),
                        token_amount=swap_info.get("token_amount", 0),
                        price_usd=token_info.get("priceUsd"),
                        liquidity_usd=token_info.get("liquidity"),
                        market_cap_usd=token_info.get("marketCap"),
                    )
                    print_alert(alert)
                    swaps_detected += 1

        # Status update every 6 polls (1 minute)
        if poll_count % 6 == 0:
            print(
                f"[{time.strftime('%H:%M:%S')}] "
                f"Polls: {poll_count} | Swaps detected: {swaps_detected}"
            )

        time.sleep(POLL_INTERVAL_SECONDS)

    print(f"\nMonitor stopped. Total polls: {poll_count}, Swaps detected: {swaps_detected}")


# ── Demo Mode ───────────────────────────────────────────────────────
def run_demo() -> None:
    """Simulate wallet monitoring with fake trade alerts."""
    print("[DEMO MODE] Simulating wallet monitoring with example trades\n")
    print("Monitoring wallet: DemoWa11etXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
    print("Press Ctrl+C to stop.\n")

    demo_alerts = [
        SwapAlert(
            signature="5xYz" + "A" * 80,
            timestamp=int(time.time()) - 120,
            dex="Jupiter v6",
            direction="BUY",
            token_address="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            token_symbol="BONK",
            token_name="Bonk",
            amount_sol=2.5,
            token_amount=50_000_000,
            price_usd="0.00002341",
            liquidity_usd=4_500_000,
            market_cap_usd=1_200_000_000,
        ),
        SwapAlert(
            signature="7kMn" + "B" * 80,
            timestamp=int(time.time()) - 60,
            dex="Raydium AMM",
            direction="BUY",
            token_address="EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
            token_symbol="WIF",
            token_name="dogwifhat",
            amount_sol=5.0,
            token_amount=3_200,
            price_usd="0.234",
            liquidity_usd=12_000_000,
            market_cap_usd=2_500_000_000,
        ),
        SwapAlert(
            signature="9pQr" + "C" * 80,
            timestamp=int(time.time()),
            dex="Jupiter v6",
            direction="SELL",
            token_address="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            token_symbol="BONK",
            token_name="Bonk",
            amount_sol=3.1,
            token_amount=50_000_000,
            price_usd="0.00002412",
            liquidity_usd=4_500_000,
            market_cap_usd=1_200_000_000,
        ),
    ]

    for i, alert in enumerate(demo_alerts):
        if not _running:
            break
        print(f"\n[Simulated delay: waiting for next trade...]")
        time.sleep(8)
        if not _running:
            break
        alert.timestamp = int(time.time())
        print_alert(alert)

    print("\n[DEMO] All simulated trades shown.")
    print("[DEMO] In live mode, monitoring continues until Ctrl+C.")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Main entry point."""
    args = sys.argv[1:]
    demo_mode = "--demo" in args

    if demo_mode:
        run_demo()
        return

    # Determine wallet address
    wallet = None
    for arg in args:
        if not arg.startswith("-"):
            wallet = arg
            break
    if not wallet:
        wallet = os.getenv("WALLET_ADDRESS", "")
    if not wallet:
        print("Usage: python scripts/monitor_wallet.py <wallet_address>")
        print("       python scripts/monitor_wallet.py --demo")
        print("Or set WALLET_ADDRESS environment variable.")
        sys.exit(1)

    if not HELIUS_API_KEY and SOLANA_RPC_URL == "https://api.mainnet-beta.solana.com":
        print("WARNING: Using public RPC endpoint. Set HELIUS_API_KEY for better")
        print("         performance and parsed transaction data.\n")

    monitor_wallet(wallet)


if __name__ == "__main__":
    main()
