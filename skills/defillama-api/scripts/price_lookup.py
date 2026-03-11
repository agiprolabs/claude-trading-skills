#!/usr/bin/env python3
"""Multi-token price lookup with historical comparison via DeFiLlama.

Fetches current prices for multiple tokens and compares against
historical prices. Free, no authentication required.

Usage:
    python scripts/price_lookup.py
    TOKENS="SOL,JUP,BONK" python scripts/price_lookup.py

Dependencies:
    uv pip install httpx
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

COINS_BASE = "https://coins.llama.fi"

# Well-known Solana tokens
TOKEN_MAP = {
    "SOL":  "solana:So11111111111111111111111111111111111111112",
    "USDC": "solana:EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "solana:Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "JUP":  "solana:JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "BONK": "solana:DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "WIF":  "solana:EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "RAY":  "solana:4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "ORCA": "solana:orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "BTC":  "coingecko:bitcoin",
    "ETH":  "coingecko:ethereum",
}

TOKENS_INPUT = os.getenv("TOKENS", "SOL,JUP,BONK,WIF,RAY")
SELECTED_TOKENS = [t.strip().upper() for t in TOKENS_INPUT.split(",")]

# ── API Helper ──────────────────────────────────────────────────────


def llama_get(url: str, max_retries: int = 3) -> dict:
    """GET request to DeFiLlama with retry."""
    for attempt in range(max_retries):
        try:
            resp = httpx.get(url, timeout=30.0)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                time.sleep(30.0)
                continue
            if resp.status_code >= 500:
                time.sleep(5.0)
                continue
            resp.raise_for_status()
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                time.sleep(5.0)
                continue
            raise
    return {}


# ── Price Functions ─────────────────────────────────────────────────


def get_current_prices(coin_ids: list[str]) -> dict[str, dict]:
    """Get current prices for multiple coins.

    Args:
        coin_ids: List of DeFiLlama coin identifiers.

    Returns:
        Dict of coin_id -> {price, symbol, confidence, timestamp}.
    """
    joined = ",".join(coin_ids)
    data = llama_get(f"{COINS_BASE}/prices/current/{joined}")
    return data.get("coins", {})


def get_historical_prices(coin_ids: list[str], timestamp: int) -> dict[str, dict]:
    """Get prices at a historical timestamp.

    Args:
        coin_ids: List of DeFiLlama coin identifiers.
        timestamp: Unix timestamp (seconds).

    Returns:
        Dict of coin_id -> {price, symbol, confidence, timestamp}.
    """
    joined = ",".join(coin_ids)
    data = llama_get(f"{COINS_BASE}/prices/historical/{timestamp}/{joined}?searchWidth=12h")
    return data.get("coins", {})


def get_price_changes(coin_ids: list[str]) -> dict[str, float]:
    """Get percentage price changes.

    Args:
        coin_ids: List of DeFiLlama coin identifiers.

    Returns:
        Dict of coin_id -> percentage change.
    """
    joined = ",".join(coin_ids)
    data = llama_get(f"{COINS_BASE}/percentage/{joined}")
    return data.get("coins", {})


# ── Display ─────────────────────────────────────────────────────────


def print_report(
    selected: list[str],
    current: dict[str, dict],
    prices_7d: dict[str, dict],
    prices_30d: dict[str, dict],
) -> None:
    """Print price comparison report.

    Args:
        selected: List of token symbols.
        current: Current price data.
        prices_7d: 7-day ago prices.
        prices_30d: 30-day ago prices.
    """
    print(f"\n{'='*75}")
    print(f"TOKEN PRICE COMPARISON")
    print(f"{'='*75}")
    print(f"  {'Token':<8} {'Price':>14} {'7d Change':>12} {'30d Change':>12} {'Confidence':>12}")
    print(f"  {'─'*8} {'─'*14} {'─'*12} {'─'*12} {'─'*12}")

    for symbol in selected:
        coin_id = TOKEN_MAP.get(symbol)
        if not coin_id or coin_id not in current:
            print(f"  {symbol:<8} {'N/A':>14}")
            continue

        price = current[coin_id].get("price", 0)
        confidence = current[coin_id].get("confidence", 0)

        # 7d change
        price_7d = prices_7d.get(coin_id, {}).get("price", 0)
        change_7d = ((price / price_7d) - 1) * 100 if price_7d > 0 else 0

        # 30d change
        price_30d = prices_30d.get(coin_id, {}).get("price", 0)
        change_30d = ((price / price_30d) - 1) * 100 if price_30d > 0 else 0

        # Format price
        if price >= 100:
            price_str = f"${price:,.2f}"
        elif price >= 1:
            price_str = f"${price:.4f}"
        elif price >= 0.001:
            price_str = f"${price:.6f}"
        else:
            price_str = f"${price:.10f}"

        change_7d_str = f"{change_7d:+.1f}%" if price_7d > 0 else "N/A"
        change_30d_str = f"{change_30d:+.1f}%" if price_30d > 0 else "N/A"
        conf_str = f"{confidence:.2f}"

        print(f"  {symbol:<8} {price_str:>14} {change_7d_str:>12} {change_30d_str:>12} {conf_str:>12}")

    # Best/worst performers
    changes = {}
    for symbol in selected:
        coin_id = TOKEN_MAP.get(symbol)
        if not coin_id:
            continue
        price = current.get(coin_id, {}).get("price", 0)
        price_7d = prices_7d.get(coin_id, {}).get("price", 0)
        if price > 0 and price_7d > 0:
            changes[symbol] = ((price / price_7d) - 1) * 100

    if changes:
        best = max(changes, key=changes.get)
        worst = min(changes, key=changes.get)
        print(f"\n  7d Best:  {best} ({changes[best]:+.1f}%)")
        print(f"  7d Worst: {worst} ({changes[worst]:+.1f}%)")

    print()


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run price lookup and comparison."""
    # Resolve coin IDs
    coin_ids = []
    valid_tokens = []
    for symbol in SELECTED_TOKENS:
        if symbol in TOKEN_MAP:
            coin_ids.append(TOKEN_MAP[symbol])
            valid_tokens.append(symbol)
        elif symbol.startswith("solana:") or symbol.startswith("coingecko:"):
            coin_ids.append(symbol)
            valid_tokens.append(symbol)
        else:
            print(f"  Unknown token: {symbol} (use symbol name or full coin ID)")

    if not coin_ids:
        print("No valid tokens specified.")
        sys.exit(1)

    print(f"Looking up {len(coin_ids)} tokens...")

    # Timestamps
    now = datetime.now(tz=timezone.utc)
    ts_7d = int((now - timedelta(days=7)).timestamp())
    ts_30d = int((now - timedelta(days=30)).timestamp())

    # Fetch current and historical prices
    print("Fetching current prices...")
    current = get_current_prices(coin_ids)
    time.sleep(0.5)

    print("Fetching 7-day ago prices...")
    prices_7d = get_historical_prices(coin_ids, ts_7d)
    time.sleep(0.5)

    print("Fetching 30-day ago prices...")
    prices_30d = get_historical_prices(coin_ids, ts_30d)

    print_report(valid_tokens, current, prices_7d, prices_30d)


if __name__ == "__main__":
    main()
