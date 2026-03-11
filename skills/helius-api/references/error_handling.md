# Helius API — Error Handling & Rate Limits

## Rate Limits by Plan

| Plan | RPC req/s | DAS req/s | Enhanced req/s | Webhook events |
|------|-----------|-----------|---------------|----------------|
| Free | 10 | 2 | 2 | 1 credit/event |
| Developer ($49) | 50 | 10 | 10 | 1 credit/event |
| Business ($499) | 200 | 50 | 50 | 1 credit/event |
| Professional ($999) | 500 | 100 | 100 | 1 credit/event |

## Credit Costs

| API | Credits per Call |
|-----|-----------------|
| Standard RPC | 1 |
| getProgramAccounts | 10 |
| DAS methods | 10 |
| Enhanced Transactions | 100 |
| Webhook management | 100 |
| Webhook event delivery | 1 |
| Priority Fee API | 1 |
| ZK Compression | 10 (getValidityProofs: 100) |
| LaserStream/Enhanced WS | 3 per 0.1 MB |

Additional credits: $5 per 1M across all plans.

## HTTP Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Process response |
| 400 | Bad request | Check request format/params |
| 401 | Unauthorized | Check API key |
| 404 | Not found | Check endpoint URL |
| 429 | Rate limited | Back off and retry |
| 500 | Server error | Retry with backoff |
| 502/503 | Service unavailable | Retry with backoff |

## JSON-RPC Errors

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32600,
    "message": "Invalid request"
  },
  "id": 1
}
```

| Code | Meaning |
|------|---------|
| -32600 | Invalid request (malformed JSON-RPC) |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |
| -32000 | Server error (Solana RPC specific) |

## Retry Strategy

```python
import httpx
import time
import random

def helius_request(
    url: str,
    payload: dict,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> dict:
    """Make a Helius API request with exponential backoff.

    Args:
        url: Full endpoint URL with API key.
        payload: Request body.
        max_retries: Max retry attempts.
        base_delay: Initial delay in seconds.

    Returns:
        Parsed JSON response.

    Raises:
        httpx.HTTPStatusError: After all retries exhausted.
    """
    for attempt in range(max_retries + 1):
        try:
            resp = httpx.post(url, json=payload, timeout=30.0)

            if resp.status_code == 429:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                print(f"Rate limited. Retrying in {delay:.1f}s...")
                time.sleep(delay)
                continue

            resp.raise_for_status()
            return resp.json()

        except httpx.TimeoutException:
            if attempt < max_retries:
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise

        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < max_retries:
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise

    raise RuntimeError("Max retries exceeded")
```

## Pagination Best Practices

### DAS API Pagination

```python
def paginate_das(rpc_url: str, method: str, params: dict) -> list:
    """Paginate through all results from a DAS method."""
    all_items = []
    page = 1

    while True:
        params["page"] = page
        params["limit"] = 1000  # max per page

        resp = helius_request(rpc_url, {
            "jsonrpc": "2.0", "id": 1,
            "method": method,
            "params": params,
        })

        items = resp.get("result", {}).get("items", [])
        all_items.extend(items)

        if len(items) < 1000:
            break  # last page
        page += 1

        time.sleep(0.5)  # respect rate limits

    return all_items
```

### Enhanced Transactions Pagination

```python
def paginate_history(api_key: str, address: str, limit: int = 1000) -> list:
    """Paginate through wallet transaction history."""
    all_txns = []
    before_sig = None

    while len(all_txns) < limit:
        params = {"api-key": api_key, "limit": 100}
        if before_sig:
            params["before-signature"] = before_sig

        url = f"https://api-mainnet.helius-rpc.com/v0/addresses/{address}/transactions"
        resp = httpx.get(url, params=params, timeout=30.0)
        resp.raise_for_status()

        txns = resp.json()
        if not txns:
            break

        all_txns.extend(txns)
        before_sig = txns[-1]["signature"]

        time.sleep(1.0)  # enhanced API has lower rate limits

    return all_txns[:limit]
```

## Common Gotchas

1. **Two different base URLs** — RPC/DAS uses `mainnet.helius-rpc.com`, Enhanced/Webhooks uses `api-mainnet.helius-rpc.com`
2. **DAS price data is cached** — 600s TTL, only top 10k tokens by volume
3. **Enhanced Transactions cost 100 credits** — budget carefully on free tier (1M credits = 10k calls)
4. **Webhook duplicates** — Helius retries failed deliveries; always deduplicate by signature
5. **getAssetsByOwner** — Set `showFungible: true` or you'll only get NFTs
6. **Pagination max** — DAS offset-based pagination maxes at 1000; use cursor for larger sets
