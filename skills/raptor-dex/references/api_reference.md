# Raptor API Reference

Complete HTTP and WebSocket API for the Raptor DEX aggregator.

## HTTP Endpoints

### GET /quote

Get the best swap quote across all supported DEXes.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `inputMint` | string | Yes | Input token mint address |
| `outputMint` | string | Yes | Output token mint address |
| `amount` | integer | Yes | Amount in smallest unit (lamports for SOL) |
| `slippageBps` | string | No | Basis points (e.g. `50`) or `"dynamic"` |
| `dexes` | string | No | Comma-separated DEX whitelist |
| `excludeDexes` | string | No | Comma-separated DEX blacklist |
| `maxHops` | integer | No | Max routing hops 1-4 (default: 4) |
| `directRouteOnly` | boolean | No | Only single-hop routes |
| `pools` | string | No | Comma-separated pool address filter |
| `mints` | string | No | Comma-separated intermediate mint allowlist |
| `feeBps` | integer | No | Platform fee 0-1000 bps |
| `feeAccount` | string | No | Fee recipient wallet |

**Response**:
```json
{
  "amountIn": 1000000000,
  "amountOut": 156234567,
  "otherAmountThreshold": 155453000,
  "priceImpact": 0.12,
  "slippageBps": 50,
  "routePlan": [
    {
      "inputMint": "So11...",
      "outputMint": "EPjF...",
      "amountIn": 1000000000,
      "amountOut": 156234567,
      "dex": "raydium_clmm",
      "pool": "pool_address..."
    }
  ],
  "contextSlot": 298765432
}
```

### POST /swap

Build a complete swap transaction from a quote.

**Request body**:
```json
{
  "quoteResponse": { /* from GET /quote */ },
  "userPublicKey": "wallet_pubkey",
  "wrapUnwrapSol": true,
  "txVersion": "v0",
  "priorityFee": "auto",
  "maxPriorityFee": 100000,
  "computeUnitLimit": null,
  "tip": null,
  "destinationTokenAccount": null
}
```

**Response**:
```json
{
  "swapTransaction": "base64_encoded_unsigned_transaction"
}
```

### POST /swap-instructions

Same as `/swap` but returns instructions only (no transaction wrapper). Useful for composing with other instructions.

### POST /quote-and-swap

Combined quote + transaction build in a single request. Accepts all `/quote` params plus `/swap` body fields.

### POST /send-transaction

Submit a signed transaction via Yellowstone Jet TPU. Requires `--enable-yellowstone-jet`.

**Request body**:
```json
{
  "transaction": "base64_encoded_signed_transaction"
}
```

**Response**:
```json
{
  "signature": "5abc..."
}
```

Raptor automatically retries submission for ~30 seconds or until confirmed.

### GET /transaction/:signature

Track a submitted transaction's status.

**Response**:
```json
{
  "signature": "5abc...",
  "status": "confirmed",
  "latency_ms": 450,
  "slot": 298765433,
  "events": [
    {
      "name": "SwapEvent",
      "parsed": {
        "amountIn": 1000000000,
        "amountOut": 156234567,
        "inputMint": "So11...",
        "outputMint": "EPjF..."
      }
    }
  ]
}
```

Status values: `pending`, `confirmed`, `failed`, `expired`

### GET /health

Returns pool count, cache status, and Yellowstone connection health.

---

## WebSocket API

### /stream — Real-time Quote Streaming

Connect and subscribe to receive updated quotes whenever pool state changes.

**Subscribe**:
```json
{
  "type": "subscribe",
  "inputMint": "So11...",
  "outputMint": "EPjF...",
  "amount": 1000000000,
  "slippageBps": "50"
}
```

**Quote update message**:
```json
{
  "type": "quote",
  "data": {
    "amountIn": 1000000000,
    "amountOut": 156234567,
    "priceImpact": 0.12,
    "routePlan": [...],
    "contextSlot": 298765432
  }
}
```

**Unsubscribe**: `{"type": "unsubscribe", "inputMint": "...", "outputMint": "..."}`

### /stream/swap — Streaming Swap Transactions

Same as `/stream` but returns pre-built transactions ready to sign. Automatically resends after 10 slots without an update to prevent transaction expiry.

**Subscribe** (additional fields):
```json
{
  "type": "subscribe",
  "inputMint": "So11...",
  "outputMint": "EPjF...",
  "amount": 1000000000,
  "slippageBps": "50",
  "userPublicKey": "wallet_pubkey",
  "priorityFee": "auto",
  "tip": null
}
```

**Swap update message**:
```json
{
  "type": "swap",
  "data": {
    "swapTransaction": "base64_unsigned_tx",
    "quote": { /* full quote data */ }
  }
}
```

---

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Invalid parameters or transaction |
| 404 | Transaction not tracked / token not found |
| 503 | Service unavailable (pool indexer still loading, Yellowstone disconnected) |

## Priority Fee Levels

| Level | Description |
|-------|-------------|
| `min` / `low` | Lowest fees, may take longer |
| `auto` / `medium` | Recommended — balances cost and speed |
| `high` / `veryHigh` | Higher fees for faster landing |
| `turbo` / `unsafeMax` | Maximum priority, use for competitive scenarios |

Fees are calculated per-route and per-DEX based on recent fee data.
