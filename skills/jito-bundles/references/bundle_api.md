# Jito Bundle API Reference

## Overview

The Jito Bundle API uses JSON-RPC 2.0 over HTTPS. All requests go to `/api/v1/bundles` on a block engine endpoint.

**Base URLs:**
- `https://mainnet.block-engine.jito.wtf/api/v1/bundles`
- `https://amsterdam.block-engine.jito.wtf/api/v1/bundles`
- `https://frankfurt.block-engine.jito.wtf/api/v1/bundles`
- `https://tokyo.block-engine.jito.wtf/api/v1/bundles`

**Headers:**
```
Content-Type: application/json
```

Some endpoints may require a UUID auth token (obtained from the Jito dashboard) passed as a query parameter or header. Public endpoints (sendBundle, getBundleStatuses, getTipAccounts) generally do not require auth.

---

## sendBundle

Submit a bundle of up to 5 signed transactions for atomic execution.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "sendBundle",
  "params": [
    ["<base58_tx_1>", "<base58_tx_2>"]
  ]
}
```

**Parameters:**
- `params[0]` (array of strings, required): List of 1-5 base58-encoded signed transactions. Transactions execute in order.

**Response (success):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

- `result` (string): Bundle UUID for status tracking.

**Response (error):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "Invalid params: bundle must contain 1-5 transactions"
  }
}
```

**Error codes:**
| Code | Message | Cause |
|------|---------|-------|
| -32600 | Invalid Request | Malformed JSON-RPC |
| -32601 | Method not found | Typo in method name |
| -32602 | Invalid params | Wrong param format, >5 txs, or invalid base58 |
| -32603 | Internal error | Block engine internal failure |
| -32000 | Bundle simulation failed | A transaction in the bundle fails simulation |
| -32001 | Rate limited | Too many requests; back off |

**curl example:**
```bash
curl -X POST "https://mainnet.block-engine.jito.wtf/api/v1/bundles" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "sendBundle",
    "params": [["<base58_tx>"]]
  }'
```

---

## getBundleStatuses

Check landing status of previously submitted bundles.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getBundleStatuses",
  "params": [
    ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"]
  ]
}
```

**Parameters:**
- `params[0]` (array of strings, required): List of 1-5 bundle UUIDs to check.

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "context": {
      "slot": 280000000
    },
    "value": [
      {
        "bundle_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "transactions": [
          {
            "signature": "5rGz...",
            "slot": 280000000,
            "confirmation_status": "confirmed",
            "err": null
          }
        ],
        "slot": 280000000,
        "confirmation_status": "confirmed",
        "err": {
          "Ok": null
        }
      }
    ]
  }
}
```

**Status values in `confirmation_status`:**
| Status | Meaning |
|--------|---------|
| `processed` | Transaction seen by the cluster |
| `confirmed` | Transaction confirmed by supermajority |
| `finalized` | Transaction finalized (max confirmations) |

**If bundle not found**, the corresponding entry in `value` will be `null`. This means the bundle either expired, was never submitted, or is still in-flight. Use `getInflightBundleStatuses` to check in-flight bundles.

---

## getTipAccounts

Fetch the current list of Jito tip payment accounts.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getTipAccounts",
  "params": []
}
```

**Parameters:** None.

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4bVqkfRtQ7NmXwkiAMXBiap",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2o2J3mF9Cp4vFsMhBBe6Vy",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"
  ]
}
```

Returns an array of 8 base58-encoded public keys. Select one randomly or rotate through them to distribute load across validators.

---

## getInflightBundleStatuses

Check status of bundles that are still being processed (not yet landed or expired).

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getInflightBundleStatuses",
  "params": [
    ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"]
  ]
}
```

**Parameters:**
- `params[0]` (array of strings, required): List of 1-5 bundle UUIDs.

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "context": {
      "slot": 280000000
    },
    "value": [
      {
        "bundle_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "status": "Pending",
        "landed_slot": null
      }
    ]
  }
}
```

**Status values:**
| Status | Meaning |
|--------|---------|
| `Pending` | Bundle received, awaiting inclusion |
| `Landed` | Bundle successfully included in a block |
| `Failed` | Bundle failed simulation or expired |
| `Invalid` | Bundle was malformed or contained invalid transactions |

---

## Rate Limits

- Public endpoints: approximately 5-10 requests/second per IP
- Authenticated endpoints: higher limits based on plan
- `sendBundle`: subject to per-IP and per-bundle rate limiting
- `getBundleStatuses` / `getInflightBundleStatuses`: relatively generous limits

**Rate limit response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32001,
    "message": "Rate limited. Please slow down."
  }
}
```

**Mitigation strategies:**
1. Rotate between block engine endpoints (NY, Amsterdam, Frankfurt, Tokyo)
2. Implement exponential backoff on rate limit errors
3. Batch status checks (up to 5 bundle IDs per request)
4. Cache tip accounts (refresh every 60 seconds, not every request)

---

## Request/Response Schema Summary

| Method | Params | Result Type | Notes |
|--------|--------|-------------|-------|
| `sendBundle` | `[[tx1, tx2, ...]]` | `string` (UUID) | Max 5 txs |
| `getBundleStatuses` | `[[id1, id2, ...]]` | `{context, value}` | Max 5 IDs |
| `getTipAccounts` | `[]` | `string[]` | 8 accounts |
| `getInflightBundleStatuses` | `[[id1, id2, ...]]` | `{context, value}` | Max 5 IDs |
