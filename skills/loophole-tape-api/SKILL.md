---
name: loophole-tape-api
description: >-
  pump.fun launch risk check through the loophole tape API: observed creator
  exits, bundle dumps, curve and pool drains, holder concentration, buyer flow,
  and calibrated probabilities of a rug within 5 minutes and of a true
  graduation. Free radar, coverage, watch, calibration and track-record routes;
  paid checks cost $0.005 per mint or $0.01 for up to five, paid per call with
  x402 (USDC on Solana or Base, or USDG on Robinhood Chain). Use before trading a fresh pump.fun token or
  when monitoring a watchlist of new mints.
license: MIT
metadata:
  author: loopholetape
  version: "1.0.0"
  category: trading
---

# loophole tape API — pump.fun Launch Risk Check

loophole tape is a pay-per-call HTTP API and MCP server computed from its own independent capture of pump.fun program events (feed at most 5 seconds behind the chain; the response says when it is not). For a given mint it reports what has already been observed on-chain (creator sold, bundle wallets dumped, curve or pool drained, curve closed low, migration below the graduation threshold) plus two calibrated probabilities: `rug_within_300s` and `true_graduation`.

Basic authority and holder flags are available free from other providers (see `solanatracker-api`, `birdeye-api`). What this API adds is the event-level exit evidence with timestamps and probabilities whose out-of-time validation tables and forward track record are public.

> **Spending rule for agents:** the free routes below need no wallet. Every paid route costs real USDC. **Ask your human before the first paid call**, state the route and the price, and wait for an explicit yes. Never pay from a wallet the human did not designate for this, and never raise the amount or the number of calls beyond what they approved.

> Not financial advice. The output is analysis of public on-chain data; labels and probabilities are statistical, not guarantees.

## Prerequisites

```bash
uv pip install httpx
```

No account and no API key are needed for the free routes. Paid routes need one of: an x402 v2 client with a funded USDC wallet on Solana or Base (or USDG on Robinhood Chain, eip155:4663), a prepaid key (below), or a browser wallet (Phantom or Solflare) opened on the paid URL.

## Quick Start (free routes only)

```python
import httpx

BASE = "https://api.loopholetape.com"

# 1. Free radar: covered mints younger than 30 s with the highest rug probability,
#    and mints younger than 15 min with the highest graduation probability.
radar = httpx.get(f"{BASE}/v1/radar", timeout=10).json()
for item in radar["data"]["top_rug_risk"][:3]:
    print(item["mint"], item["age_s"], item["probabilities"], item["flags"])

# 2. Free coverage check for one to five mints before any paid call.
mint = radar["data"]["top_rug_risk"][0]["mint"]
cov = httpx.get(f"{BASE}/v1/check/coverage", params={"mints": mint}, timeout=10).json()
print(cov["data"]["ready"], cov["data"]["items"], cov["data"]["prices_usd"])
# -> prices_usd: {"single": 0.005, "batch_up_to_five": 0.01}
```

Or run the bundled script: `python scripts/risk_check.py --demo` (offline, mock data) or `python scripts/risk_check.py --mint <MINT>` (free routes plus the unpaid 402 quote; it never pays).

## Routes

### Free

| Route | What it returns |
|-------|-----------------|
| `GET /v1/radar` | Live watchlist (5 s cache): top rug-risk and graduation candidates, each with its paid check URL |
| `GET /v1/check/coverage?mints=A,B` | Per-mint `available`, `data.ready`, and quoted prices; skip mints that are not available |
| `GET /v1/check/watch?mints=A,B&cursor=C` | Signed cursor; `data.has_new_events` tells you whether a new paid check would show anything new. Poll every 15 s or slower |
| `GET /v1/calibration` | Model, features, validation tables (Brier lift, ECE, per-age bins) and caveats |
| `GET /v1/track-record` | Daily forward scorecard of the radar's calls against outcomes |
| `GET /v1/sample/mint` | A full mint card, delayed 5 minutes, to see the response shape |
| `GET /v1/keys/balance` | Remaining credit on a prepaid key (send the `X-API-Key` header) |

### Paid (x402 v2, scheme `exact`)

| Route | Price |
|-------|-------|
| `GET /v1/check/mint/{mint}` | $0.005 |
| `GET /v1/check/watchlist?mints=A,B,C` (up to five) | $0.01 |
| `GET /v1/mint/{mint}` (full card) | $0.025 |
| `GET /v1/launches/since?since=<unix>` (cursor delta with probabilities) | $0.001 per poll |
| `GET /v1/keys/trial` / `GET /v1/keys/new` (prepaid key with that credit) | $0.10 / $2.00 |

The full list with prices is in `https://api.loopholetape.com/openapi.json` and `https://api.loopholetape.com/pricing`.

## Paying (only after the human approves)

