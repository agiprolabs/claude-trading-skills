---
name: stock-alert-monitor
description: Persistent NASDAQ micro-cap catalyst-momentum monitor that polls news feeds on an interval and pings on new matches — mergers/acquisitions, earnings & profit beats, and positive PR (FDA, contract, patent, partnership) — gated by a quantitative screen (price, float, average & relative volume, daily % change)
---

# Stock Alert Monitor

Watch US equities for actionable catalysts on small- and micro-cap names and get
pinged the moment a new headline matches a **catalyst keyword AND a quantitative
momentum screen**. Built for traders who care about three event types on
low-priced NASDAQ names:

- **Mergers / acquisitions** — buyouts, definitive agreements, tender offers, go-shops
- **Profit reports** — earnings beats, record revenue/net income, raised guidance
- **Positive PR** — FDA approvals/filings, clinical readouts, contract/patent/partnership wins

### Default momentum screen

A candidate must clear *all* of these (each tunable via flags; `0` disables):

| Criterion | Default | Flag |
|-----------|---------|------|
| Listing | NASDAQ only | `--nasdaq-only` / `--any-exchange` |
| Price | $0.10 – $10 | `--min-price` / `--max-price` |
| Float | ≤ 20,000,000 shares | `--max-float` |
| Avg daily vol (30-day) | > 500,000 | `--min-avg-vol` |
| Relative volume (today / 30-day) | > 2× | `--min-rel-vol` |
| Daily % change vs prev close | > +10% | `--min-change-pct` |
| Catalyst keywords | FDA · approval · contract · earnings · patent · partnership · acquisition · merge(r) | (built-in groups) |

The float / relative-volume / % change gates need the **live quote feed**. In
`--strict` mode (default) a candidate whose metrics can't be confirmed is
dropped; pass `--no-strict` to fall back to keyword + best-effort-price matching
when the quote feed is partially blocked.

## When to Use This Skill

- You want a hands-off, always-on watcher for catalyst-driven moves in cheap stocks
- You trade micro/small caps where a single press release moves the tape
- You need de-duplicated, near-real-time alerts pushed to chat, phone, or a webhook

## How It Works

`monitor.py` (stdlib only, no deps) polls one or more RSS/Atom feeds, keyword-matches
each headline against the catalyst groups, extracts the ticker, pulls a live
quote (price, volume, 30-day avg volume, relative volume, daily % change, float),
applies the momentum screen above, de-duplicates against a seen-state file, and
emits **one JSON line per new match** on stdout.

```
python skills/stock-alert-monitor/monitor.py --interval 120      # full default screen
python skills/stock-alert-monitor/monitor.py --no-strict          # quotes blocked: keyword/price only
```

Key flags (screen flags are in the table above):

| Flag | Default | Purpose |
|------|---------|---------|
| `--feeds URL ...` | M&A + biotech feeds | News sources to poll (use ones reachable from your network) |
| `--interval N` | `300` | Seconds between polls |
| `--strict/--no-strict` | strict | Drop (or allow) candidates whose screen metrics can't be confirmed |
| `--quotes/--no-quotes` | on | Fetch live price/volume/float per ticker |
| `--webhook URL` | `$ALERT_WEBHOOK` | POST each match to Slack/Discord-style webhook |
| `--once` | off | Single pass then exit (for cron or `/loop`) |
| `--state PATH` | `~/.cache/stock-alert-monitor/seen.txt` | De-dup memory |

## Running It Persistently

**Inside Claude Code (recommended):** wrap it with the `Monitor` tool so every new
match becomes a chat/phone notification:

> Monitor: `python skills/stock-alert-monitor/monitor.py --interval 120`
> (set `persistent: true`)

Each stdout JSON line fires one notification. The script keeps running across the
session and de-dupes via the state file.

**Standalone:** `cron`, `systemd`, or `nohup python monitor.py &`. Point `--webhook`
at Slack/Discord to get pushes, or read the JSONL stdout in your own pipeline.

**Via the `/loop` skill (when shell egress is blocked):** in sandboxes where the
shell can't reach news hosts, run a recurring agent turn instead — each iteration
does a `WebSearch` for fresh catalysts and a `PushNotification` on new matches. Use
`--once` semantics: keep a small seen-list so you only ping on genuinely new items.

## Network Notes

