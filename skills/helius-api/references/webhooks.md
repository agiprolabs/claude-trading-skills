# Helius Webhooks — Reference

## Overview

Webhooks deliver real-time on-chain events to your server via HTTP POST — no polling.

**Base URL**: `https://api-mainnet.helius-rpc.com/v0/webhooks?api-key=YOUR_KEY`

**Cost**: 1 credit per event delivered, 100 credits per management API call.

## Webhook Types

| Type | Data | Latency | Filtering |
|------|------|---------|-----------|
| `enhanced` | Parsed (same as Enhanced Transactions API) | Higher | By type + account |
| `raw` | Unprocessed transaction data | Lower | By account only |
| `discord` | Formatted for Discord channel | Higher | By type + account |

Devnet variants: `enhancedDevnet`, `rawDevnet`, `discordDevnet`.

## CRUD Operations

### Create

```python
import httpx, os

API_KEY = os.environ["HELIUS_API_KEY"]
url = f"https://api-mainnet.helius-rpc.com/v0/webhooks?api-key={API_KEY}"

resp = httpx.post(url, json={
    "webhookURL": "https://your-server.com/helius-hook",
    "transactionTypes": ["SWAP", "TRANSFER"],
    "accountAddresses": ["WalletAddr1", "WalletAddr2"],
    "webhookType": "enhanced",
    "authHeader": "Bearer your-secret",  # optional, sent with each delivery
})
webhook = resp.json()
webhook_id = webhook["webhookID"]
```

### List All

```python
resp = httpx.get(f"https://api-mainnet.helius-rpc.com/v0/webhooks?api-key={API_KEY}")
webhooks = resp.json()
```

### Get One

```python
resp = httpx.get(
    f"https://api-mainnet.helius-rpc.com/v0/webhooks/{webhook_id}?api-key={API_KEY}"
)
```

### Update

```python
resp = httpx.put(
    f"https://api-mainnet.helius-rpc.com/v0/webhooks/{webhook_id}?api-key={API_KEY}",
    json={
        "webhookURL": "https://your-server.com/helius-hook",
        "transactionTypes": ["SWAP"],
        "accountAddresses": ["NewWallet1", "NewWallet2"],
        "webhookType": "enhanced",
    }
)
```

### Delete

```python
resp = httpx.delete(
    f"https://api-mainnet.helius-rpc.com/v0/webhooks/{webhook_id}?api-key={API_KEY}"
)
```

## Request Body Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `webhookURL` | string | Yes | Your endpoint URL |
| `transactionTypes` | string[] | Yes | Filter types (use `["ANY"]` for all) |
| `accountAddresses` | string[] | Yes | Addresses to monitor (max 100,000) |
| `webhookType` | string | Yes | `enhanced`, `raw`, or `discord` |
| `authHeader` | string | No | Auth header sent with each delivery |
| `encoding` | string | No | Response encoding |
| `txnStatus` | string | No | Filter by tx status |

## Webhook Delivery Payload

### Enhanced Webhook

Same structure as Enhanced Transactions API:

```json
[
  {
    "signature": "5K2b...",
    "type": "SWAP",
    "source": "JUPITER",
    "description": "User swapped 1 SOL for 150 USDC on Jupiter",
    "fee": 5000,
    "feePayer": "...",
    "timestamp": 1700000000,
    "nativeTransfers": [...],
    "tokenTransfers": [...],
    "accountData": [...],
    "events": {...}
  }
]
```

Note: Payload is an array — multiple events may be batched.

### Raw Webhook

```json
[
  {
    "blockTime": 1700000000,
    "indexWithinBlock": 42,
    "meta": {
      "err": null,
      "fee": 5000,
      "preBalances": [...],
      "postBalances": [...],
      "preTokenBalances": [...],
      "postTokenBalances": [...],
      "logMessages": [...]
    },
    "slot": 250000000,
    "transaction": {
      "message": {...},
      "signatures": [...]
    }
  }
]
```

## Handling Webhook Events

### Verification

Always verify the `authHeader` you configured:

```python
from fastapi import FastAPI, Request, HTTPException

app = FastAPI()
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

@app.post("/helius-hook")
async def handle_webhook(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth != WEBHOOK_SECRET:
        raise HTTPException(status_code=401)

    events = await request.json()
    for event in events:
        if event["type"] == "SWAP":
            handle_swap(event)
        elif event["type"] == "TRANSFER":
            handle_transfer(event)

    return {"status": "ok"}
```

### Idempotency

Helius retries failed deliveries, which can cause duplicates. Deduplicate by transaction signature:

```python
seen_sigs = set()

def handle_event(event):
    sig = event["signature"]
    if sig in seen_sigs:
        return  # duplicate
    seen_sigs.add(sig)
    process(event)
```

## Limits

- **Max addresses per webhook**: 100,000 (via API; dashboard limited to 25)
- **Max webhooks per API key**: Varies by plan
- **Delivery timeout**: Events may be delayed during high load
- **Retry policy**: Helius retries on 4xx/5xx responses

## Use Cases for Trading

| Use Case | Configuration |
|----------|--------------|
| Monitor a wallet for swaps | `accountAddresses: [wallet]`, `transactionTypes: ["SWAP"]` |
| Track token transfers | `accountAddresses: [token_mint]`, `transactionTypes: ["TRANSFER"]` |
| NFT marketplace activity | `accountAddresses: [collection]`, `transactionTypes: ["NFT_SALE"]` |
| Any activity for a set of wallets | `accountAddresses: [w1, w2, ...]`, `transactionTypes: ["ANY"]` |
