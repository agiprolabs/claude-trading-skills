---
name: kalshi-api
description: Kalshi exchange mechanics — RSA-PSS auth, order schema, YES/NO orderbook convention, WebSocket, and endpoint surface. Market-type-agnostic shared layer for all Kalshi skills.
---

# Kalshi API

CFTC-regulated US event exchange. USD-denominated binary contracts settle at $1.00 (YES wins) or $0.00 (NO wins). REST + WebSocket, RSA-PSS authentication on every request.

For contract semantics and settlement rules, see the `kalshi-weather-markets` and `kalshi-crypto-index-markets` skills. For strategy, sizing, and backtesting, see `prediction-market-strategy`.

---

> **VERIFY BEFORE CODING.**
> The Kalshi API has broken backward compatibility before: the host changed (old `trading-api.kalshi.com` → dead), and the order schema changed (integer cents → dollar strings). Always smoke-test signing and order bodies against a live response before shipping.
>
> Canonical sources:
> - API reference: <https://docs.kalshi.com> (legacy mirror: <https://trading-api.readme.io>)
> - Official Python starter: <https://github.com/Kalshi/kalshi-starter-code-python>

---

## Overview

- **Base URL:** `https://api.elections.kalshi.com/trade-api/v2`
- **Auth:** RSA-PSS on every request — there are no public/unauthenticated endpoints
- **No demo parity:** the demo environment (`demo-api.kalshi.co`) has a near-empty book; use production even for read-only pulls
- **Contracts:** $0.01–$0.99 per contract; pay price if YES wins, lose price if NO wins; max payout = $1.00

---

## Quick Start

### 1. Credentials

```
KALSHI_KEY_ID=<your-key-uuid>
KALSHI_PRIVATE_KEY_PATH=~/.kalshi/private.pem
```

Generate the key in the Kalshi dashboard. Store secrets in environment variables or a secrets manager — never in code.

### 2. Install

```bash
pip install httpx cryptography
```

### 3. Host + auth (the part everyone gets wrong)

The host and signature format are where implementations break. Three common failures:
1. Using the old `trading-api.kalshi.com` host → 401
2. Including the query string in the signed path → 401
3. Signing with seconds instead of milliseconds → 401

```python
import os, time, base64, httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

BASE = "https://api.elections.kalshi.com/trade-api/v2"
KEY_ID = os.environ["KALSHI_KEY_ID"]
with open(os.environ["KALSHI_PRIVATE_KEY_PATH"], "rb") as f:
    PRIV = serialization.load_pem_private_key(f.read(), password=None)

def _headers(method: str, path: str) -> dict:
    """path must include /trade-api/v2 prefix and exclude query string."""
    ts = str(int(time.time() * 1000))             # milliseconds
    msg = f"{ts}{method}{path}".encode()
    sig = PRIV.sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": KEY_ID,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
    }

def get(path: str, params=None):
    # Sign the path only — query goes into params, not the signature
    r = httpx.get(BASE + path, params=params,
                  headers=_headers("GET", "/trade-api/v2" + path))
    r.raise_for_status()
    return r.json()

def post(path: str, body: dict):
    r = httpx.post(BASE + path, json=body,
                   headers=_headers("POST", "/trade-api/v2" + path))
    r.raise_for_status()
    return r.json()

# Example: open markets in a series
markets = get("/markets", params={"series_ticker": "KXHIGHNY", "status": "open"})
```

**Signature spec:** RSA-PSS, MGF1 over SHA-256, salt length = `PSS.DIGEST_LENGTH`. String to sign: `{timestamp_ms}{METHOD}{path}` where path includes `/trade-api/v2` and excludes the query string.

Headers: `KALSHI-ACCESS-KEY` (UUID), `KALSHI-ACCESS-TIMESTAMP` (ms), `KALSHI-ACCESS-SIGNATURE` (base64).

### 4. Candlestick history

```python
# Returns OHLC for yes_bid / yes_ask + volume + open_interest
# Values are dollar strings: {"close": "0.42"}
candles = get(
    f"/series/KXHIGHNY/markets/{ticker}/candlesticks",
    params={"start_ts": start_epoch, "end_ts": end_epoch, "period_interval": 60},
)
```

