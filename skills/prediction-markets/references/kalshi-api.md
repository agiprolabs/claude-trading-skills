# Kalshi API Reference

CFTC-regulated US event exchange. USD-denominated, RSA-signed REST + WebSocket. Sources cross-validated across three production codebases.

> 📖 **Canonical docs (verify before coding — this API has changed before):** API reference <https://docs.kalshi.com> (legacy <https://trading-api.readme.io>); official starter code <https://github.com/Kalshi/kalshi-starter-code-python>. The host, order schema, and field names below were correct at audit time but **re-confirm them against the live docs + one smoke call before hand-rolling** signing or order bodies — the old host (`trading-api.kalshi.com`) and the integer-cents order schema both broke when Kalshi changed them.

## Host & versioning

- **Base URL: `https://api.elections.kalshi.com/trade-api/v2`**
- `trading-api.kalshi.com` and `api.kalshi.com` **return 401** — they are dead. This is a recurring live bug.
- The **demo** environment has a near-empty book; use the production host even for read-only candlestick/orderbook pulls.
- There are **no unauthenticated endpoints** — even market-data reads require a signed request.

## Authentication (RSA-PSS)

1. Generate an API key in the Kalshi dashboard → you get a **key UUID** and a **private RSA key (PEM)**.
2. Sign the string `{timestamp_ms}{METHOD}{path}` where `path` **includes** the `/trade-api/v2` prefix and **excludes** the query string.
3. Scheme: **RSA-PSS**, MGF1 over **SHA-256**, salt length = digest length (`PSS.DIGEST_LENGTH`). Kalshi also accepts `MAX_LENGTH` salt, but digest-length is the documented default.
4. Send three headers: `KALSHI-ACCESS-KEY` (the UUID), `KALSHI-ACCESS-TIMESTAMP` (the ms used in the signature), `KALSHI-ACCESS-SIGNATURE` (base64).

Common failures: signing the path **with** the query string; forgetting the `/trade-api/v2` prefix; using seconds instead of milliseconds; reusing a timestamp.

## Order placement

`POST /portfolio/orders`. The current schema uses **fixed-point dollar STRINGS**, not integer cents:

```python
body = {
    "ticker": "KXHIGHNY-26JUN21-B74.5",
    "action": "buy",                 # buy | sell
    "side": "yes",                   # yes | no  (both are BID sides — see order-book convention)
    "count_fp": "1.00",              # contracts as a dollar-string, NOT integer `count`
    "yes_price_dollars": "0.30",     # price as a dollar-string, NOT integer `yes_price`
    "time_in_force": "good_till_canceled",   # REQUIRED: good_till_canceled | immediate_or_cancel | fill_or_kill
    "client_order_id": "myapp-20260621-knyc-b74-5",  # [A-Za-z0-9-] ONLY
}
```

Pitfalls (all observed as live `invalid_parameters` / `400` errors):
- The **old `count` / `yes_price` integer-cents schema is rejected**. Use `count_fp` / `yes_price_dollars`.
- **Do NOT include `type: "limit"`** — that field is rejected.
- `time_in_force` is **required**; omitting it 400s.
- `client_order_id` accepts **`[A-Za-z0-9-]` only**. Bracket tickers contain `.` and `:` (e.g. `B74.5`) — you must **sanitize** the coid separately from the ticker.
- Fill quantity in the response is `fill_count_fp`, not `filled_count`.

### `strike_type` is NOT inferable from the ticker

A `T67` threshold market can be **`greater`** or **`less`**. Read the API `strike_type` field — inferring it from the ticker caused 8/14 live misclassifications and a measurable daily loss gap. Always trust the API field.

### Fees

Taker fee per contract: `ceil(0.07 · C · p · (1 − p) · 100) / 100` dollars, where `C` = contracts, `p` = price in [0,1]. Peaks at `p=0.50` (~1.75¢/contract), shrinks toward the wings. Maker fills are 0% (plus periodic liquidity rebates). This makes **maker-side** strategies structurally favored.

## Tickers

```
KXHIGH<CITY>-<YYMONDD>-B<center>     # bracket: 2°F window, e.g. B74.5 = {74,75}
KXHIGH<CITY>-<YYMONDD>-T<strike>     # threshold: greater/less (read strike_type!)
KXLOW<CITY>-...                      # daily LOW series
```

- ~20 US cities, both HIGH and LOW series.
- **The settlement date is the `<YYMONDD>` token in the ticker** (e.g. `26JUN21` → 2026-06-21). Do **not** derive it from `close_time`, which is the next-day UTC (~00:59 ET) and off-by-ones the join.
- Kalshi lists only **next-day (T-1)** markets — there is no deep forward calendar.

## Market data

