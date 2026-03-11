# Data Sources — APIs and On-Chain Methods for Liquidity Data

## DexScreener (Free, No Auth)

Best for: Quick pool discovery, basic liquidity metrics, multi-chain support.

### Get Pairs by Token

- **Endpoint**: `GET https://api.dexscreener.com/tokens/v1/solana/{tokenAddress}`
- **Rate Limit**: 60 requests/minute
- **Auth**: None required

**Response fields relevant to liquidity**:

| Field | Type | Description |
|-------|------|-------------|
| `pairAddress` | string | On-chain pool address |
| `dexId` | string | DEX name (raydium, orca, meteora) |
| `liquidity.usd` | number | Total pool liquidity in USD |
| `liquidity.base` | number | Base token reserve |
| `liquidity.quote` | number | Quote token reserve |
| `volume.h24` | number | 24h trading volume in USD |
| `priceUsd` | string | Current price in USD |
| `pairCreatedAt` | number | Pool creation timestamp (ms) |
| `labels` | array | Tags like "v2", "v3" |
| `fdv` | number | Fully diluted valuation |

**Example**:

```python
import httpx

def get_dexscreener_pools(mint: str) -> list[dict]:
    """Fetch all pools for a token from DexScreener."""
    resp = httpx.get(
        f"https://api.dexscreener.com/tokens/v1/solana/{mint}",
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
```

### Search Pairs

- **Endpoint**: `GET https://api.dexscreener.com/latest/dex/search?q={query}`
- **Use case**: Find pools by token name/symbol when you do not have the mint address

### Get Pair by Address

- **Endpoint**: `GET https://api.dexscreener.com/latest/dex/pairs/solana/{pairAddress}`
- **Use case**: Get details for a specific pool

## Jupiter Quote API (Free, No Auth)

Best for: Empirical slippage measurement, aggregated across all pools.

### Get Quote

- **Endpoint**: `GET https://api.jup.ag/quote/v1`
- **Rate Limit**: Generous but undocumented; use 10 req/s as safe limit

**Parameters**:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `inputMint` | Yes | Input token mint address |
| `outputMint` | Yes | Output token mint address |
| `amount` | Yes | Input amount in smallest unit (lamports for SOL) |
| `slippageBps` | No | Max slippage tolerance in basis points (default 50) |
| `onlyDirectRoutes` | No | If true, no intermediate tokens |

**Response fields relevant to liquidity**:

| Field | Type | Description |
|-------|------|-------------|
| `outAmount` | string | Expected output in smallest unit |
| `priceImpactPct` | string | Price impact as decimal string |
| `routePlan` | array | Routing details (which pools, percentages) |
| `routePlan[].percent` | number | Percentage routed through this pool |
| `routePlan[].swapInfo.ammKey` | string | Pool address used |

**Example — Building a slippage curve**:

```python
import httpx

SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS = 1_000_000_000

def get_jupiter_quote(token_mint: str, sol_amount: float) -> dict | None:
    """Get Jupiter quote for a specific trade size."""
    resp = httpx.get(
        "https://api.jup.ag/quote/v1",
        params={
            "inputMint": SOL_MINT,
            "outputMint": token_mint,
            "amount": str(int(sol_amount * LAMPORTS)),
            "slippageBps": 5000,
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    return resp.json()
```

**Extracting routing info**:

```python
def parse_route_pools(quote: dict) -> list[dict]:
    """Extract pool routing details from Jupiter quote."""
    pools = []
    for step in quote.get("routePlan", []):
        info = step.get("swapInfo", {})
        pools.append({
            "amm": info.get("label", "unknown"),
            "pool": info.get("ammKey", ""),
            "percent": step.get("percent", 0),
            "in_amount": int(info.get("inAmount", 0)),
            "out_amount": int(info.get("outAmount", 0)),
        })
    return pools
```

## Birdeye API (API Key Required)

Best for: Detailed pool data, historical volume, trade counts.

### Token Trade Data

- **Endpoint**: `GET https://public-api.birdeye.so/defi/v3/token/trade-data/single`
- **Auth**: Header `X-API-KEY: {key}`, or `x-chain: solana`
- **Rate Limit**: 100/min (free), 1000/min (paid)

**Parameters**: `address` (token mint)

**Response includes**: price, volume (24h, buy/sell split), trade count, liquidity, unique wallets.

### Token Markets (Pool Listings)

- **Endpoint**: `GET https://public-api.birdeye.so/defi/v2/markets`
- **Parameters**: `address` (token mint), `sort_by`, `sort_type`
- **Returns**: List of pools with liquidity, volume, source (DEX name)

**Example**:

```python
import httpx
import os

def get_birdeye_pools(mint: str) -> list[dict]:
    """Fetch pool listings from Birdeye."""
    api_key = os.getenv("BIRDEYE_API_KEY", "")
    if not api_key:
        raise ValueError("Set BIRDEYE_API_KEY environment variable")

    resp = httpx.get(
        "https://public-api.birdeye.so/defi/v2/markets",
        params={"address": mint},
        headers={"X-API-KEY": api_key, "x-chain": "solana"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("data", {}).get("items", [])
```

## On-Chain Pool Data (RPC Only)

Best for: LP lock status, exact reserves, pool account verification.

### Raydium V4 Pool State

Read the pool state account to get exact reserves:

```python
import httpx
import base64
import struct

def get_raydium_reserves(pool_address: str, rpc_url: str) -> dict:
    """Fetch Raydium V4 pool reserves from on-chain data.

    Note: This is simplified. Full implementation requires
    reading the associated token vault accounts.
    """
    resp = httpx.post(
        rpc_url,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [pool_address, {"encoding": "base64"}],
        },
        timeout=10,
    )
    data = resp.json()
    # Pool state account contains vault addresses at known offsets
    # Read vault token balances for actual reserves
    return data
```

### LP Token Analysis

Check LP token distribution to assess rug risk:

1. Get the LP mint address from the pool state
2. Query `getTokenLargestAccounts` for the LP mint
3. Check if the largest holder is a known burn address or lock program

```python
BURN_ADDRESSES = {
    "1111111111111111111111111111111111",  # System program (burned)
}

LOCK_PROGRAMS = {
    "2r5VekMNiWPzi1pWwvJczrdPaZnJG59u91unSrTunwJg",  # Raydium LP locker
}
```

## Source Selection Guide

| Use Case | Primary Source | Fallback |
|----------|---------------|----------|
| Pool discovery | DexScreener | Birdeye |
| Quick liquidity check | DexScreener | Jupiter quote |
| Slippage estimation | Jupiter Quote API | Manual calculation |
| Historical volume | Birdeye | DexScreener (24h only) |
| LP lock status | On-chain RPC | N/A |
| Exact reserves | On-chain RPC | DexScreener liquidity.base/quote |
| Multi-pool routing | Jupiter Quote API | N/A |
| Cross-chain comparison | DexScreener | CoinGecko |

## Rate Limit Management

```python
import time
from collections import deque

class RateLimiter:
    """Simple sliding-window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window = window_seconds
        self.timestamps: deque[float] = deque()

    def wait_if_needed(self) -> None:
        now = time.time()
        while self.timestamps and now - self.timestamps[0] > self.window:
            self.timestamps.popleft()
        if len(self.timestamps) >= self.max_requests:
            sleep_time = self.window - (now - self.timestamps[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
        self.timestamps.append(time.time())
```
