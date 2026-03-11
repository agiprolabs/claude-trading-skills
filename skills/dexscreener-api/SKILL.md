---
name: dexscreener-api
description: Free, no-auth multi-chain DEX pair data — prices, volume, liquidity, transactions, and token profiles
---

# DexScreener API — Free Multi-Chain DEX Data

DexScreener provides DEX pair data across 80+ chains with **no API key required**. Prices, volume, liquidity, transaction counts, and token profiles — all free. Best for quick lookups, cross-chain comparison, and lightweight monitoring.

## Quick Start

No authentication needed. Just make requests:

```python
import httpx

# Search for a token
resp = httpx.get("https://api.dexscreener.com/latest/dex/search", params={"q": "BONK"})
pairs = resp.json()["pairs"]
for p in pairs[:3]:
    print(f"{p['baseToken']['symbol']}/{p['quoteToken']['symbol']} on {p['chainId']}: ${p['priceUsd']}")
```

```bash
# Or with curl
curl "https://api.dexscreener.com/latest/dex/search?q=BONK"
```

## Base URL

`https://api.dexscreener.com`

No API key, no headers required. Rate limits: ~300 req/min for DEX data endpoints, 60 req/min for profile/boost endpoints.

## Core Endpoints

### Search Pairs

```python
# Search by token name, symbol, or address (returns ~30 pairs across all chains)
GET /latest/dex/search?q=BONK
GET /latest/dex/search?q=So11111111111111111111111111111111111111112
```

### Get Pairs by Chain + Pair Address

```python
# Single pair
GET /latest/dex/pairs/solana/PAIR_ADDRESS

# Multiple pairs (comma-separated)
GET /latest/dex/pairs/solana/PAIR1,PAIR2,PAIR3
```

### Get Pairs by Token Address

```python
# All pairs containing this token across all chains
GET /latest/dex/tokens/TOKEN_MINT_ADDRESS

# Chain-specific (v1)
GET /token-pairs/v1/solana/TOKEN_MINT

# Multiple tokens on one chain (v1)
GET /tokens/v1/solana/TOKEN1,TOKEN2,TOKEN3
```

### Token Profiles & Boosts

```python
# Latest token profiles (60 req/min)
GET /token-profiles/latest/v1

# Latest boosted tokens
GET /token-boosts/latest/v1

# Top boosted tokens (sorted by total boost amount)
GET /token-boosts/top/v1

# Token orders (ads, profile claims)
GET /orders/v1/solana/TOKEN_ADDRESS

# Community takeovers
GET /community-takeovers/latest/v1
```

## Pair Response Schema

```json
{
  "chainId": "solana",
  "dexId": "raydium",
  "url": "https://dexscreener.com/solana/PAIR_ADDR",
  "pairAddress": "3nMFwZX...",
  "labels": ["CLMM"],
  "baseToken": { "address": "So11...", "name": "Wrapped SOL", "symbol": "SOL" },
  "quoteToken": { "address": "EPjF...", "name": "USD Coin", "symbol": "USDC" },
  "priceNative": "86.08",
  "priceUsd": "86.08",
  "txns": {
    "m5":  { "buys": 25, "sells": 18 },
    "h1":  { "buys": 916, "sells": 1282 },
    "h6":  { "buys": 11309, "sells": 12661 },
    "h24": { "buys": 27974, "sells": 31475 }
  },
  "volume": { "m5": 41680, "h1": 6773038, "h6": 71628073, "h24": 167164493 },
  "priceChange": { "m5": -0.01, "h1": -0.36, "h6": 0.82, "h24": 0.25 },
  "liquidity": { "usd": 28168478, "base": 232348, "quote": 8167805 },
  "fdv": 8171740,
  "marketCap": 8171740,
  "pairCreatedAt": 1688106058000,
  "info": {
    "imageUrl": "https://cdn.dexscreener.com/...",
    "websites": [{ "url": "https://...", "label": "Website" }],
    "socials": [{ "url": "https://x.com/...", "type": "twitter" }]
  }
}
```

