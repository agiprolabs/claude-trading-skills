# Polymarket — CLOB & Gamma APIs

> Verify all endpoints and parameters against the live docs before use.
> Docs: https://docs.polymarket.com | SDK: https://github.com/Polymarket/py-clob-client

---

## Hosts

| API | Host | Auth |
|-----|------|------|
| Gamma | `https://gamma-api.polymarket.com` | None |
| CLOB | `https://clob.polymarket.com` | EIP-712 (see below) |
| Data | `https://data-api.polymarket.com` | None |
| WebSocket (market) | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | None |
| WebSocket (user) | `wss://ws-subscriptions-clob.polymarket.com/ws/user` | JWT |

Chain: Polygon mainnet `chain_id=137`. Collateral: USDC.e `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`.

---

## Gamma API endpoints

All read-only, no auth required.

| Endpoint | Description |
|----------|-------------|
| `GET /events` | List events (groups of markets). Key params: `tag_id`, `order`, `ascending`, `closed`, `limit`, `offset` |
| `GET /events/{event_id}` | Single event with all child markets |
| `GET /markets` | List markets directly |
| `GET /markets/{condition_id}` | Single market by condition_id |
| `GET /conditions` | On-chain conditions |
| `GET /prices-history` | Historical prices for a token |

**Pagination:** `limit=100&offset=N`, step by 100.

**CRITICAL sort default:** `ascending=true` is the default — you get oldest (closed) markets first. Always pass `order=endDate&ascending=false&closed=false` for active market discovery.

Key response fields per market:
- `condition_id` — on-chain condition hex
- `clobTokenIds` — `[yes_token_id, no_token_id]`
- `question`, `outcomes`, `outcomePrices`
- `endDate`, `closed`, `archived`
- `eventId` — parent event

---

## CLOB API — EIP-712 auth

Install: `uv pip install py-clob-client`

Auth flow:
1. Client instantiated with wallet private key (`POLYMARKET_PRIVATE_KEY` env var) and `signature_type`
2. Call `client.create_or_derive_api_creds()` — signs a canonical message with the wallet to derive `api_key`, `api_secret`, `api_passphrase`
3. Call `client.set_api_creds(creds)` — attaches them to the session
4. Subsequent requests are signed with HMAC using the derived credentials

`signature_type` values:
- `0` — direct EOA (externally owned account you fully control)
- `2` — Gnosis Safe proxy (the account type Polymarket's web UI creates; the funder is the Safe address)

Wallet env vars: `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_FUNDER`. Never hardcode.

### Key CLOB endpoints (via SDK)

| SDK method | REST equivalent | Notes |
|------------|----------------|-------|
| `get_order_book(token_id)` | `GET /book?token_id=` | Returns bids/asks for one outcome token |
| `get_price(token_id, side)` | `GET /price` | Best ask/bid |
| `get_midpoint(token_id)` | `GET /midpoint` | Mid-price |
| `create_order(...)` | `POST /order` | Place limit or market order |
| `cancel_order(order_id)` | `DELETE /order` | Cancel by order ID |
| `cancel_all()` | `DELETE /orders` | Cancel all open orders |
| `get_orders()` | `GET /orders` | Open orders for the account |
| `get_trades()` | `GET /data/trades` | (Data API) historical fills |

### Order schema

```python
from py_clob_client.order_builder.constants import BUY, SELL

order = client.create_order({
    "token_id": "<yes_token_id>",
    "price": 0.62,          # [0.01, 0.99], two decimal places
    "size": 10.0,           # in USDC
    "side": BUY,
    "expiration": 0,        # 0 = GTC (good till cancel)
})
client.post_order(order, order_type="GTC")
```

Price tick is 0.01 USDC (1 cent). Minimum order size: check live docs — varies by market.

---

## WebSocket

### Market feed (no auth)

```python
# Connect: wss://ws-subscriptions-clob.polymarket.com/ws/market
# Subscribe:
{"type": "market", "assets_ids": ["<token_id_1>", "<token_id_2>"]}
```

Event shapes:
- `book` — full order book snapshot (sent on subscribe)
- `price_change` — incremental update `{"asset_id": ..., "price": ..., "side": ..., "size": ...}`
- `last_trade_price` — most recent trade `{"asset_id": ..., "price": ...}`

### User feed (JWT auth)

```python
# Connect: wss://ws-subscriptions-clob.polymarket.com/ws/user
# Auth header: Authorization: Bearer <jwt>
# JWT obtained from: client.derive_api_creds() flow
```

User events: order fills, order status changes.

---

## Trading-parameter defaults (reference)

```python
POLYMARKET_FEE_RATE          = 0.0    # zero taker fees
MIN_EDGE_POLYMARKET          = 0.05   # 5% min net edge after slippage
MIN_CITY_HITRATE             = 0.45   # only trade ~45%+ hit-rate cities
MAX_BET_FRACTION             = 0.015  # 1.5% of bankroll per trade
MAX_DAILY_WAGER_FRACTION     = 0.15   # 15% deployed per day
MAX_SLIPPAGE_FRACTION_OF_EDGE = 0.50
N_BRACKETS_TYPICAL           = 11
BRACKET_WIDTH_C_TYPICAL      = 1
```

Sizing formula (fee-aware net edge):

```
net_edge  = p_model − ask − fee(ask)    # Polymarket: fee = 0
trade if  net_edge > 0.05
limit_¢   = floor((p_model − θ) · 100) # rest bid θ below fair value
size      = fractional_kelly(net_edge, entry), capped at 1.5%/trade, 15%/day
```
