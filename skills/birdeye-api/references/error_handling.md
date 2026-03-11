# Birdeye API — Error Handling & Rate Limits

## Error Responses

All errors return: `{ "success": false, "message": "..." }`

| Code | Meaning | Action |
|------|---------|--------|
| 400 | Bad Request | Check parameter format |
| 401 | Unauthorized | Invalid or missing API key |
| 403 | Forbidden | Tier lacks access to endpoint |
| 422 | Unprocessable Entity | Invalid param combination |
| 429 | Too Many Requests | Rate limit — back off |
| 500 | Internal Server Error | Retry with backoff |

### Common 422 Causes
- Passing both `before_time` and `after_time` to seek_by_time endpoints
- Invalid token address format
- Timeframe not supported for chain

## Rate Limits

Limits are **per account** (not per key or endpoint).

| Tier | Requests/sec | Notes |
|------|-------------|-------|
| Free | 1 | Very restrictive |
| Lite/Starter | 15 | Adequate for research |
| Premium | 50 (1000 rpm) | Most use cases |
| Business | 100-150 | Production workloads |

**Wallet endpoints**: Fixed at **30 rpm** regardless of tier, across all 7 wallet endpoints.

No rate limit headers are returned in responses — you must track your own usage.

## Retry Strategy

```python
import httpx
import time
import random

def birdeye_request(
    endpoint: str,
    params: dict,
    api_key: str,
    chain: str = "solana",
    max_retries: int = 3,
) -> dict:
    """Make a Birdeye API request with retry logic.

    Args:
        endpoint: API path (e.g., '/defi/price').
        params: Query parameters.
        api_key: Birdeye API key.
        chain: Chain identifier.
        max_retries: Max retry attempts.

    Returns:
        Parsed response data (the 'data' field).

    Raises:
        RuntimeError: On persistent failure.
    """
    headers = {
        "X-API-KEY": api_key,
        "x-chain": chain,
        "accept": "application/json",
    }
    url = f"https://public-api.birdeye.so{endpoint}"

    for attempt in range(max_retries + 1):
        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=30.0)

            if resp.status_code == 429:
                delay = (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limited. Retrying in {delay:.1f}s...")
                time.sleep(delay)
                continue

            if resp.status_code == 403:
                raise RuntimeError(
                    f"Forbidden: tier lacks access to {endpoint}. "
                    "Upgrade at birdeye.so"
                )

            resp.raise_for_status()
            data = resp.json()

            if not data.get("success"):
                raise RuntimeError(f"Birdeye error: {data.get('message', 'unknown')}")

            return data["data"]

        except httpx.TimeoutException:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise

    raise RuntimeError(f"Max retries exceeded for {endpoint}")
```

## CU Optimization Tips

### Use Multi-Price Instead of Loops
```python
# Bad: 10 CU per call × 20 tokens = 200 CU
for token in tokens:
    price = get_price(token)

# Good: Variable CU for batch
prices = get_multi_price(tokens)  # single call
```

### Cache Token Overview
`token_overview` (30 CU) returns price, volume, trades, wallets — often enough without needing separate calls.

### Use Appropriate Timeframes
For backtesting, choose the coarsest timeframe that meets your needs:
- 1D candles: 1000 candles = 2.7 years → 1 call (40 CU)
- 1H candles: 1000 candles = 41.6 days → ~9 calls for 1 year (360 CU)
- 15m candles: 1000 candles = 10.4 days → ~35 calls for 1 year (1400 CU)

### Free Tier Budget (30K CU/month)
| Use Case | Calls | CU Used |
|----------|-------|---------|
| 750 price checks | 750 | 7,500 |
| 100 OHLCV fetches | 100 | 4,000 |
| 50 token overviews | 50 | 1,500 |
| 20 security checks | 20 | 1,000 |
| **Total** | **920** | **14,000** |

### Starter Tier Budget (5M CU/month)
Enough for ~125K price calls or ~12.5K OHLCV fetches. Comfortable for daily research workflows.

## Pagination Patterns

### OHLCV Pagination (Time-Window Sliding)

```python
import time

def fetch_all_ohlcv(
    address: str,
    timeframe: str,
    start_ts: int,
    end_ts: int,
    api_key: str,
) -> list[dict]:
    """Fetch complete OHLCV history by paginating time windows."""
    all_candles = []
    current_start = start_ts

    # Seconds per candle (approximate)
    tf_seconds = {
        "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
        "1H": 3600, "4H": 14400, "1D": 86400, "1W": 604800,
    }
    window = tf_seconds.get(timeframe, 3600) * 1000  # 1000 candles

    while current_start < end_ts:
        current_end = min(current_start + window, end_ts)
        data = birdeye_request(
            "/defi/ohlcv",
            {"address": address, "type": timeframe,
             "time_from": current_start, "time_to": current_end},
            api_key,
        )
        items = data.get("items", [])
        all_candles.extend(items)

        if not items:
            break
        current_start = items[-1]["unixTime"] + 1
        time.sleep(0.1)  # respect rate limits

    return all_candles
```

### Trade Pagination (Time-Based)

```python
def fetch_trades_after(
    address: str, after_time: int, api_key: str, max_pages: int = 10
) -> list[dict]:
    """Fetch trades after a timestamp, paginating forward."""
    all_trades = []
    current_time = after_time

    for _ in range(max_pages):
        data = birdeye_request(
            "/defi/txs/token/seek_by_time",
            {"address": address, "after_time": current_time,
             "limit": 50, "tx_type": "swap"},
            api_key,
        )
        items = data.get("items", [])
        all_trades.extend(items)

        if not data.get("hasNext") or not items:
            break
        current_time = items[-1]["blockUnixTime"]
        time.sleep(0.1)

    return all_trades
```
