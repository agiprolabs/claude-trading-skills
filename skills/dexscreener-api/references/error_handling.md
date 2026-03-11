# DexScreener API — Error Handling & Rate Limits

## Rate Limits

| Endpoint Group | Limit | Scope |
|----------------|-------|-------|
| DEX data (`/latest/dex/*`, `/tokens/v1/*`, `/token-pairs/v1/*`) | ~300 req/min | Per IP |
| Token profiles & boosts (`/token-profiles/*`, `/token-boosts/*`) | ~60 req/min | Per IP |
| Orders & takeovers (`/orders/*`, `/community-takeovers/*`) | ~60 req/min | Per IP |

No rate limit headers are returned. Limits are enforced silently — you get HTTP 429 when exceeded.

## HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Process response |
| 400 | Bad request | Check parameters, address format |
| 404 | Not found | Pair/token doesn't exist or has no DEX listings |
| 429 | Rate limited | Back off, wait 10-30 seconds |
| 500 | Server error | Retry after 5 seconds, max 3 attempts |
| 503 | Service unavailable | Retry after 30 seconds |

## Error Response Format

DexScreener doesn't return structured error bodies. Non-200 responses may have empty bodies or plain text. Always check status code first.

## Retry Strategy

```python
import time
import httpx

def dexscreener_get(url: str, max_retries: int = 3) -> dict:
    """GET with exponential backoff for rate limits."""
    for attempt in range(max_retries):
        resp = httpx.get(url, timeout=15.0)

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 429:
            wait = 10.0 * (attempt + 1)
            print(f"Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue

        if resp.status_code >= 500:
            time.sleep(5.0 * (attempt + 1))
            continue

        # 4xx (not 429) — don't retry
        resp.raise_for_status()

    raise RuntimeError(f"Failed after {max_retries} retries: {url}")
```

## Common Gotchas

### 1. String prices, not numbers
`priceNative` and `priceUsd` are **strings**. Always cast:
```python
price = float(pair.get("priceUsd", "0"))
```

### 2. Missing fields
- `fdv`, `marketCap` — absent for tokens without supply data
- `info` — only present if token profile has been claimed
- `liquidity` — may be `None` or `{"usd": 0}` for dead pools

Always use `.get()` with defaults:
```python
liq = pair.get("liquidity", {}).get("usd", 0) or 0
```

### 3. Millisecond timestamps
`pairCreatedAt` is milliseconds, not seconds:
```python
from datetime import datetime, timezone
created = datetime.fromtimestamp(pair["pairCreatedAt"] / 1000, tz=timezone.utc)
```

### 4. No pagination
Search returns ~30 results max. If you need exhaustive results, use the token address endpoint instead of search.

### 5. Duplicate pairs across DEXes
A token may have pairs on Raydium, Orca, and Meteora simultaneously. Filter by `dexId` or sort by liquidity to find the primary pair:
```python
pairs.sort(key=lambda p: p.get("liquidity", {}).get("usd", 0) or 0, reverse=True)
primary = pairs[0]
```

### 6. Cross-chain ambiguity
Searching by symbol (e.g., "USDC") returns pairs from many chains. Filter by `chainId`:
```python
solana_pairs = [p for p in pairs if p["chainId"] == "solana"]
```

## Batch Request Optimization

When looking up multiple tokens, use comma-separated addresses instead of individual requests:

```python
# Bad: 10 requests
for addr in addresses:
    resp = httpx.get(f"https://api.dexscreener.com/latest/dex/tokens/{addr}")

# Good: 1 request (max 30 addresses)
joined = ",".join(addresses[:30])
resp = httpx.get(f"https://api.dexscreener.com/tokens/v1/solana/{joined}")
```

## No Historical Data

DexScreener provides snapshot data only. For historical OHLCV, use:
- **Birdeye** — Solana OHLCV with pagination
- **SolanaTracker** — 1-second resolution OHLCV
- **CoinGecko** — Long-term historical (years)
