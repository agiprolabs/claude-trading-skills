# Kalshi WebSocket Reference

## Host

```
wss://api.elections.kalshi.com/trade-api/ws/v2
```

Some deployments also use `wss://external-api-ws.kalshi.com/trade-api/ws/v2`.

> **Signing path gotcha:** sign the WS upgrade with path **`/trade-api/ws/v2`** (not `/trade-api/v2`). A client that force-prepends `/trade-api/v2` corrupts the signature and the connection fails immediately.

---

## Authentication

Sign the WebSocket upgrade HTTP request with the same RSA-PSS headers as REST:

```
KALSHI-ACCESS-KEY:       <key-uuid>
KALSHI-ACCESS-TIMESTAMP: <timestamp_ms>
KALSHI-ACCESS-SIGNATURE: <base64(sign("{ts}GET/trade-api/ws/v2"))>
```

Note: the method is always `GET` for the WS upgrade.

---

## Channels

| Channel | Description |
|---|---|
| `orderbook_delta` | Incremental orderbook updates; first message after subscribe is a full snapshot |
| `trade` | Trade prints (matched fills) |
| `market_lifecycle_v2` | Market create / open / close / settle events |
| `ticker` | Best bid/ask ticker updates |
| `fill` | Your own fill confirmations (private channel) |

---

## Discovery Pipeline

Kalshi lists markets only **T-1** (next trading day). To capture a new market's orderbook from the moment it opens:

1. Subscribe unfiltered to `["trade", "market_lifecycle_v2"]` on connect
2. On a `market_lifecycle_v2` event with `event_type: "created"`, immediately subscribe `["orderbook_delta"]` for that `ticker`
3. The first `orderbook_delta` message after subscribing is an `orderbook_snapshot` — treat it as the full state
4. Apply subsequent delta messages to maintain the live book

**Why this matters:** early-session books are thin. Subscribing at market open captures the full price history. REST polling misses the first few ticks.

---

## Subscribe / Unsubscribe Messages

```json
{"id": 1, "cmd": "subscribe", "params": {"channels": ["orderbook_delta"], "market_tickers": ["KXHIGHNY-26JUN02-B75.5"]}}
```

```json
{"id": 2, "cmd": "unsubscribe", "params": {"channels": ["orderbook_delta"], "market_tickers": ["KXHIGHNY-26JUN02-B75.5"]}}
```

---

## Orderbook Delta Format

**Snapshot** (first message after subscribe):
```json
{
  "type": "orderbook_snapshot",
  "market_ticker": "KXHIGHNY-26JUN02-B75.5",
  "yes": [[42, 100], [40, 250]],
  "no":  [[55, 80], [53, 200]]
}
```

**Delta** (incremental update):
```json
{
  "type": "orderbook_delta",
  "market_ticker": "KXHIGHNY-26JUN02-B75.5",
  "price": 42,
  "delta": -50,
  "side": "yes"
}
```

Apply delta: find the price level in the resting bid ladder for that side, add `delta` to the size. If size reaches 0, remove the level.

---

## Reconnection

- Implement exponential backoff on disconnect
- Re-send all subscriptions after reconnect (the server does not remember previous subscriptions)
- Re-run the discovery pipeline (subscribe to `market_lifecycle_v2` unfiltered) after any reconnect to catch markets that opened during the outage
