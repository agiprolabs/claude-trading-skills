# Polymarket API Reference

On-chain prediction market on **Polygon**. Each market is a pair of YES/NO **ERC-1155** outcome tokens (the Conditional Token Framework, "CTF"), collateralized 1:1 by **USDC**. Off-chain CLOB order matching, on-chain settlement, **zero taker fees**.

## Identifiers (you will juggle several)

| ID | What it is |
|----|-----------|
| `condition_id` | On-chain hex id of the market (the CTF condition) |
| `clob_token_ids` | The YES/NO **pair** of ERC-1155 token ids |
| `token_id` | A **single** outcome token — what you pass to order-book / WS queries |
| `event_id` | Parent grouping (e.g. all brackets of "NYC high today") |

Prices are in **[0.00, 1.00]** USDC; YES + NO ≈ 1.0 per market.

## Gamma API — market discovery (no auth)

```python
import httpx
events = httpx.get("https://gamma-api.polymarket.com/events", params={
    "tag_id": 103040,           # category tag (e.g. weather)
    "order": "endDate",
    "ascending": "false",       # CRITICAL: default sort is OLDEST-first → you get closed markets
    "closed": "false",
}).json()
```

Each event → `markets[]`, each with `condition_id`, `clob_token_ids`, `question`, `outcomes`, `outcomePrices`. Always set `order`/`ascending` — the oldest-first default is a recurring trap.

## CLOB API — order book & trading (EIP-712 auth)

```bash
uv pip install py-clob-client
```

```python
import os
from py_clob_client.client import ClobClient

client = ClobClient(
    "https://clob.polymarket.com",
    chain_id=137,                                  # Polygon mainnet
    key=os.environ["POLYMARKET_PRIVATE_KEY"],      # wallet private key — env only, NEVER hardcode
    signature_type=2,                              # 2 = Gnosis Safe proxy (Polymarket UI accounts)
                                                   # 0 = direct EOA
)
client.set_api_creds(client.create_or_derive_api_creds())   # derives API key/secret/passphrase from the wallet

book = client.get_order_book(token_id)             # bids/asks for one outcome token
price = client.get_price(token_id, side="BUY")
```

- Auth is **EIP-712** typed-data signing with the wallet key; the SDK derives a set of API credentials from it.
- `signature_type=2` for the proxy/Safe accounts the Polymarket web UI creates; `0` for a raw EOA you control.
- REST host: `https://clob.polymarket.com`. Data API (trades, holders, etc.): `https://data-api.polymarket.com`.

## WebSocket

```python
# wss://ws-subscriptions-clob.polymarket.com/ws/market
# subscribe:
{"type": "market", "assets_ids": ["<token_id>", "..."]}
```

Event types: `book` (full snapshot), `price_change` (deltas), `last_trade_price`.

## Settlement & redemption

- **Resolution source for weather markets: Weather Underground** ("History" tab), on the metro's **local clock WITH DST**, midnight-to-midnight. (Contrast Kalshi's LST/no-DST CLI — see brackets-and-settlement.md.)
- Disputes on the international book escalate to the **UMA optimistic oracle** (token-holder vote). This is a genuine resolution-divergence risk vs. Kalshi's CFTC-CCP settlement.
- After resolution, winning tokens must be **redeemed on-chain**: call the CTF `redeemPositions()`. Winnings are not auto-swept.
- Known bad source-data dates have occurred (WU history occasionally wrong) — build a manual-override path for resolution edge cases.

## Geo / KYC constraint

US persons are **restricted** from Polymarket. Reaching the API from a US host typically requires a **SOCKS5 proxy** from an allowed jurisdiction (a `USE_PROXY` toggle is the common pattern); some non-US hosts reach it directly. This — plus on-chain capital lockup and USDC↔USD friction — is why most Kalshi↔Polymarket "arbitrage" is not executable at retail scale by a single legal entity.

## Brackets

Weather range markets list ~**11 brackets of ~1°C** each (US markets quote °F, international °C), across ~50 global cities. Mutually exclusive; `outcomePrices` across an event sum to ~1.0 (overround applies just as on Kalshi).
