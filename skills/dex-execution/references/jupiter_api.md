# Jupiter v6 API Reference

Base URL: `https://quote-api.jup.ag/v6`

No authentication required. Rate limits apply per IP.

## Rate Limits

| Endpoint | Limit |
|---|---|
| GET /quote | 600 requests/minute |
| POST /swap | 300 requests/minute |
| POST /swap-instructions | 300 requests/minute |
| GET /price | 600 requests/minute |
| GET /tokens | 60 requests/minute |

## GET /quote

Get the best-price quote for a token swap.

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `inputMint` | string | Yes | — | Input token mint address |
| `outputMint` | string | Yes | — | Output token mint address |
| `amount` | integer | Yes | — | Input amount in smallest unit (lamports for SOL) |
| `slippageBps` | integer | No | 50 | Maximum slippage in basis points |
| `platformFeeBps` | integer | No | 0 | Integrator fee in basis points |
| `onlyDirectRoutes` | boolean | No | false | Skip multi-hop routes |
| `asLegacyTransaction` | boolean | No | false | Return legacy transaction format |
| `maxAccounts` | integer | No | 64 | Maximum accounts in transaction |
| `excludeDexes` | string | No | — | Comma-separated DEX names to exclude |
| `restrictIntermediateTokens` | boolean | No | false | Only use high-liquidity intermediate tokens |

### Response

```json
{
  "inputMint": "So11111111111111111111111111111111111111112",
  "inAmount": "1000000000",
  "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  "outAmount": "14250000",
  "otherAmountThreshold": "14178750",
  "swapMode": "ExactIn",
  "slippageBps": 50,
  "priceImpactPct": "0.01",
  "routePlan": [
    {
      "swapInfo": {
        "ammKey": "...",
        "label": "Raydium",
        "inputMint": "So111...",
        "outputMint": "EPjFW...",
        "inAmount": "1000000000",
        "outAmount": "14250000",
        "feeAmount": "25000",
        "feeMint": "So111..."
      },
      "percent": 100
    }
  ],
  "contextSlot": 250000000,
  "timeTaken": 0.05
}
```

### Key Response Fields

- **`outAmount`**: Expected output in smallest units
- **`otherAmountThreshold`**: Minimum output after slippage (for ExactIn mode)
- **`priceImpactPct`**: Price impact as a percentage string
- **`routePlan`**: Array of swap steps with DEX labels and amounts
- **`timeTaken`**: Quote computation time in seconds

### Example

```bash
curl "https://quote-api.jup.ag/v6/quote?\
inputMint=So11111111111111111111111111111111111111112&\
outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&\
amount=1000000000&\
slippageBps=50"
```

## POST /swap

Build a swap transaction from a quote response.

### Request Body

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `quoteResponse` | object | Yes | — | Full quote response from GET /quote |
| `userPublicKey` | string | Yes | — | Signer's public key (base58) |
| `wrapAndUnwrapSol` | boolean | No | true | Auto wrap/unwrap SOL |
| `useSharedAccounts` | boolean | No | true | Use shared intermediate token accounts |
| `dynamicComputeUnitLimit` | boolean | No | false | Auto-set compute unit limit from simulation |
| `skipUserAccountsRpcCalls` | boolean | No | false | Skip RPC calls for user account checks |
| `prioritizationFeeLamports` | int/string | No | 0 | Priority fee; use `"auto"` for Jupiter estimate |
| `dynamicSlippage` | boolean | No | false | Auto-adjust slippage based on conditions |
| `computeUnitPriceMicroLamports` | integer | No | — | Explicit compute unit price (overrides prioritizationFeeLamports) |

### Response

```json
{
  "swapTransaction": "AQAAAA...base64...",
  "lastValidBlockHeight": 250000100,
  "prioritizationFeeLamports": 50000,
  "computeUnitLimit": 200000,
  "dynamicSlippageReport": {
    "slippageBps": 75,
    "otherAmount": 14143125,
    "simulatedIncurredSlippageBps": 12
  }
}
```

- **`swapTransaction`**: Base64-encoded versioned transaction (or legacy if requested)
- **`lastValidBlockHeight`**: Transaction expires after this block height
- **`dynamicSlippageReport`**: Present when `dynamicSlippage: true`; shows actual slippage used

### Example

```bash
curl -X POST "https://quote-api.jup.ag/v6/swap" \
  -H "Content-Type: application/json" \
  -d '{
    "quoteResponse": { ... },
    "userPublicKey": "YourPubkeyHere",
    "wrapAndUnwrapSol": true,
    "dynamicComputeUnitLimit": true,
    "prioritizationFeeLamports": "auto"
  }'
```

## POST /swap-instructions

Returns individual instructions instead of a serialized transaction. Use this for advanced cases where you need to add custom instructions.

### Request Body

Same as POST /swap.

### Response

```json
{
  "tokenLedgerInstruction": null,
  "computeBudgetInstructions": [...],
  "setupInstructions": [...],
  "swapInstruction": { ... },
  "cleanupInstruction": { ... },
  "addressLookupTableAddresses": [...]
}
```

Each instruction contains `programId`, `accounts` (array of `{pubkey, isSigner, isWritable}`), and `data` (base58).

## GET /price

Simple price lookup for one or more tokens (Jupiter Price API v2).

**URL**: `https://price.jup.ag/v2/price`

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `ids` | string | Yes | Comma-separated token mint addresses |
| `vsToken` | string | No | Quote token (default: USDC) |

### Response

```json
{
  "data": {
    "So11111111111111111111111111111111111111112": {
      "id": "So11111111111111111111111111111111111111112",
      "mintSymbol": "SOL",
      "vsToken": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
      "vsTokenSymbol": "USDC",
      "price": 142.50
    }
  },
  "timeTaken": 0.002
}
```

## GET /tokens

Returns all tokens Jupiter supports for swapping.

### Response

Array of token objects:

```json
[
  {
    "address": "So11111111111111111111111111111111111111112",
    "chainId": 101,
    "decimals": 9,
    "name": "Wrapped SOL",
    "symbol": "SOL",
    "logoURI": "https://...",
    "tags": ["old-registry"],
    "extensions": {}
  }
]
```

## Common Token Mints

| Token | Mint Address |
|---|---|
| SOL (wrapped) | `So11111111111111111111111111111111111111112` |
| USDC | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` |
| USDT | `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB` |
| BONK | `DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263` |
| JUP | `JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN` |
| RAY | `4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R` |
| ORCA | `orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE` |

## Error Responses

| Status | Body | Meaning |
|---|---|---|
| 400 | `{"error": "No route found"}` | No swap path exists for this pair/amount |
| 400 | `{"error": "Amount too small"}` | Input amount below minimum |
| 429 | — | Rate limit exceeded |
| 500 | — | Internal server error; retry |
