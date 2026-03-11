# DexScreener API — Endpoints Reference

All endpoints use base URL `https://api.dexscreener.com`. No authentication required.

---

## DEX Data Endpoints (~300 req/min)

### Search Pairs

- **Endpoint**: `GET /latest/dex/search`
- **Parameters**: `q` (required) — token name, symbol, or address
- **Response**: `{ "schemaVersion": "1.0.0", "pairs": [...] }` — up to ~30 pairs
- **Notes**: Searches across all 80+ chains. Results sorted by liquidity.

```bash
curl "https://api.dexscreener.com/latest/dex/search?q=BONK"
```

### Get Pairs by Chain + Pair Address

- **Endpoint**: `GET /latest/dex/pairs/{chainId}/{pairAddresses}`
- **Parameters**:
  - `chainId` (path) — chain identifier (e.g., `solana`, `ethereum`)
  - `pairAddresses` (path) — single or comma-separated pair addresses (max 30)
- **Response**: `{ "schemaVersion": "1.0.0", "pairs": [...] }`

```bash
curl "https://api.dexscreener.com/latest/dex/pairs/solana/PAIR_ADDRESS"
# Multiple pairs
curl "https://api.dexscreener.com/latest/dex/pairs/solana/PAIR1,PAIR2,PAIR3"
```

### Get Pairs by Token Address (Legacy)

- **Endpoint**: `GET /latest/dex/tokens/{tokenAddresses}`
- **Parameters**: `tokenAddresses` (path) — single or comma-separated token addresses (max 30)
- **Response**: `{ "schemaVersion": "1.0.0", "pairs": [...] }`
- **Notes**: Returns all pairs containing the token across all chains.

```bash
curl "https://api.dexscreener.com/latest/dex/tokens/So11111111111111111111111111111111111111112"
```

### Get Token Pairs (v1)

- **Endpoint**: `GET /token-pairs/v1/{chainId}/{tokenAddress}`
- **Parameters**:
  - `chainId` (path) — chain identifier
  - `tokenAddress` (path) — single token address
- **Response**: Array of pair objects for that token on the specified chain.

```bash
curl "https://api.dexscreener.com/token-pairs/v1/solana/TOKEN_MINT"
```

### Get Tokens (v1)

- **Endpoint**: `GET /tokens/v1/{chainId}/{tokenAddresses}`
- **Parameters**:
  - `chainId` (path) — chain identifier
  - `tokenAddresses` (path) — comma-separated token addresses (max 30)
- **Response**: Array of pair objects.

```bash
curl "https://api.dexscreener.com/tokens/v1/solana/TOKEN1,TOKEN2"
```

---

## Token Profile & Boost Endpoints (~60 req/min)

### Latest Token Profiles

- **Endpoint**: `GET /token-profiles/latest/v1`
- **Response**: Array of token profiles with metadata, links, and images.

```json
[
  {
    "chainId": "solana",
    "tokenAddress": "TOKEN...",
    "icon": "https://...",
    "header": "https://...",
    "description": "...",
    "links": [
      { "label": "Website", "type": "website", "url": "https://..." },
      { "label": "Twitter", "type": "twitter", "url": "https://x.com/..." }
    ]
  }
]
```

### Latest Boosted Tokens

- **Endpoint**: `GET /token-boosts/latest/v1`
- **Response**: Array of recently boosted tokens.

```json
[
  {
    "chainId": "solana",
    "tokenAddress": "TOKEN...",
    "amount": 500,
    "totalAmount": 2500,
    "icon": "https://...",
    "description": "..."
  }
]
```

### Top Boosted Tokens

- **Endpoint**: `GET /token-boosts/top/v1`
- **Response**: Same schema as latest, sorted by `totalAmount` descending.

### Token Orders

- **Endpoint**: `GET /orders/v1/{chainId}/{tokenAddress}`
- **Response**: Array of orders (ads, profile claims) for a token.

```json
[
  {
    "type": "tokenProfile",
    "status": "approved",
    "paymentTimestamp": 1700000000
  }
]
```

### Community Takeovers

- **Endpoint**: `GET /community-takeovers/latest/v1`
- **Response**: Array of tokens with recent community takeover activity.

---

## Pair Response Schema

Every pair object returned by DEX data endpoints:

| Field | Type | Description |
|-------|------|-------------|
| `chainId` | string | Chain identifier |
| `dexId` | string | DEX name (raydium, orca, uniswap, etc.) |
| `url` | string | DexScreener URL for this pair |
| `pairAddress` | string | On-chain pair/pool address |
| `labels` | string[] | Pool type labels: `"CLMM"`, `"DLMM"`, `"wp"` |
| `baseToken` | object | `{ address, name, symbol }` |
| `quoteToken` | object | `{ address, name, symbol }` |
| `priceNative` | string | Price in quote token (string for precision) |
| `priceUsd` | string | USD price (string for precision) |
| `txns` | object | Transaction counts by timeframe |
| `volume` | object | Volume in USD: `{ m5, h1, h6, h24 }` |
| `priceChange` | object | % change: `{ m5, h1, h6, h24 }` |
| `liquidity` | object | `{ usd, base, quote }` |
| `fdv` | number | Fully diluted valuation (may be absent) |
| `marketCap` | number | Market cap (may be absent) |
| `pairCreatedAt` | number | Millisecond timestamp |
| `info` | object | Optional: `{ imageUrl, websites[], socials[] }` |

---

## Supported Chains

Major: `solana`, `ethereum`, `base`, `arbitrum`, `bsc`, `polygon`, `avalanche`, `optimism`, `zksync`, `scroll`, `linea`, `tron`, `near`, `aptos`, `ton`, `sui`, `hyperliquid`

80+ chains total. The `chainId` value matches the URL slug on dexscreener.com.
