---
name: polymarket-api
description: Polymarket exchange mechanics — on-chain Polygon CTF, Gamma/CLOB/Data APIs, EIP-712 auth, identifier model, WebSocket, settlement, and geo/KYC constraint
---

# Polymarket API

Polymarket is a **prediction market on Polygon mainnet**. Every market is a pair of YES/NO **ERC-1155** tokens issued by the Conditional Token Framework (CTF), collateralized 1:1 in USDC. Off-chain CLOB matching, on-chain settlement, **zero taker fees**. Prices are in [0.00, 1.00] USDC; YES + NO ≈ 1.0 per market.

---

> **Before you write any API code — read the live docs first.**
>
> - Docs: https://docs.polymarket.com
> - Official Python SDK: https://github.com/Polymarket/py-clob-client
>
> Polymarket endpoints and auth flows have changed without notice. Prefer the official `py-clob-client` SDK over hand-rolled HTTP; it handles EIP-712 derivation, API credential management, and order signing. Only hand-roll when the SDK doesn't expose what you need.

---

## Identifier model

You will juggle four distinct IDs — get them confused and queries silently return wrong data.

| ID | What it is |
|----|-----------|
| `condition_id` | On-chain hex ID of the market (the CTF condition) |
| `clob_token_ids` | The YES/NO **pair** of ERC-1155 token IDs — a two-element list |
| `token_id` | A **single** outcome token — what you pass to order-book and WebSocket queries |
| `event_id` | Parent grouping (e.g. all brackets for "NYC high today") |

---

## Quick Start

### 1. Read markets — Gamma API (no auth required)

```python
import httpx

# CRITICAL: default sort is OLDEST-first — always override or you silently get closed markets
events = httpx.get("https://gamma-api.polymarket.com/events", params={
    "tag_id": 103040,        # category tag (e.g. weather)
    "order": "endDate",
    "ascending": "false",    # must be string "false", not bool
    "closed": "false",
}).json()

# Each event → markets[], each market has:
#   condition_id, clob_token_ids (YES/NO pair), question, outcomes, outcomePrices
for event in events:
    for mkt in event.get("markets", []):
        yes_token, no_token = mkt["clobTokenIds"]  # split the pair here
        print(mkt["question"], mkt["outcomePrices"])
```

**Pagination:** `limit=100&offset=N`, step by 100.

### 2. Order book and trading — CLOB API (EIP-712 auth)

```bash
uv pip install py-clob-client
```

```python
import os
from py_clob_client.client import ClobClient

client = ClobClient(
    "https://clob.polymarket.com",
    chain_id=137,                                     # Polygon mainnet
    key=os.environ["POLYMARKET_PRIVATE_KEY"],          # wallet private key — env only, NEVER hardcode
    signature_type=2,                                  # 2 = Gnosis Safe proxy (Polymarket UI accounts)
                                                       # 0 = direct EOA you fully control
)
# Derives API key/secret/passphrase from the wallet signature — call once per session
client.set_api_creds(client.create_or_derive_api_creds())

token_id = "<yes_token_from_clob_token_ids>"
book = client.get_order_book(token_id)     # bids/asks for one outcome token
price = client.get_price(token_id, side="BUY")
```

`signature_type=2` is for the proxy/Safe accounts the Polymarket web UI creates (the funder address is the Safe). Use `signature_type=0` for a raw EOA you control directly. Read the live SDK docs — the type you choose affects how orders are signed on-chain.

Wallet env vars: `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_FUNDER`. Never hardcode keys.

---

## API surface overview

| API | Host | Auth | Purpose |
|-----|------|------|---------|
| Gamma | `https://gamma-api.polymarket.com` | none | Events/markets/conditions/prices metadata |
| CLOB | `https://clob.polymarket.com` | EIP-712 | Order book, order placement/cancel |
| Data | `https://data-api.polymarket.com` | none | Historical trades |
| WebSocket | `wss://ws-subscriptions-clob.polymarket.com/ws/` | none (market) / JWT (user) | Real-time book + trade ticks |

Chain: Polygon mainnet `chain_id=137`. Collateral: USDC.e at `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`.

---

## WebSocket

```python
# Connect to: wss://ws-subscriptions-clob.polymarket.com/ws/market
# Subscribe message:
{"type": "market", "assets_ids": ["<token_id>", "<token_id2>"]}
```

Event types: `book` (full snapshot on subscribe), `price_change` (delta updates), `last_trade_price`.

For user-level order/fill events, connect to `/ws/user` with a JWT derived from your API credentials.

---

## On-chain settlement and redemption

Polymarket weather markets resolve via **Weather Underground** ("History" tab), on the metro's **local clock with DST**, midnight-to-midnight. This differs from Kalshi, which uses LST (no DST) and NWS CLI — see `kalshi-weather-markets` for the divergence.

After resolution, winning tokens **must be redeemed manually on-chain**:

```python
# Call CTF contract redeemPositions() — the SDK or direct web3.py call
# Winnings are NOT auto-swept to your wallet
```

Disputes on the international book escalate to the **UMA optimistic oracle** (token-holder vote). This is a real resolution-divergence risk vs. Kalshi's CFTC-CCP settlement — factor it into any cross-venue comparison.

---

## US geo / KYC constraint

US persons are **blocked** from Polymarket. API calls from a US IP typically require a **SOCKS5 proxy** from an allowed jurisdiction (use a `USE_PROXY` env flag pattern; never hardcode the proxy address). This constraint — combined with on-chain capital lockup and USDC/USD friction — is why most Kalshi/Polymarket arbitrage is not executable at retail scale.

---

## Cross-references

- For strategy, sizing, and backtesting that apply across venues: `prediction-market-strategy`
- For the Kalshi counterpart (RSA-PSS auth, REST host, tickers, order schema): `kalshi-api`
- For weather settlement specifics (WU local-clock+DST vs Kalshi LST, KLGA vs KNYC station): `kalshi-weather-markets`

---

## Files

### References
- `references/clob-and-gamma-apis.md` — Full API surface, all endpoints, EIP-712 auth detail, pagination, order schema, trading-parameter defaults
- `references/settlement-and-ops.md` — WU/UMA resolution, `redeemPositions`, truth-source priority (IEM > WU > Open-Meteo), known-bad dates, geo/KYC, host-segregation, two-exchange architecture notes