**Key notes:**
- `priceNative` and `priceUsd` are **strings** (preserves precision)
- `pairCreatedAt` is **milliseconds** (divide by 1000 for unix timestamp)
- `labels`: `"CLMM"` (concentrated), `"DLMM"` (dynamic), `"wp"` (whirlpool)
- `info` is optional — only present if the token profile has been claimed
- `fdv`/`marketCap` may be absent for tokens without supply data

## Common Patterns

### Quick Token Lookup

```python
def lookup_token(address: str) -> dict | None:
    """Get the best pair for a token by liquidity."""
    resp = httpx.get(f"https://api.dexscreener.com/latest/dex/tokens/{address}")
    pairs = resp.json().get("pairs", [])
    if not pairs:
        return None
    # Sort by liquidity (highest first)
    pairs.sort(key=lambda p: p.get("liquidity", {}).get("usd", 0), reverse=True)
    return pairs[0]
```

### Cross-Chain Price Check

```python
def find_best_price(symbol: str) -> list[dict]:
    """Find a token across all chains and compare prices."""
    resp = httpx.get("https://api.dexscreener.com/latest/dex/search", params={"q": symbol})
    pairs = resp.json().get("pairs", [])
    results = []
    for p in pairs:
        if p["baseToken"]["symbol"].upper() == symbol.upper():
            results.append({
                "chain": p["chainId"],
                "dex": p["dexId"],
                "price": float(p.get("priceUsd", 0)),
                "liquidity": p.get("liquidity", {}).get("usd", 0),
                "volume_24h": p.get("volume", {}).get("h24", 0),
            })
    return sorted(results, key=lambda x: x["liquidity"], reverse=True)
```

### Monitor New Tokens via Boosts

```python
def get_newly_boosted() -> list[dict]:
    """Get tokens that were recently boosted (paid promotion)."""
    resp = httpx.get("https://api.dexscreener.com/token-boosts/latest/v1")
    return [
        {
            "chain": t["chainId"],
            "address": t["tokenAddress"],
            "boost_amount": t.get("amount", 0),
            "total_boost": t.get("totalAmount", 0),
            "description": t.get("description", ""),
        }
        for t in resp.json()
    ]
```

### Buy/Sell Ratio Analysis

```python
def analyze_pressure(pair: dict) -> dict:
    """Analyze buy/sell pressure from transaction counts."""
    txns = pair.get("txns", {})
    result = {}
    for tf in ["m5", "h1", "h6", "h24"]:
        data = txns.get(tf, {})
        buys = data.get("buys", 0)
        sells = data.get("sells", 0)
        total = buys + sells
        result[tf] = {
            "buys": buys, "sells": sells, "total": total,
            "buy_ratio": buys / total if total > 0 else 0.5,
        }
    return result
```

## Supported Chains

Major chains: `solana`, `ethereum`, `base`, `arbitrum`, `bsc`, `polygon`, `avalanche`, `optimism`, `zksync`, `scroll`, `linea`, `tron`, `near`, `aptos`, `ton`, `sui`, `hyperliquid`

80+ chains total. The `chainId` matches the URL path on dexscreener.com.

## Limitations

- **No OHLCV/candle data** — Use Birdeye or SolanaTracker for historical candles
- **No pagination** — Search returns ~30 results max
- **No wallet/trader data** — Use Birdeye or Helius for wallet analysis
- **No token security data** — Use Birdeye `token_security` endpoint
- **Snapshot data only** — Current state, not historical time series
- **No WebSocket** — Polling only

## When to Use DexScreener vs Alternatives

| Need | Use |
|------|-----|
| Quick free token lookup | **DexScreener** |
| Cross-chain comparison | **DexScreener** |
| Historical OHLCV for backtesting | Birdeye or SolanaTracker |
| Wallet/trader analysis | Helius or SolanaTracker |
| Real-time streaming | Yellowstone gRPC or Birdeye WebSocket |
| Token security check | Birdeye or SolanaTracker risk score |

## Files

### References
- `references/endpoints.md` — Complete endpoint listing with response schemas
- `references/error_handling.md` — Rate limits, error codes, best practices

### Scripts
- `scripts/token_lookup.py` — Look up any token across all chains with liquidity analysis
- `scripts/boost_monitor.py` — Monitor newly boosted/promoted tokens
