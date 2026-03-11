# DeFiLlama API — Error Handling

## Rate Limits

| Tier | Limit | Monthly |
|------|-------|---------|
| Free | ~500 req / 5 min | Unlimited |
| API ($300/mo) | 1,000 req/min | 1M calls |

No rate limit headers are returned. HTTP 429 means you're rate limited.

## HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Process response |
| 400 | Bad request | Check coin IDs, parameters |
| 429 | Rate limited | Wait 30-60 seconds |
| 502 | Upstream error | Retry after 5 seconds |
| 504 | Gateway timeout | Response too large, use exclude params |

## Retry Strategy

```python
import time
import httpx

def llama_get(url: str, max_retries: int = 3) -> dict | list:
    """GET with retry for DeFiLlama endpoints."""
    for attempt in range(max_retries):
        try:
            resp = httpx.get(url, timeout=30.0)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                wait = 30.0 * (attempt + 1)
                print(f"Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                time.sleep(5.0 * (attempt + 1))
                continue

            resp.raise_for_status()
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                time.sleep(5.0)
                continue
            raise

    raise RuntimeError(f"Failed after {max_retries} retries: {url}")
```

## Common Issues

### 1. Large response payloads
`/protocols` and volume/fee overviews can return 10MB+. Always use filter params:
```python
resp = httpx.get("https://api.llama.fi/overview/dexs", params={
    "excludeTotalDataChart": "true",
    "excludeTotalDataChartBreakdown": "true",
})
```

### 2. Timestamps are seconds, not milliseconds
All DeFiLlama timestamps are unix seconds. Don't multiply by 1000.

### 3. Missing coin data
If a coin ID returns no data, check:
- Address format (lowercase for EVM, base58 for Solana)
- Chain prefix is correct
- Token has on-chain liquidity
- Try `searchWidth=24h` for illiquid tokens

### 4. Stale prices
Check the `timestamp` and `confidence` fields:
```python
import time

data = resp.json()["coins"].get(coin_id, {})
age = time.time() - data.get("timestamp", 0)
if age > 3600:  # older than 1 hour
    print("Warning: stale price data")
if data.get("confidence", 0) < 0.9:
    print("Warning: low confidence price")
```

### 5. Protocol slugs
Protocol slugs don't always match the display name:
- "Raydium" → `raydium`
- "Aave V3" → `aave-v3`
- "Uniswap V3" → `uniswap`

Use `/protocols` to find the correct `slug` field.

### 6. Chain name casing
Chain names in URLs are case-sensitive:
- Correct: `Solana`, `Ethereum`, `Arbitrum`
- Wrong: `solana`, `SOLANA`

This applies to `/overview/dexs/{chain}`, `/overview/fees/{chain}`, `/v2/historicalChainTvl/{chain}`.

## Caching Recommendations

| Data | Cache TTL | Reason |
|------|-----------|--------|
| Protocol list | 15-30 min | Changes slowly |
| TVL (current) | 5-15 min | Updates periodically |
| Historical TVL | 1 hour+ | Immutable history |
| Prices (current) | 1-5 min | Changes constantly |
| Prices (historical) | Forever | Immutable |
| Volume/Fee overviews | 15-30 min | Daily aggregation |
