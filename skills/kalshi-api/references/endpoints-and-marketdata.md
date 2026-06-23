# Kalshi Endpoints & Market Data Reference

## Host

```
https://api.elections.kalshi.com/trade-api/v2
```

Dead hosts (return 401): `trading-api.kalshi.com`, `api.kalshi.com`. There are no unauthenticated endpoints — every request requires RSA-PSS signing.

---

## Full Endpoint Surface

All paths below are relative to the base URL.

### Portfolio

| Method | Path | Notes |
|---|---|---|
| GET | `/portfolio/balance` | Account balance |
| GET | `/portfolio/positions` | Open positions |
| GET | `/portfolio/orders` | `?status=resting\|canceled\|executed` |
| GET | `/portfolio/orders/{order_id}` | Single order by ID |
| POST | `/portfolio/orders` | Place order (dollar-string schema) |
| DELETE | `/portfolio/orders/{order_id}` | Cancel → `{"order": {..., "status": "canceled"}}` |
| POST | `/portfolio/orders/{id}/amend` | Modify; `ticker` required in body |
| POST | `/portfolio/orders/{id}/decrease` | `{"reduce_by_fp": "1.00"}` |
| POST | `/portfolio/orders/batched` | `{"orders": [...]}` |
| GET | `/portfolio/fills` | `?limit=N` |
| GET | `/portfolio/settlements` | `?limit=N` |
| GET | `/portfolio/deposits` | Deposit history |
| GET | `/portfolio/withdrawals` | Withdrawal history |

### Market Data

| Method | Path | Notes |
|---|---|---|
| GET | `/markets` | List markets; `?series_ticker=&status=open&limit=500` |
| GET | `/markets/{ticker}` | Single market details |
| GET | `/markets/{ticker}/orderbook` | `?depth=N`; both-bid-ladder format |
| GET | `/markets/trades` | Recent trade prints |
| GET | `/events/{event_ticker}` | Event + nested markets |
| GET | `/events` | `?series_ticker=&status=open&with_nested_markets=true` |
| GET | `/series/{series}` | Series metadata (includes `contract_url`) |
| GET | `/series/{series}/markets/{ticker}/candlesticks` | OHLC history |

### Exchange Status

| Method | Path |
|---|---|
| GET | `/exchange/status` |
| GET | `/exchange/schedule` |
| GET | `/exchange/announcements` |

---

## Market Metadata Fields

Key fields returned by `GET /markets/{ticker}`:

| Field | Type | Description |
|---|---|---|
| `ticker` | string | Unique market identifier |
| `event_ticker` | string | Parent event |
| `series_ticker` | string | Parent series |
| `title` | string | Human-readable description |
| `status` | string | `open`, `closed`, `settled` |
| `result` | string | `yes`, `no`, or empty until settled |
| `open_time` | ISO-8601 | When market opened |
| `close_time` | ISO-8601 | When market stops accepting orders |
| `expected_expiration_time` | ISO-8601 | Expected settlement time |
| `yes_bid` | dollar string | Best resting YES bid |
| `yes_ask` | dollar string | Implied YES ask (derived) |
| `no_bid` | dollar string | Best resting NO bid |
| `last_price` | dollar string | Last trade price |
| `volume` | integer | Total contracts traded |
| `open_interest` | integer | Open contracts |
| `strike_type` | string | Settlement comparison type — must query; not inferable from ticker |
| `floor_strike` | number | Lower boundary (bracket markets) |
| `cap_strike` | number | Upper boundary (bracket markets) |

---

## Orderbook Response (normalize before using)

```json
{"orderbook": {"yes": [[price, size], ...], "no": [[price, size], ...]}}
```

Both `yes` and `no` are **resting BID** ladders, sorted best-first. Prices come in two formats depending on API tier:

- **Dollar floats** (`orderbook_fp` variant): price in `[0.0, 1.0]`
- **Integer cents** (`orderbook` variant): price in `[0, 100]`

**Normalize:** if any price value is `> 1.0`, it is integer cents — divide by 100 before computing mid or fee.

---

## Candlesticks

`GET /series/{series}/markets/{ticker}/candlesticks?start_ts=&end_ts=&period_interval=60`

- `start_ts` / `end_ts`: Unix epoch seconds
- `period_interval`: minutes — valid values are `1`, `60`, `1440`

**Response fields** (all prices are dollar strings):

```json
{
  "candles": [
    {
      "ts": 1234567890,
      "yes_bid": {"open": "0.40", "high": "0.45", "low": "0.38", "close": "0.42"},
      "yes_ask": {"open": "0.60", "high": "0.62", "low": "0.55", "close": "0.58"},
      "price":   {"open": "0.41", "high": "0.44", "low": "0.39", "close": "0.41"},
      "volume": 42,
      "open_interest": 100
    }
  ]
}
```

Parse with: `float(candle["yes_bid"]["close"])`.

---

## Rate Limits

Kalshi uses a token-bucket model, tiered by account level:

| Tier | Read tokens/sec | Write tokens/sec |
|---|---|---|
| Basic | ~200 | ~100 |
| Higher tiers | Higher (contact Kalshi) | — |

- Exceeding limits → `429 Too Many Requests`
- Back off with exponential retry; pace bursts to ~1.5s between calls during order management
- The demo environment rate-limits the same way: ~24 rapid calls before hitting 429

---

## Tickers

Kalshi ticker hierarchy: `SERIES-YYMMDD[-STRIKE]`

- **Series ticker:** `KXHIGHNY` (NYC daily high)
- **Event ticker:** `KXHIGHNY-26JUN02` (NYC high on June 2, 2026)
- **Market ticker:** `KXHIGHNY-26JUN02-B75.5` (bracket at 75.5°F)

Kalshi lists only **T-1** (next trading day). Markets appear ~24 hours before their observation window opens. The WebSocket `market_lifecycle_v2` channel signals new listings.

`series_ticker` on `GET /markets?series_ticker=KXHIGHNY&status=open` returns all open markets in that series.