An unpaid request to a paid route answers **HTTP 402** with a `PAYMENT-REQUIRED` header (base64 JSON, x402 v2). `accepts[]` carries two options for the same price:

- USDC on Solana mainnet (`solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp`), asset `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`, payTo `9HkwyUhDMyjbpSpnyu5xuZ9vRaFQeajnJsavhie7XcsT`, settled by the PayAI facilitator.
- USDC on Base (`eip155:8453`), asset `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, payTo `0x25d408eF54e60F3006bD13d5A040d525E2F359c2`, settled by Coinbase's CDP facilitator.

Amounts are in 6-decimal base units (`5000` = $0.005). The facilitator pays the network fee; the payer needs only USDC. Sign the entry your wallet supports with any x402 v2 client and retry with the `PAYMENT-SIGNATURE` header. Always compare `amount` and `payTo` in the 402 against the values above before signing.

Without an x402 client: buy a prepaid key once (`/v1/keys/trial` $0.10 or `/v1/keys/new` $2.00, by x402 or in a browser wallet), then send `X-API-Key: lt_...` on any paid route; the route price is deducted from the key's credit.

Charging rules stated by the API: invalid mints, uncovered mints and a stale feed are refused before payment and not charged; an exact retry of the same paid request within 10 minutes replays the result without a second charge; errors on keyed calls are refunded.

## Reading a Check

`data.items[]` in a paid check:

- `status`: `flags_observed` or `no_flags_observed`.
- `findings[]`: `code` (`creator_sold`, `bundle_dumped`, `curve_drained`, `pool_drained`, `curve_closed_low`, `migrate_below_grad`), `first_seen_at`, and the evidence.
- `probabilities.rug_within_300s`: published only while the mint is younger than 30 s (the age range where validation ECE is at most 0.05). `probabilities.true_graduation`: published at any age.
- `concentration`, `buyer_flow`, `curve`: the numbers behind the label.
- `meta.is_stale: false` means the feed was within 5 s of the chain when the answer was generated.

## Calibration Caveats

From `GET /v1/calibration` (model `loophole-risk-gbm-v1`, gradient boosting + isotonic calibration; discovery on launches before 2026-09-04, validation on launches after it):

- "probabilities are statistical estimates on public on-chain data, not guarantees and not financial advice"
- "the model is refit as history grows; the validation shown is for the model currently serving"
- "rug = the launch's price collapsed by our documented rug rule within the horizon after the check"

Out-of-time validation: rug-within-300 s Brier lift 0.288 over the base rate, ECE 0.040 (n_test 163,242); true graduation Brier lift 0.336, ECE 0.004.

Read the forward record too. `GET /v1/track-record` for 2026-09-13 to 2026-09-22 shows the radar's top rug picks rugged within 300 s 31–41% of the time against a mean published probability of 52–61%, while its graduation candidates graduated 5–9% of the time against 4–6% published. The track record's own notes say the last three days can still move and that its base rate is a floor, not a like-for-like comparison. Treat the rug probability as a ranking signal that has run high on the radar's population, and weigh the observed `findings[]` more than the number.

## MCP

Streamable HTTP at `https://api.loopholetape.com/mcp` (initialize and `tools/list` answer without auth). 23 tools: 8 free (`catalog`, `health`, `market_regime`, `sample_mint`, `radar`, `check_coverage`, `watchlist_updates`, `rhc_regime`) and 15 paid (including `check_pumpfun_risk` $0.005 and `check_watchlist_risk` $0.01). A paid tool called without payment returns the x402 requirements as its result; the same human-approval rule applies.

## Use Cases

- **Pre-trade screen:** free coverage check, then (with approval) one $0.005 check; skip the token when `findings[]` shows `creator_sold` or `bundle_dumped`.
- **Watchlist monitoring:** poll the free `/v1/check/watch` cursor and pay for a check only when `has_new_events` is true.
- **Research:** compare the free radar and track record against your own labels before deciding whether the paid data is worth it.

## When to Use vs Alternatives

| Need | Use |
|------|-----|
| Timestamped creator-exit / bundle-dump / drain evidence on a fresh pump.fun mint | **loophole-tape-api** |
| Calibrated rug / graduation probability with public validation | **loophole-tape-api** |
| Free authority and holder flags, risk score | `solanatracker-api`, `birdeye-api` |
| Bonding-curve math and event parsing yourself | `pumpfun-mechanics`, `yellowstone-grpc` |

## Files

### Scripts
- `scripts/risk_check.py` — calls the free radar, coverage and watch routes and prints the unpaid 402 quote for a mint; never signs or pays. `--demo` runs offline on mock responses.

### External docs
- `https://api.loopholetape.com/llms.txt` — full route notes
- `https://api.loopholetape.com/openapi.json` — OpenAPI with prices
- `https://api.loopholetape.com/terms` — terms
- `https://github.com/gosadu/loophole-tape` — buyer examples in Python and TypeScript