`period_interval` is in **minutes**: `1`, `60`, or `1440`.

---

## YES/NO Order-Book Convention

On Kalshi, **`yes` and `no` are both resting BID ladders** — there is no separate ask book. To take the other side you lift the opposing bid:

```
no_ask  = 1 − best_yes_bid    # cost to buy NO right now (lift YES bids)
yes_ask = 1 − best_no_bid     # cost to buy YES right now (lift NO bids)
P(YES) mid = (best_yes_bid + (1 − best_no_bid)) / 2
```

Getting this backwards silently inverts every signal. Use the helpers in `scripts/kalshi_orderbook.py`.

**Orderbook response** comes in two variants depending on API tier — normalize before using:
```json
{"orderbook": {"yes": [[price, size], ...], "no": [[price, size], ...]}}
```
If a price value is `> 1.0`, it is integer cents — divide by 100.

---

## Order Schema

`POST /trade-api/v2/portfolio/orders` uses **fixed-point dollar STRINGS**, not integers. The old schema (integer cents, `count`, `yes_price`) returns `400 invalid_parameters`.

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

Critical field rules — each violation returns `400`:

| Field | Rule | Common mistake that 400s |
|---|---|---|
| `count_fp` | fixed-point **string** `"1.00"` | integer `count: 1` |
| `{side}_price_dollars` | dollar **string** `"0.01"` | integer cents `yes_price: 1` |
| `time_in_force` | **required**: `good_till_canceled` \| `immediate_or_cancel` \| `fill_or_kill` | omitted |
| `client_order_id` | `[A-Za-z0-9-]` only | `.` or `:` in the string — bracket tickers contain `.`, so never copy the ticker directly |
| `type` | **do not send** | `"type": "limit"` |

For the full order lifecycle (amend, decrease, cancel, batch) and `strike_type` gotchas, see `references/auth-and-orders.md`.

---

## Endpoint Summary

| Category | Endpoint | Notes |
|---|---|---|
| Balance | `GET /portfolio/balance` | — |
| Positions | `GET /portfolio/positions` | — |
| Orders | `GET /portfolio/orders` | `?status=resting\|canceled\|executed` |
| Place order | `POST /portfolio/orders` | dollar-string schema above |
| Cancel | `DELETE /portfolio/orders/{id}` | returns `{"order": {...status: "canceled"}}` |
| Amend | `POST /portfolio/orders/{id}/amend` | `ticker` required in body |
| Decrease | `POST /portfolio/orders/{id}/decrease` | `{"reduce_by_fp": "1.00"}` |
| Batch | `POST /portfolio/orders/batched` | `{"orders": [...]}` |
| Fills | `GET /portfolio/fills` | `?limit=N` |
| Settlements | `GET /portfolio/settlements` | `?limit=N` |
| Markets | `GET /markets` | `?series_ticker=&status=open&limit=500` |
| Orderbook | `GET /markets/{ticker}/orderbook` | `?depth=N` |
| Candlesticks | `GET /series/{series}/markets/{ticker}/candlesticks` | `?start_ts=&end_ts=&period_interval=60` |
| Trades | `GET /markets/trades` | recent trade prints |

Full endpoint surface, market metadata fields, and rate limits: `references/endpoints-and-marketdata.md`.
WebSocket discovery pipeline: `references/websocket.md`.

---

## Files

### References
- `references/auth-and-orders.md` — RSA-PSS spec, dollar-string order schema, `time_in_force`, `client_order_id` sanitization, amend/decrease/cancel lifecycle, `strike_type` gotcha, fees
- `references/endpoints-and-marketdata.md` — Full endpoint table, orderbook variants, market metadata fields (`result`, `open_time`, `close_time`, `series_ticker`), candlesticks, rate limits
- `references/websocket.md` — WS host, discovery pipeline, channels, signing the WS upgrade

### Scripts
- `scripts/kalshi_orderbook.py` — YES/NO bid-ladder helpers (`no_ask`, `yes_ask`, `p_yes_mid`, `overround`, `kalshi_fee`). Pure stdlib, no keys, runs offline.
