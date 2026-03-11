#!/usr/bin/env python3
"""Fetch current crypto market data from the CoinGecko API.

Demonstrates fetching top coins by market cap, trending tokens, and global
market statistics. Supports --demo mode that uses embedded sample data so
no API key or network access is required.

Usage:
    python scripts/fetch_market_data.py              # Live API calls
    python scripts/fetch_market_data.py --demo        # Use sample data

Dependencies:
    uv pip install httpx

Environment Variables:
    COINGECKO_API_KEY: (Optional) CoinGecko Pro API key for higher rate limits.
                       Free tier (30 calls/min) is used when not set.
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Optional

try:
    import httpx
except ImportError:
    print("httpx is required. Install with: uv pip install httpx")
    sys.exit(1)

# ── Configuration ───────────────────────────────────────────────────
API_KEY = os.getenv("COINGECKO_API_KEY", "")
if API_KEY:
    BASE_URL = "https://pro-api.coingecko.com/api/v3"
    HEADERS: dict[str, str] = {"x-cg-pro-api-key": API_KEY}
else:
    BASE_URL = "https://api.coingecko.com/api/v3"
    HEADERS = {}

TOP_N = 15  # Number of top coins to fetch

# ── Demo Data ───────────────────────────────────────────────────────
DEMO_MARKETS = [
    {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin",
     "current_price": 97250.00, "market_cap": 1920000000000,
     "market_cap_rank": 1, "total_volume": 38000000000,
     "price_change_percentage_24h": 1.23, "circulating_supply": 19800000,
     "ath": 108268.00, "ath_date": "2024-12-17T15:02:41.429Z"},
    {"id": "ethereum", "symbol": "eth", "name": "Ethereum",
     "current_price": 3450.00, "market_cap": 415000000000,
     "market_cap_rank": 2, "total_volume": 18000000000,
     "price_change_percentage_24h": -0.45, "circulating_supply": 120000000,
     "ath": 4878.26, "ath_date": "2021-11-10T14:24:19.604Z"},
    {"id": "solana", "symbol": "sol", "name": "Solana",
     "current_price": 185.50, "market_cap": 89000000000,
     "market_cap_rank": 5, "total_volume": 4200000000,
     "price_change_percentage_24h": 4.78, "circulating_supply": 480000000,
     "ath": 293.31, "ath_date": "2025-01-19T11:15:00.000Z"},
    {"id": "ripple", "symbol": "xrp", "name": "XRP",
     "current_price": 2.35, "market_cap": 135000000000,
     "market_cap_rank": 3, "total_volume": 8500000000,
     "price_change_percentage_24h": 0.67, "circulating_supply": 57000000000,
     "ath": 3.40, "ath_date": "2018-01-07T00:00:00.000Z"},
    {"id": "binancecoin", "symbol": "bnb", "name": "BNB",
     "current_price": 680.00, "market_cap": 98000000000,
     "market_cap_rank": 4, "total_volume": 1800000000,
     "price_change_percentage_24h": -0.12, "circulating_supply": 144000000,
     "ath": 793.35, "ath_date": "2024-12-04T10:35:00.000Z"},
]

DEMO_TRENDING = {
    "coins": [
        {"item": {"id": "pepe", "name": "Pepe", "symbol": "PEPE",
                  "market_cap_rank": 25, "score": 0}},
        {"item": {"id": "bonk", "name": "Bonk", "symbol": "BONK",
                  "market_cap_rank": 65, "score": 1}},
        {"item": {"id": "dogwifcoin", "name": "dogwifhat", "symbol": "WIF",
                  "market_cap_rank": 80, "score": 2}},
        {"item": {"id": "render-token", "name": "Render", "symbol": "RENDER",
                  "market_cap_rank": 35, "score": 3}},
        {"item": {"id": "sui", "name": "Sui", "symbol": "SUI",
                  "market_cap_rank": 15, "score": 4}},
    ]
}

DEMO_GLOBAL = {
    "data": {
        "active_cryptocurrencies": 15320,
        "markets": 1120,
        "total_market_cap": {"usd": 3250000000000},
        "total_volume": {"usd": 125000000000},
        "market_cap_percentage": {"btc": 56.2, "eth": 12.8, "usdt": 4.1},
        "market_cap_change_percentage_24h_usd": 1.85,
        "updated_at": 1741564800,
    }
}


# ── API Functions ───────────────────────────────────────────────────
def cg_get(endpoint: str, params: Optional[dict[str, Any]] = None,
           max_retries: int = 3) -> Any:
    """Make a GET request to the CoinGecko API with retry on rate limit.

    Args:
        endpoint: API path (e.g., "/coins/markets").
        params: Query parameters.
        max_retries: Number of retries on 429 responses.

    Returns:
        Parsed JSON response.

    Raises:
        httpx.HTTPStatusError: On non-2xx, non-429 response.
        RuntimeError: If max retries exceeded.
    """
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(max_retries):
        resp = httpx.get(url, params=params or {}, headers=HEADERS, timeout=15.0)
        if resp.status_code == 429:
            wait = 2 ** attempt * 10
            print(f"  Rate limited, waiting {wait}s (attempt {attempt + 1})...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Rate limited after {max_retries} retries on {endpoint}")


def fetch_top_coins(n: int = TOP_N) -> list[dict[str, Any]]:
    """Fetch top N coins by market cap."""
    return cg_get("/coins/markets", params={
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": str(n),
        "page": "1",
        "sparkline": "false",
        "price_change_percentage": "24h,7d",
    })


def fetch_trending() -> dict[str, Any]:
    """Fetch trending coins from the last 24 hours."""
    return cg_get("/search/trending")


def fetch_global() -> dict[str, Any]:
    """Fetch global crypto market statistics."""
    return cg_get("/global")


# ── Display Functions ───────────────────────────────────────────────
def display_top_coins(coins: list[dict[str, Any]]) -> None:
    """Print a formatted table of top coins."""
    print("\n" + "=" * 75)
    print("TOP COINS BY MARKET CAP")
    print("=" * 75)
    print(f"{'#':>3}  {'Symbol':<7} {'Price':>12}  {'Market Cap':>14}  "
          f"{'24h Vol':>12}  {'24h %':>7}")
    print("-" * 75)
    for coin in coins:
        rank = coin.get("market_cap_rank", "?")
        symbol = coin["symbol"].upper()
        price = coin["current_price"]
        mcap = coin["market_cap"]
        vol = coin["total_volume"]
        chg = coin.get("price_change_percentage_24h", 0) or 0

        # Format market cap and volume
        mcap_str = f"${mcap / 1e9:.1f}B" if mcap >= 1e9 else f"${mcap / 1e6:.0f}M"
        vol_str = f"${vol / 1e9:.1f}B" if vol >= 1e9 else f"${vol / 1e6:.0f}M"

        if price >= 1000:
            price_str = f"${price:,.0f}"
        elif price >= 1:
            price_str = f"${price:,.2f}"
        else:
            price_str = f"${price:.6f}"

        print(f"{rank:>3}  {symbol:<7} {price_str:>12}  {mcap_str:>14}  "
              f"{vol_str:>12}  {chg:>+6.1f}%")


def display_trending(data: dict[str, Any]) -> None:
    """Print trending coins."""
    print("\n" + "=" * 50)
    print("TRENDING COINS (Last 24h)")
    print("=" * 50)
    for item in data.get("coins", []):
        coin = item["item"]
        rank = coin.get("market_cap_rank") or "?"
        print(f"  #{str(rank):>5}  {coin['name']} ({coin['symbol']})")


def display_global(data: dict[str, Any]) -> None:
    """Print global market statistics."""
    g = data["data"]
    total_mcap = g["total_market_cap"]["usd"]
    total_vol = g["total_volume"]["usd"]
    btc_dom = g["market_cap_percentage"].get("btc", 0)
    eth_dom = g["market_cap_percentage"].get("eth", 0)
    chg_24h = g.get("market_cap_change_percentage_24h_usd", 0)

    print("\n" + "=" * 50)
    print("GLOBAL CRYPTO MARKET")
    print("=" * 50)
    print(f"  Total Market Cap:     ${total_mcap / 1e12:.2f}T  ({chg_24h:+.1f}% 24h)")
    print(f"  Total 24h Volume:     ${total_vol / 1e9:.0f}B")
    print(f"  BTC Dominance:        {btc_dom:.1f}%")
    print(f"  ETH Dominance:        {eth_dom:.1f}%")
    print(f"  Active Coins:         {g.get('active_cryptocurrencies', 0):,}")
    print(f"  Active Exchanges:     {g.get('markets', 0):,}")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run the market data fetch and display pipeline."""
    parser = argparse.ArgumentParser(description="Fetch CoinGecko market data")
    parser.add_argument("--demo", action="store_true",
                        help="Use embedded sample data instead of live API")
    args = parser.parse_args()

    if args.demo:
        print("[DEMO MODE] Using embedded sample data\n")
        markets = DEMO_MARKETS
        trending = DEMO_TRENDING
        global_data = DEMO_GLOBAL
    else:
        print("Fetching data from CoinGecko API...\n")
        try:
            markets = fetch_top_coins()
            time.sleep(2)  # Respect rate limit
            trending = fetch_trending()
            time.sleep(2)
            global_data = fetch_global()
        except httpx.HTTPStatusError as e:
            print(f"API error: {e.response.status_code} — {e.response.text[:200]}")
            sys.exit(1)
        except httpx.ConnectError:
            print("Connection error. Check your internet connection.")
            sys.exit(1)

    display_global(global_data)
    display_top_coins(markets)
    display_trending(trending)
    print()


if __name__ == "__main__":
    main()