```python
# list markets / events / series
GET /markets?series_ticker=KXHIGHNY&status=open
GET /events/{event_ticker}
# candlesticks (dollar-string OHLC for yes_bid/yes_ask + price/volume/open_interest)
GET /series/{series}/markets/{ticker}/candlesticks?start_ts=&end_ts=&period_interval=60
# orderbook snapshot
GET /markets/{ticker}/orderbook?depth=
```

`period_interval` is in **minutes** (1, 60, 1440). Candlestick price fields are dollar strings (e.g. `"yes_bid": {"close": "0.42"}`).

## WebSocket

- **`wss://api.elections.kalshi.com/trade-api/ws/v2`** (some deployments use `wss://external-api-ws.kalshi.com/trade-api/ws/v2`). Sign the WS upgrade with path **`/trade-api/ws/v2`** — a client that force-prepends `/trade-api/v2` corrupts the signature and the connection fails.
- **Discovery pipeline:** subscribe unfiltered to `["trade", "market_lifecycle_v2"]`; on a `market_lifecycle_v2` event with `event_type: "created"`, immediately subscribe `["orderbook_delta"]` for that ticker → you receive an `orderbook_snapshot` then incremental deltas.
- Because Kalshi lists only T-1, the WS collector is the primary way to capture the (thin, early) book before settlement day.

## Rate limits

- Reads ~**200 tokens/sec** (bucket cap 200); writes ~**100 tokens/sec** (bucket cap 100). Tiers vary by account.
- Retry **429 / 5xx** with exponential backoff (e.g. `250ms · 2^n`, cap ~4s). **Never retry 4xx** — it's a malformed request, not transient.

## Settlement (summary — full rules in brackets-and-settlement.md)

- Source: **NWS CLI** daily climate report (integer °F), **LST** window (no DST). Mirrored by **IEM ASOS** daily, which is a **100% match** to Kalshi payouts.
- **Grid-actuals / model reanalysis are NOT the settlement source** — they are leaky and inaccurate; do not settle backtests on them.
- CLI ≠ raw METAR; a per-city seasonal bias correction may be needed when forecasting *toward* the CLI value. See `forecasting-for-brackets.md`.

## Full endpoint surface (verified)

```
# Portfolio
GET    /trade-api/v2/portfolio/balance
GET    /trade-api/v2/portfolio/positions
GET    /trade-api/v2/portfolio/orders[?status=resting|canceled|executed]
GET    /trade-api/v2/portfolio/orders/{order_id}
POST   /trade-api/v2/portfolio/orders                      # place
DELETE /trade-api/v2/portfolio/orders/{order_id}           # cancel -> 200 {"order":{... status:"canceled"}}
POST   /trade-api/v2/portfolio/orders/{id}/amend           # ticker REQUIRED in body, else 400
POST   /trade-api/v2/portfolio/orders/{id}/decrease        # body {"reduce_by_fp":"1.00"}; to-zero closes it
POST   /trade-api/v2/portfolio/orders/batched              # body {"orders":[...]}
GET    /trade-api/v2/portfolio/fills[?limit=N]
GET    /trade-api/v2/portfolio/settlements[?limit=N]
GET    /trade-api/v2/portfolio/deposits | /withdrawals
# Market data (all require auth)
GET    /trade-api/v2/markets?event_ticker={event}[&with_nested_markets=true][&limit=500]
GET    /trade-api/v2/markets/{ticker}/orderbook
GET    /trade-api/v2/series/{series}/markets/{ticker}/candlesticks?start_ts=&end_ts=&period_interval=60
GET    /trade-api/v2/markets/trades                        # recent trade prints
```

### Market metadata fields (from `/markets`)
`ticker`, `series`, `event_ticker`, `strike_type` (`"greater"`/`"less"`/`"bracket"`), `floor_strike`, `cap_strike` (floats), `subtitle`, `close_ts`, and `result` (`"yes"`/`"no"`/`""`). **`result` is the simplest authoritative settlement source** — read it post-resolution instead of re-deriving truth.

### Orderbook response (two variants — normalize)
```
{"orderbook": {"yes": [[price, size], ...], "no": [[price, size], ...]}}
```
- `yes`/`no` are both **resting bid** ladders. Prices may be **integer cents** OR **dollar floats** depending on the API tier (`orderbook_fp.yes_dollars` vs `orderbook.yes`). Normalize: if a price value is `> 1.0`, divide by 100.

### Order-lifecycle gotchas
- `amend` **silently 400s** if `ticker` is omitted from the body.
- `decrease` to zero **closes** the order; a subsequent `DELETE` returns **404**, not 400 — handle gracefully.
- Response fill quantity is `fill_count_fp` (string), and prices are `*_price_dollars` strings — not `filled_count`/`yes_price`.
- Demo host (`https://demo-api.kalshi.co`, WS `wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2`) is order-lifecycle testing only — its book is near-empty; real prices need production even for read-only candlestick pulls. Demo 429s after ~24 rapid calls.
