# Kalshi Auth & Orders Reference

## RSA-PSS Authentication

**String to sign:** `{timestamp_ms}{METHOD}{path}`
- `timestamp_ms` — current Unix time in **milliseconds** (not seconds)
- `METHOD` — uppercase HTTP verb: `GET`, `POST`, `DELETE`
- `path` — includes the `/trade-api/v2` prefix, **excludes the query string**

**Algorithm:** RSA-PSS, MGF1 over SHA-256, `salt_length = PSS.DIGEST_LENGTH` (Kalshi also accepts `MAX_LENGTH` but `DIGEST_LENGTH` is the documented default).

**Headers:**
```
KALSHI-ACCESS-KEY:       <key-uuid>
KALSHI-ACCESS-TIMESTAMP: <timestamp_ms string>
KALSHI-ACCESS-SIGNATURE: <base64(signature)>
```

**Common failures:**
- Signing the path with the query string → 401
- Omitting the `/trade-api/v2` prefix from the signed path → 401
- Using seconds instead of milliseconds → 401
- Reusing a timestamp across requests → intermittent 401

---

## Order Schema (current — dollar strings)

`POST /trade-api/v2/portfolio/orders`

The API changed from integer cents to fixed-point dollar **strings**. Any code using the old `count` / `yes_price` / `type` fields will get `400 {"error":{"code":"invalid_parameters"}}`.

**Minimum valid body:**
```json
{
  "ticker": "KXHIGHNY-26JUN02-B75.5",
  "action": "buy",
  "side": "yes",
  "count_fp": "1.00",
  "yes_price_dollars": "0.01",
  "client_order_id": "my-strategy-001",
  "time_in_force": "good_till_canceled"
}
```

**Field rules:**

| Field | Valid values / format | What 400s |
|---|---|---|
| `action` | `"buy"` or `"sell"` | — |
| `side` | `"yes"` or `"no"` | — |
| `count_fp` | fixed-point string, e.g. `"1.00"`, `"10.00"` | integer `count: 1` |
| `yes_price_dollars` | dollar string when side=yes, e.g. `"0.42"` | integer cents `yes_price: 42` |
| `no_price_dollars` | dollar string when side=no | — |
| `time_in_force` | `"good_till_canceled"` \| `"immediate_or_cancel"` \| `"fill_or_kill"` | omitted entirely |
| `client_order_id` | `[A-Za-z0-9-]` only — no dots, colons, or spaces | anything with `.` or `:` (bracket tickers always contain `.`, so never copy the ticker as the coid) |
| `type` | **do not send** | `"type": "limit"` or any `type` field |
| `ticker` | market ticker (not event/series) | event ticker |

**Sanitizing `client_order_id` for bracket tickers:**
```python
import re
def safe_coid(prefix: str, ticker: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9-]", "-", ticker)
    return f"{prefix}-{clean}"[:36]  # keep under length limit
```

---

## `time_in_force` Semantics

| Value | Behavior |
|---|---|
| `good_till_canceled` (GTC) | Rests in the book until filled or explicitly canceled |
| `immediate_or_cancel` (IOC) | Fills what it can immediately; cancels the remainder |
| `fill_or_kill` (FOK) | Fills entirely or cancels entirely — no partial fills |

---

## `strike_type` — Not Inferable from the Ticker

`strike_type` controls how the settlement price is compared to the threshold. It is **not** deducible from the ticker string — you must query the market metadata to read the `strike_type` field.

Querying: `GET /markets/{ticker}` returns `strike_type` in the response body. Always fetch it rather than assuming from the ticker format.

---

## Order Lifecycle

### Amend
`POST /portfolio/orders/{id}/amend`

`ticker` is **required** in the body alongside the updated fields. Omitting it returns `400`.

```json
{
  "ticker": "KXHIGHNY-26JUN02-B75.5",
  "action": "buy",
  "side": "yes",
  "count_fp": "2.00",
  "yes_price_dollars": "0.40",
  "updated_client_order_id": "my-strategy-002"
}
```

### Decrease
`POST /portfolio/orders/{id}/decrease`

Reduces an order's size. Decreasing to zero closes the order (subsequent DELETE returns 404 — the order is already gone).

```json
{"reduce_by_fp": "1.00"}
```

### Cancel
`DELETE /portfolio/orders/{id}`

Returns `200 {"order": {..., "status": "canceled"}}` on success.

### Batch
`POST /portfolio/orders/batched`

```json
{"orders": [<order_body>, <order_body>, ...]}
```

### Lifecycle gotchas
- A resting order that fully fills transitions to `status: "executed"` — it disappears from the resting queue
- `filled_count_fp` tracks partial fills; `remaining_count_fp` is what's still resting
- Canceling an already-filled order returns `400` (not a no-op)
- The demo book is separate from production and near-empty; rate limits apply in demo (~24 calls before 429)

---

## Fees

Kalshi charges a **taker fee** of approximately 7% of the potential profit on the resting order.

```python
def kalshi_fee(price: float, contracts: float) -> float:
    """Taker fee: ~7% of max profit. price in dollars [0, 1]."""
    max_profit_per_contract = 1.0 - price
    return 0.07 * max_profit_per_contract * contracts
```

Maker (resting limit) orders pay no fee. All fees are deducted at settlement, not at fill time.

> Re-confirm the exact fee percentage against <https://docs.kalshi.com> before sizing — Kalshi has adjusted fee tiers before.
