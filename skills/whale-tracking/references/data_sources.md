# Whale Tracking Data Sources

Complete guide to the APIs and on-chain methods used for whale tracking on Solana.

## Source Comparison

| Source | Real-Time | Auth | Free Tier | Best For |
|--------|-----------|------|-----------|----------|
| Helius | Yes (webhooks) | API key | 100K credits/mo | Transaction history, webhooks |
| SolanaTracker | Polling | API key | Limited | Top traders, PnL rankings |
| Birdeye | Polling | API key | 100 req/min | Token holder rankings |
| Solana RPC | Polling | None (public) | Unlimited | Token accounts, raw signatures |

## Helius

Helius provides parsed transaction data and webhook-based real-time monitoring. It is the primary data source for whale tracking.

### getSignaturesForAddress

Fetch recent transaction signatures for a wallet:

```
GET https://api.helius.xyz/v0/addresses/{address}/transactions?api-key={KEY}
```

**Parameters:**
- `address` (path): Wallet address
- `api-key` (query): Your Helius API key
- `limit` (query): Max results (default 100, max 1000)
- `before` (query): Signature to paginate before
- `type` (query): Filter by type (e.g., `SWAP`, `TRANSFER`)

**Response** (array of enhanced transactions):
```json
[
  {
    "signature": "5UfD...",
    "timestamp": 1709856000,
    "type": "SWAP",
    "source": "JUPITER",
    "tokenTransfers": [
      {
        "fromUserAccount": "WhaLe...",
        "toUserAccount": "Pool...",
        "mint": "So11...",
        "tokenAmount": 150.5
      },
      {
        "fromUserAccount": "Pool...",
        "toUserAccount": "WhaLe...",
        "mint": "EPjF...",
        "tokenAmount": 45000.0
      }
    ],
    "nativeTransfers": [...],
    "description": "WhaLe... swapped 150.5 SOL for 45000 TOKEN"
  }
]
```

**Rate limit:** Varies by plan. Free tier: ~10 req/sec.

### Webhooks for Real-Time Monitoring

Create a webhook to receive instant notifications for whale activity:

```
POST https://api.helius.xyz/v0/webhooks?api-key={KEY}
```

**Request body:**
```json
{
  "webhookURL": "https://your-server.com/whale-webhook",
  "transactionTypes": ["SWAP", "TRANSFER"],
  "accountAddresses": ["WhaLe1...", "WhaLe2..."],
  "webhookType": "enhanced",
  "encoding": "jsonParsed"
}
```

**Webhook types:**
- `enhanced` — Parsed transaction with human-readable descriptions (recommended)
- `raw` — Full raw transaction data
- `discord` — Formatted for Discord webhooks

**Key considerations:**
- Webhooks fire within seconds of transaction confirmation
- You can monitor up to 100 addresses per webhook on the free tier
- Enhanced type provides token transfer details pre-parsed
- Webhook delivery includes retry on failure (3 attempts)

### Helius DAS API

The Digital Asset Standard API provides token balance snapshots:

```
POST https://mainnet.helius-rpc.com/?api-key={KEY}
```

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getAssetsByOwner",
  "params": {
    "ownerAddress": "WhaLe...",
    "page": 1,
    "limit": 1000,
    "displayOptions": {
      "showFungible": true
    }
  }
}
```

Returns all tokens held by a wallet with current balances. Useful for building a whale portfolio snapshot.

## SolanaTracker

SolanaTracker provides pre-computed trader rankings and PnL data.

### Top Traders Per Token

```
GET https://data.solanatracker.io/top-traders/{mint}
```

**Headers:** `x-api-key: {SOLANATRACKER_API_KEY}`

**Response:**
```json
{
  "wallets": [
    {
      "wallet": "WhaLe...",
      "pnl": 12500.0,
      "pnlPercent": 340.5,
      "bought": 5000.0,
      "sold": 17500.0,
      "volume": 22500.0,
      "tradeCount": 15,
      "holding": 0.0
    }
  ]
}
```

### Wallet PnL and Trade History

```
GET https://data.solanatracker.io/pnl/{wallet}
```

Returns overall PnL stats for a wallet across all tokens traded.

```
GET https://data.solanatracker.io/wallet/{wallet}/trades
```

Returns recent trades with token, direction, size, and timestamp.

### Top Traders Discovery

```
GET https://data.solanatracker.io/top-traders/all?period=7d&limit=50
```

Returns the most profitable wallets over a time period. Useful for discovering new whales to track.

## Birdeye

Birdeye provides token-centric holder and trader data.

### Token Top Traders

```
GET https://public-api.birdeye.so/defi/v2/tokens/top_traders
```

**Headers:** `X-API-KEY: {BIRDEYE_API_KEY}`, `x-chain: solana`

**Parameters:**
- `address` (query): Token mint address
- `time_frame` (query): `24h`, `7d`, `30d`
- `sort_type` (query): `volume`, `pnl`
- `offset`, `limit`: Pagination

**Response includes:** wallet address, buy/sell volume, trade count, PnL.

### Token Holder Distribution

```
GET https://public-api.birdeye.so/defi/v2/tokens/holder
```

**Parameters:**
- `address`: Token mint
- `offset`, `limit`: Pagination

Returns holder addresses sorted by balance, with percentage of supply.

**Rate limit:** 100 req/min (free), 1000 req/min (paid).

## On-Chain (Solana RPC)

Direct RPC calls require no API key and work with any Solana RPC endpoint.

### getTokenLargestAccounts

Fetch the top token holders directly from the chain:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getTokenLargestAccounts",
  "params": ["TokenMintAddress..."]
}
```

**Response:**
```json
{
  "result": {
    "value": [
      {
        "address": "TokenAccountAddress...",
        "amount": "1000000000",
        "decimals": 9,
        "uiAmount": 1.0,
        "uiAmountString": "1.0"
      }
    ]
  }
}
```

**Notes:**
- Returns token account addresses, not wallet addresses
- You need `getAccountInfo` to resolve the token account owner (wallet address)
- Returns top 20 accounts by default
- Free, no authentication required

### Resolving Token Account to Wallet

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getAccountInfo",
  "params": [
    "TokenAccountAddress...",
    {"encoding": "jsonParsed"}
  ]
}
```

The `parsed.info.owner` field contains the wallet address.

### getSignaturesForAddress

Monitor recent transactions for a wallet:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getSignaturesForAddress",
  "params": [
    "WalletAddress...",
    {"limit": 20}
  ]
}
```

Returns signature, slot, blockTime, and err (null if successful). Use each signature to fetch full transaction details via `getTransaction`.

### Transaction Monitoring Pipeline

For whale tracking via raw RPC: (1) `getTokenLargestAccounts` for target token, (2) resolve each token account to wallet, (3) poll `getSignaturesForAddress` per whale, (4) fetch new transactions with `getTransaction` (jsonParsed), (5) parse token transfers to classify buy/sell/transfer.

## Recommended Stack

| Component | Recommended | Fallback |
|-----------|-------------|----------|
| Real-time alerts | Helius webhooks | Polling RPC signatures |
| Transaction history | Helius enhanced API | Solana RPC + manual parsing |
| Top trader discovery | SolanaTracker rankings | Birdeye top traders |
| Holder snapshots | Solana RPC (getTokenLargestAccounts) | Birdeye holder endpoint |
| Wallet PnL | SolanaTracker wallet PnL | Compute from trade history |

For a cost-effective setup, use free Solana RPC for holder snapshots and Helius free tier for enhanced transaction parsing. Upgrade to paid Helius ($49/mo) for webhook-based real-time tracking.
