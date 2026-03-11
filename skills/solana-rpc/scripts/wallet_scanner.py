#!/usr/bin/env python3
"""Scan a Solana wallet for all token holdings using direct RPC.

Fetches SOL balance and all SPL token accounts, then displays a
summary of holdings sorted by value (if price data available via
a simple DexScreener lookup).

Usage:
    python scripts/wallet_scanner.py
    WALLET_ADDRESS="YourWallet..." python scripts/wallet_scanner.py

Dependencies:
    uv pip install httpx

Environment Variables:
    SOLANA_RPC_URL: Solana RPC endpoint (default: public mainnet)
    WALLET_ADDRESS: Wallet public key to scan
"""

import os
import sys
import time
from typing import Any, Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")

if not WALLET_ADDRESS:
    print("Set WALLET_ADDRESS environment variable")
    print("  Example: WALLET_ADDRESS=\"YourWallet...\" python scripts/wallet_scanner.py")
    sys.exit(1)

# ── RPC Helper ──────────────────────────────────────────────────────


def rpc_call(method: str, params: Optional[list] = None) -> dict[str, Any]:
    """Make a JSON-RPC call to Solana.

    Args:
        method: RPC method name.
        params: Method parameters.

    Returns:
        The 'result' field from the response.

    Raises:
        RuntimeError: On RPC error.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or [],
    }

    for attempt in range(3):
        try:
            resp = httpx.post(RPC_URL, json=payload, timeout=30.0)

            if resp.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue

            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                err = data["error"]
                raise RuntimeError(f"RPC error: {err.get('message', 'unknown')}")

            return data.get("result", {})

        except httpx.TimeoutException:
            if attempt < 2:
                time.sleep(2.0)
                continue
            raise

    raise RuntimeError(f"RPC call {method} failed after retries")


def rpc_batch(calls: list[tuple[str, list]]) -> list[dict]:
    """Execute multiple RPC calls in a single HTTP request.

    Args:
        calls: List of (method, params) tuples.

    Returns:
        List of result dicts in the same order.
    """
    payload = [
        {"jsonrpc": "2.0", "id": i, "method": method, "params": params}
        for i, (method, params) in enumerate(calls)
    ]

    resp = httpx.post(RPC_URL, json=payload, timeout=30.0)
    resp.raise_for_status()
    results = resp.json()
    results.sort(key=lambda r: r.get("id", 0))
    return [r.get("result") for r in results]


# ── Token Scanning ──────────────────────────────────────────────────


def get_sol_balance(wallet: str) -> float:
    """Get SOL balance for a wallet.

    Args:
        wallet: Wallet public key.

    Returns:
        SOL balance.
    """
    result = rpc_call("getBalance", [wallet, {"commitment": "confirmed"}])
    lamports = result.get("value", 0)
    return lamports / 1e9


def get_token_accounts(wallet: str) -> list[dict]:
    """Get all SPL token accounts for a wallet.

    Args:
        wallet: Wallet public key.

    Returns:
        List of token account dicts with mint, amount, decimals.
    """
    # SPL Token program
    result = rpc_call("getTokenAccountsByOwner", [
        wallet,
        {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
        {"encoding": "jsonParsed"},
    ])

    tokens = []
    for acct in result.get("value", []):
        parsed = acct.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
        amount_info = parsed.get("tokenAmount", {})
        raw_amount = int(amount_info.get("amount", "0"))

        if raw_amount == 0:
            continue

        tokens.append({
            "mint": parsed.get("mint", ""),
            "account": acct.get("pubkey", ""),
            "amount": raw_amount,
            "decimals": amount_info.get("decimals", 0),
            "ui_amount": amount_info.get("uiAmount", 0),
        })

    # Also check Token-2022
    try:
        result_2022 = rpc_call("getTokenAccountsByOwner", [
            wallet,
            {"programId": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"},
            {"encoding": "jsonParsed"},
        ])
        for acct in result_2022.get("value", []):
            parsed = acct.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            amount_info = parsed.get("tokenAmount", {})
            raw_amount = int(amount_info.get("amount", "0"))
            if raw_amount == 0:
                continue
            tokens.append({
                "mint": parsed.get("mint", ""),
                "account": acct.get("pubkey", ""),
                "amount": raw_amount,
                "decimals": amount_info.get("decimals", 0),
                "ui_amount": amount_info.get("uiAmount", 0),
                "token_2022": True,
            })
    except Exception:
        pass  # Token-2022 query may fail on some providers

    return tokens


def get_prices_dexscreener(mints: list[str]) -> dict[str, float]:
    """Get USD prices for tokens from DexScreener (free, no auth).

    Args:
        mints: List of token mint addresses.

    Returns:
        Dict of mint -> USD price.
    """
    prices = {}
    # DexScreener supports up to 30 addresses per call
    for i in range(0, len(mints), 30):
        batch = mints[i:i + 30]
        joined = ",".join(batch)
        try:
            resp = httpx.get(
                f"https://api.dexscreener.com/tokens/v1/solana/{joined}",
                timeout=15.0,
            )
            if resp.status_code == 200:
                pairs = resp.json() if isinstance(resp.json(), list) else resp.json().get("pairs", [])
                # Group by base token, take highest liquidity pair
                for pair in pairs:
                    mint = pair.get("baseToken", {}).get("address", "")
                    price = float(pair.get("priceUsd", "0") or "0")
                    liq = (pair.get("liquidity") or {}).get("usd", 0) or 0
                    if mint and price > 0:
                        if mint not in prices or liq > prices.get(f"_liq_{mint}", 0):
                            prices[mint] = price
                            prices[f"_liq_{mint}"] = liq
            time.sleep(1.0)
        except Exception:
            pass

    # Clean up liquidity tracking keys
    return {k: v for k, v in prices.items() if not k.startswith("_liq_")}


# ── Display ─────────────────────────────────────────────────────────


def format_usd(value: float) -> str:
    """Format a USD value for display."""
    if abs(value) >= 1_000_000:
        return f"${value / 1e6:.2f}M"
    elif abs(value) >= 1_000:
        return f"${value / 1e3:.2f}K"
    return f"${value:.2f}"


def print_report(
    wallet: str,
    sol_balance: float,
    tokens: list[dict],
    prices: dict[str, float],
) -> None:
    """Print formatted wallet scan report.

    Args:
        wallet: Wallet address.
        sol_balance: SOL balance.
        tokens: List of token holdings.
        prices: Dict of mint -> USD price.
    """
    # SOL price
    sol_mint = "So11111111111111111111111111111111111111112"
    sol_price = prices.get(sol_mint, 0)
    sol_value = sol_balance * sol_price

    print(f"\n{'='*60}")
    print(f"WALLET SCAN")
    print(f"{'='*60}")
    print(f"  Address: {wallet}")
    print(f"  SOL:     {sol_balance:.4f} SOL", end="")
    if sol_value:
        print(f" ({format_usd(sol_value)})")
    else:
        print()
    print(f"  Tokens:  {len(tokens)} non-zero holdings")

    if not tokens:
        print("\n  No token holdings found.")
        return

    # Enrich with prices and sort by value
    enriched = []
    for t in tokens:
        price = prices.get(t["mint"], 0)
        value = t["ui_amount"] * price if price else 0
        enriched.append({**t, "price": price, "value": value})

    enriched.sort(key=lambda t: t["value"], reverse=True)

    total_value = sol_value + sum(t["value"] for t in enriched)

    print(f"\n--- Token Holdings ---")
    print(f"  {'Mint':<20} {'Amount':>14} {'Price':>12} {'Value':>12}")
    print(f"  {'─'*20} {'─'*14} {'─'*12} {'─'*12}")

    displayed = 0
    for t in enriched:
        mint_short = t["mint"][:8] + "..." + t["mint"][-4:]
        amount_str = f"{t['ui_amount']:.4f}" if t["ui_amount"] < 1e6 else f"{t['ui_amount']:,.0f}"

        if t["price"]:
            price_str = f"${t['price']:.6f}" if t["price"] < 0.01 else f"${t['price']:.4f}"
            value_str = format_usd(t["value"])
        else:
            price_str = "—"
            value_str = "—"

        t2022 = " [T22]" if t.get("token_2022") else ""
        print(f"  {mint_short:<20} {amount_str:>14} {price_str:>12} {value_str:>12}{t2022}")

        displayed += 1
        if displayed >= 20:
            remaining = len(enriched) - displayed
            if remaining > 0:
                print(f"\n  ... and {remaining} more tokens (showing top 20 by value)")
            break

    if total_value > 0:
        print(f"\n  Total Portfolio Value: {format_usd(total_value)}")
        print(f"    SOL:    {format_usd(sol_value)} ({sol_value / total_value * 100:.1f}%)")
        token_value = total_value - sol_value
        print(f"    Tokens: {format_usd(token_value)} ({token_value / total_value * 100:.1f}%)")

    print()


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run wallet scanner."""
    print(f"Scanning wallet: {WALLET_ADDRESS}")
    print(f"RPC: {RPC_URL[:40]}...")

    print("Fetching SOL balance...")
    sol_balance = get_sol_balance(WALLET_ADDRESS)

    print("Fetching token accounts...")
    tokens = get_token_accounts(WALLET_ADDRESS)

    # Get prices from DexScreener (free, no auth)
    prices: dict[str, float] = {}
    if tokens:
        mints = list(set(t["mint"] for t in tokens))
        # Add SOL for price reference
        mints.append("So11111111111111111111111111111111111111112")
        print(f"Fetching prices for {len(mints)} tokens...")
        prices = get_prices_dexscreener(mints)

    print_report(WALLET_ADDRESS, sol_balance, tokens, prices)


if __name__ == "__main__":
    main()
