---
name: prediction-markets
description: Trade and analyze Kalshi & Polymarket event/weather prediction markets — order-book (YES/NO) conventions, temperature/range brackets, settlement rules, REST/WebSocket/CLOB APIs, and the backtesting pitfalls that produce phantom edges.
---

# Prediction Markets — Kalshi & Polymarket

Binary event contracts that settle to **$1 (YES) or $0 (NO)**. Price = the market's implied probability. This skill covers the two major US-accessible venues — **Kalshi** (CFTC-regulated, USD, RSA-auth REST/WS) and **Polymarket** (on-chain, USDC, EIP-712 CLOB) — with the exact API shapes, the **range-bracket** mechanics used for weather/index/crypto markets, the settlement conventions that decide payouts, and the hard-won pitfalls that make naive backtests look profitable when they aren't.

> ⚠️ Analysis/research toolkit. Not financial advice. Live order placement is gated behind your own explicit sign-off — default to read-only.

## The mental model (read this first)

1. **Price is probability.** A contract at $0.30 implies P(event)=30%. YES + NO ≈ $1.00.
2. **Brackets are a partition.** "What will NYC's high be?" lists ~6–11 mutually-exclusive brackets; their YES prices sum to ~1.0. The sum **over** 1.0 is the *overround* (the market's aggregate overpricing) — fair = 1.0.
3. **Favorite–longshot bias is the durable inefficiency.** Cheap longshots (< ~$0.20) are systematically **overpriced** (a $0.05 contract wins ~2%); favorites are fairly/under-priced. Takers lose ~20% pre-fee; **makers** capture the spread + the longshot premium. The edge is structural (retail behavior), not forecasting.
4. **Settlement is venue-specific and unforgiving.** The single most expensive mistake is scoring outcomes against a *derived* truth source instead of the **venue's own resolution**. See `references/brackets-and-settlement.md`.

## Quick Start — Kalshi

### 1. Credentials

Kalshi uses an **RSA key pair** (not a bearer token). Create an API key in the Kalshi dashboard; download the private PEM.

```bash
export KALSHI_KEY_ID="3e6287a8-...."          # the key UUID
export KALSHI_PRIVATE_KEY_PATH="$HOME/.kalshi/private.pem"
```

### 2. Install

```bash
uv pip install httpx cryptography
```

### 3. Host + auth (the part everyone gets wrong)

- **Base URL is `https://api.elections.kalshi.com/trade-api/v2`.** The older `trading-api.kalshi.com` and `api.kalshi.com` hosts **401**.
- **Every request is signed**, including market-data reads (there are no public endpoints; the demo host has an empty book).
- Signature = RSA-PSS (MGF1-SHA256, salt length = digest length) over the string `{timestamp_ms}{METHOD}{path}`, where `path` includes `/trade-api/v2` and **excludes the query string**.

```python
import os, time, base64, httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

BASE = "https://api.elections.kalshi.com/trade-api/v2"
KEY_ID = os.environ["KALSHI_KEY_ID"]
with open(os.environ["KALSHI_PRIVATE_KEY_PATH"], "rb") as f:
    PRIV = serialization.load_pem_private_key(f.read(), password=None)

def _headers(method: str, path: str) -> dict:
    ts = str(int(time.time() * 1000))
    msg = f"{ts}{method}{path}".encode()                 # path includes /trade-api/v2, no query
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
    # sign the PATH ONLY (no query); send params separately
    r = httpx.get(BASE + path, params=params, headers=_headers("GET", "/trade-api/v2" + path))
    r.raise_for_status()
    return r.json()

# Markets in an event (e.g. today's NYC high-temp brackets)
markets = get("/markets", params={"series_ticker": "KXHIGHNY", "status": "open"})
```

### 4. Candlestick history (price/volume over time)

```python
# yes_bid / yes_ask OHLC, price, volume, open_interest — values are dollar STRINGS
candles = get(f"/series/KXHIGHNY/markets/{ticker}/candlesticks",
              params={"start_ts": start_epoch, "end_ts": end_epoch, "period_interval": 60})
```

See `references/kalshi-api.md` for order placement (fixed-point dollar strings, `time_in_force`, `client_order_id` sanitization), the WebSocket feed, and rate limits.

## Quick Start — Polymarket

Polymarket is **on-chain on Polygon**: each market is a pair of YES/NO **ERC-1155** tokens, collateralized 1:1 by USDC in the CTF contract. Off-chain CLOB matching, on-chain settlement, **zero taker fees**.

### 1. Read markets (Gamma API — no auth)

```python
import httpx
# IMPORTANT: default sort is OLDEST-first — always override or you get closed markets
events = httpx.get("https://gamma-api.polymarket.com/events", params={
    "tag_id": 103040,            # e.g. weather tag
    "order": "endDate", "ascending": "false", "closed": "false",
}).json()
# each market exposes: condition_id, clob_token_ids (YES/NO pair), question, outcomes
```

### 2. Order book / trading (CLOB API — EIP-712 wallet auth)

```bash
uv pip install py-clob-client
```

```python
import os
from py_clob_client.client import ClobClient
client = ClobClient(
    "https://clob.polymarket.com", chain_id=137,
    key=os.environ["POLYMARKET_PRIVATE_KEY"],     # wallet key — NEVER hardcode
    signature_type=2,                              # 2 = Gnosis Safe proxy; 0 = direct EOA
)
client.set_api_creds(client.create_or_derive_api_creds())
book = client.get_order_book(token_id)             # token_id = one side from clob_token_ids
```

See `references/polymarket-api.md` for the WebSocket feed, on-chain redemption (`redeemPositions`), UMA dispute resolution, and the US geo/KYC constraint (proxy required).

## Order-book convention (the YES/NO trap)

On Kalshi, **`yes` and `no` are both BID ladders** — there is no separate "ask" book. To *buy NO* you lift the YES-bid side:

```
no_ask          = 1 − best_yes_bid          # what you pay to take NO now
maker_no_rests_at = best_no_bid             # your resting NO bid
P(yes) mid      = (best_yes_bid + (1 − best_no_bid)) / 2
```

Getting this backwards silently inverts every signal. Full treatment + a helper in `scripts/orderbook_and_brackets.py`.

## Brackets & settlement (where backtests die)

Kalshi temperature brackets are **2°F wide and inclusive of both integer endpoints**: `B74.5` covers `{74, 75}°F` and **settles YES iff the official high ∈ {74, 75}**. The bracket→probability map under a forecast `N(μ, σ)` is:

```
P(YES) = Φ((cap + 0.5 − μ)/σ) − Φ((floor − 0.5 − μ)/σ)        # bracket B<center>, e.g. floor=74 cap=75
```

| | Kalshi | Polymarket |
|---|---|---|
| Settlement source | NWS **CLI** daily (integer °F) via IEM ASOS | **Weather Underground** history |
| Day window | **LST**, no DST | **local clock, WITH DST** |
| NYC station | **KNYC** (Central Park) | **KLGA** (LaGuardia) |
| Bracket width | 2°F, inclusive {floor,cap} | ~1°C |
| Taker fee | `ceil(0.07·C·p·(1−p)·100)/100` | **zero** |

The same metro can settle to **different values on the two venues** in DST months and because of the station difference. **Always settle against the venue's own resolution feed, never a re-derived truth.** Details, threshold formulas, and the rounding rules in `references/brackets-and-settlement.md`.

## Backtesting pitfalls (each has produced a phantom edge)

- **Wrong settlement source → fake edge.** Scoring brackets with `floor ≤ round(t) < cap` (1°F, half-open) instead of the real `t ∈ {floor, cap}` (2°F, inclusive) flips ~10% of outcomes and manufactured a fake "+18% fade." Settle on the venue result.
- **Phantom penny asks.** 1¢ ask levels are routinely spoofed; assuming you fill against them produced a +1640% backtest. Count only depth that **persists across snapshots and is corroborated by trade prints**.
- **Date is in the ticker, not `close_time`.** `KXHIGHNY-26JUN21` settles 2026-06-21; `close_time` is the next-day UTC ~00:59 ET — using it off-by-ones the whole join.
- **Look-ahead via mismatched clocks.** Filling at an 18:00Z book snapshot with features cut at 14:00 LST trades non-Eastern cities on future info.
- **Undeduped contracts + infinite-liquidity fills** inflate ROI; walk the real ladder with fees.

Full list with the numbers in `references/lessons-and-pitfalls.md`.

## Files

### References
- `references/kalshi-api.md` — Host, RSA-PSS auth, order schema (fixed-point dollar strings, `time_in_force`, `client_order_id`), tickers, WebSocket discovery, candlesticks, rate limits, and the contradictions of stale docs.
- `references/polymarket-api.md` — Gamma + CLOB + Data APIs, EIP-712 auth, `condition_id`/`token_id` model, WebSocket, on-chain redemption, UMA disputes, geo/KYC.
- `references/brackets-and-settlement.md` — Bracket & threshold → P(YES) formulas, the exact per-venue settlement rounding rules, station/DST/source divergences, and overround.
- `references/lessons-and-pitfalls.md` — The favorite–longshot edge, settle-on-venue-result, phantom-ask depth, look-ahead, and the maker/taker economics (with sources).

### Scripts
- `scripts/orderbook_and_brackets.py` — YES/NO conversion, overround, Kalshi fee, and the Gaussian bracket→P(YES) map (pure functions, no network, no keys).