The script needs outbound access to your news feed hosts and (for `--quotes`) to
`query1.finance.yahoo.com`. Some managed/sandboxed environments allowlist egress;
run it where those hosts are reachable, or swap `--feeds` for a source you can hit.

## Output Schema

```json
{
  "ts": "2026-06-02T14:03:11Z",
  "ticker": "ABCD",
  "catalysts": ["positive_pr"],
  "title": "Acme Bio Awarded $34M DoD Contract for ABC-4200",
  "link": "https://...",
  "quote": {
    "price": 4.18, "volume": 6240000, "avg_vol_30d": 850000,
    "rel_vol": 7.3, "change_pct": 28.4, "float": 11800000,
    "exchange": "NasdaqCM", "currency": "USD"
  },
  "text": "🚀 ABCD [positive_pr] $4.18 +28.4% relvol 7.3x vol 6,240,000 float 11.8M :: Acme Bio Awarded $34M DoD Contract"
}
```

## Staged Buy / Hold / Sell Lifecycle (`momentum_lifecycle.py`)

The news screen above answers *"is this name worth watching?"*. The lifecycle
state machine answers *"what stage is it in, and what do I do?"* — turning a
stream of **intraday bars** into staged alerts that follow one name from
discovery to exit. Each alert maps to a buy / hold / sell action:

| Tier | Stage | Signal | Trigger (any/all as noted) | Message |
|------|-------|--------|----------------------------|---------|
| **1** | Watchlist | WATCH | premarket-high break · RVOL > 3 · news catalyst · volume surge | "Stock added to active momentum watchlist." |
| **2** | Entry Setup | **BUY** | opening-range (15m) breakout · vol > 2× prev candle · above VWAP · spread OK | "Primary momentum setup detected." |
| **3** | Optimal Entry | **BUY** | pullback to VWAP/9 EMA · trend intact · volume still elevated | "Optimal pullback entry detected." |
| **4** | Acceleration | HOLD | new intraday highs · RVOL increasing · consecutive volume expansion / halts | "Momentum accelerating." |
| **5** | Weakness | REDUCE | loss of VWAP · failed breakout · volume drying up · multiple failed highs | "Momentum weakening." |
| **6** | Failure | **SELL** | break below stop ref · sustained close below VWAP · key support breakdown | "Momentum setup invalidated." |

```
WATCHLIST → ENTRY SETUP → OPTIMAL ENTRY → ACCELERATION → WEAKNESS → FAILURE
```

It's a **state machine, not a strict pipeline**: names can skip stages
(setup → failure) or recover (weakness → acceleration). Transitions are checked
**risk-first** (Failure, then Weakness, then upgrades) so a breakdown is never
masked by a stale buy. It alerts **once per transition** (not per bar), pins a
`stop_ref` on entry so Tier 6 is objective, and **drops a name on failure** so it
can re-enter cleanly at Tier 1.

**Feed-agnostic** — you push `Bar`s (from Polygon/Alpaca/Tradier/IEX/…) plus a
light `Context`; it owns VWAP / 9-EMA / opening range / RVOL. All thresholds live
in `Config`.

```python
from momentum_lifecycle import MomentumTracker, Bar, Context
trk = MomentumTracker()
alert = trk.on_bar("ABCD", Bar(ts, o, h, l, c, vol, minutes_since_open,
                               bid=b, ask=a), Context(avg_vol_30d, prev_close,
                               premarket_high=pmh, news_catalyst=True, halt_count=n))
if alert:
    print(alert.signal, alert.tier, alert.text())   # e.g. BUY Tier.OPTIMAL_ENTRY ...
```

Run `python skills/stock-alert-monitor/momentum_lifecycle.py` for a synthetic
walk-through that emits all six tiers in order. **Tiers 2–6 require a real-time
intraday bar feed** (VWAP/EMA/ORB/spread/halts) — a different data tier than the
daily-quote news screen, and not reachable from restricted sandboxes. The news
screen feeds Tier 1; wire the lifecycle to your broker/market-data stream for 2–6.

> Not financial advice or an execution feed — a discovery/workflow tool. Pair with
> the `risk-management` and `position-sizing` skills before acting.

## Caveats

- Headline keyword matching is intentionally broad; verify each alert before trading.
- Ticker/price extraction is best-effort — not every release names its ticker cleanly.
- Quotes are delayed/last-close depending on the source; this is a discovery tool,
  not an execution feed. Pair with the `risk-management` and `position-sizing` skills.
