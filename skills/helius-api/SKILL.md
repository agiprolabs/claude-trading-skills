---
name: helius-api
description: Enhanced Solana RPC with DAS API, parsed transactions, webhooks, and priority fee estimation via Helius
---

# Helius API — Enhanced Solana RPC

Helius extends standard Solana RPC with parsed transaction history, a unified Digital Asset Standard (DAS) API, webhooks, and priority fee estimation. Essential for wallet analysis, token metadata, and transaction monitoring.

## Quick Start

### 1. Get an API Key

Sign up at [dashboard.helius.dev](https://dashboard.helius.dev) — free tier available (1M credits/mo, no card required).

```bash
export HELIUS_API_KEY="your-api-key"
```

### 2. Install Dependencies

```bash
uv pip install httpx python-dotenv
```

### 3. Two Base URLs

Helius uses different base URLs depending on the API:

| API | Base URL | Protocol |
|-----|----------|----------|
| RPC / DAS / Priority Fees | `https://mainnet.helius-rpc.com/?api-key=KEY` | JSON-RPC 2.0 |
| Enhanced Transactions / Webhooks | `https://api-mainnet.helius-rpc.com/v0/...?api-key=KEY` | REST |

## DAS API (Digital Asset Standard)

Unified interface for querying all Solana digital assets — fungible tokens, NFTs, compressed NFTs, Token-2022.

### Get Asset Metadata

```python
import httpx, os

API_KEY = os.environ["HELIUS_API_KEY"]
RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"

resp = httpx.post(RPC_URL, json={
    "jsonrpc": "2.0", "id": 1,
    "method": "getAsset",
    "params": {
        "id": "So11111111111111111111111111111111111111112",  # wSOL
        "options": {"showFungible": True}
    }
})
asset = resp.json()["result"]
# asset.content.metadata.name, asset.token_info.decimals, etc.
```

### Get All Assets for a Wallet

```python
resp = httpx.post(RPC_URL, json={
    "jsonrpc": "2.0", "id": 1,
    "method": "getAssetsByOwner",
    "params": {
        "ownerAddress": "WALLET_ADDRESS",
        "page": 1,
        "limit": 100,
        "displayOptions": {
            "showFungible": True,
            "showNativeBalance": True,
            "showZeroBalance": False,
        }
    }
})
assets = resp.json()["result"]["items"]
```

### Search Assets with Filters

```python
resp = httpx.post(RPC_URL, json={
    "jsonrpc": "2.0", "id": 1,
    "method": "searchAssets",
    "params": {
        "ownerAddress": "WALLET_ADDRESS",
        "tokenType": "fungible",      # fungible | nonFungible | all
        "page": 1,
        "limit": 50,
    }
})
```

### All DAS Methods

| Method | Purpose | Credits |
|--------|---------|---------|
| `getAsset` | Single asset metadata | 10 |
| `getAssetBatch` | Up to 1,000 assets | 10 |
| `getAssetsByOwner` | All assets for a wallet | 10 |
| `getAssetsByGroup` | Assets by collection | 10 |
| `getAssetsByCreator` | Assets by creator | 10 |
| `getAssetsByAuthority` | Assets by update authority | 10 |
| `searchAssets` | Multi-criteria filtered search | 10 |
| `getAssetProof` | Merkle proof (compressed NFTs) | 10 |
| `getAssetProofBatch` | Batch proofs | 10 |
| `getSignaturesForAsset` | Tx history for an asset | 10 |
| `getNftEditions` | All editions of a master | 10 |
| `getTokenAccounts` | Token accounts by mint/owner | 10 |

See `references/das_api.md` for complete field documentation.

## Enhanced Transactions API

Transforms raw Solana transactions into human-readable structured data with categorized types and sources.

### Parse a Transaction

```python
API_URL = f"https://api-mainnet.helius-rpc.com/v0/transactions?api-key={API_KEY}"

resp = httpx.post(API_URL, json={
    "transactions": ["SIGNATURE_HERE"],
})
parsed = resp.json()[0]
# parsed["type"]        → "SWAP"
# parsed["source"]      → "JUPITER"
# parsed["description"] → "User swapped 1 SOL for 150 USDC on Jupiter"
# parsed["tokenTransfers"] → [{mint, amount, from, to}, ...]
# parsed["nativeTransfers"] → [{from, to, amount}, ...]
```

### Get Parsed Transaction History for a Wallet

```python
url = f"https://api-mainnet.helius-rpc.com/v0/addresses/{wallet}/transactions"
resp = httpx.get(url, params={
    "api-key": API_KEY,
    "limit": 50,
    "type": "SWAP",  # optional filter
})
history = resp.json()
```

### Transaction Types (151+)

Key types for trading analysis:

| Type | Meaning |
|------|---------|
| `SWAP` | DEX swap |
| `TRANSFER` | Token/SOL transfer |
| `ADD_LIQUIDITY` / `REMOVE_LIQUIDITY` | LP operations |
| `NFT_SALE` / `NFT_MINT` / `NFT_LISTING` | NFT marketplace |
| `STAKE_SOL` / `UNSTAKE_SOL` | Staking |
| `CREATE_ORDER` / `FILL_ORDER` | Limit orders |

### Transaction Sources (50+)

`JUPITER`, `RAYDIUM`, `ORCA`, `MAGIC_EDEN`, `TENSOR`, `MARINADE`, `METEORA`, `PHANTOM`, etc.

See `references/enhanced_transactions.md` for full type/source enums.

## Webhooks

Real-time notifications for on-chain events — no polling required.

### Create a Webhook

```python
url = f"https://api-mainnet.helius-rpc.com/v0/webhooks?api-key={API_KEY}"
resp = httpx.post(url, json={
    "webhookURL": "https://your-server.com/helius-hook",
    "transactionTypes": ["SWAP", "TRANSFER"],
    "accountAddresses": ["WalletAddress1", "WalletAddress2"],
    "webhookType": "enhanced",
    "authHeader": "your-secret-token",
})
webhook_id = resp.json()["webhookID"]
```

### Webhook Types

| Type | Data Format | Filtering |
|------|------------|-----------|
| `enhanced` | Parsed (like Enhanced Transactions API) | By transaction type + account |
| `raw` | Unprocessed transaction data | By account only (lower latency) |
| `discord` | Formatted messages to Discord channel | By transaction type + account |

### Manage Webhooks

```python
# List all
webhooks = httpx.get(f"{url}?api-key={API_KEY}").json()

# Update
httpx.put(f"{url}/{webhook_id}?api-key={API_KEY}", json={
    "webhookURL": "https://new-url.com/hook",
    "transactionTypes": ["SWAP"],
    "accountAddresses": ["NewWallet..."],
    "webhookType": "enhanced",
})

# Delete
httpx.delete(f"{url}/{webhook_id}?api-key={API_KEY}")
```

Up to 100,000 addresses per webhook (via API). 1 credit per event delivered.

## Priority Fee API

Estimate optimal priority fees for transaction landing.

```python
resp = httpx.post(RPC_URL, json={
    "jsonrpc": "2.0", "id": 1,
    "method": "getPriorityFeeEstimate",
    "params": [{
        "accountKeys": ["JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"],
        "options": {
            "includeAllPriorityFeeLevels": True,
            "recommended": True,
        }
    }]
})
fees = resp.json()["result"]
# fees["priorityFeeEstimate"]  → recommended fee (microlamports/CU)
# fees["priorityFeeLevels"]    → {min, low, medium, high, veryHigh, unsafeMax}
```

| Level | Percentile | Use Case |
|-------|-----------|----------|
| `min` | 0-20th | Non-urgent |
| `low` | 20-40th | Standard transfers |
| `medium` | 40-60th | DEX swaps (recommended default) |
| `high` | 60-80th | Time-sensitive |
| `veryHigh` | 80-95th | Critical timing |
| `unsafeMax` | 100th | Emergency only |

Fee in microlamports/CU. Total priority fee = microlamports/CU × compute units consumed.

## Pricing & Rate Limits

| Plan | Price/mo | Credits | RPC req/s | DAS req/s |
|------|----------|---------|-----------|-----------|
| Free | $0 | 1M | 10 | 2 |
| Developer | $49 | 10M | 50 | 10 |
| Business | $499 | 100M | 200 | 50 |
| Professional | $999 | 200M | 500 | 100 |

**Credit costs**: Standard RPC = 1, DAS = 10, Enhanced Txns = 100, Webhooks = 1/event. Additional credits: $5/million.

## Files

### References
- `references/das_api.md` — Complete DAS API field reference and response schemas
- `references/enhanced_transactions.md` — Transaction types, sources, and response structure
- `references/webhooks.md` — Webhook setup, management, and event handling
- `references/error_handling.md` — Rate limits, error codes, and retry strategies

### Scripts
- `scripts/wallet_analysis.py` — Fetch wallet assets and parsed transaction history
- `scripts/token_lookup.py` — Look up token metadata and holder information via DAS
