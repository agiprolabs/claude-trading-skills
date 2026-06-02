---
name: stock-alert-monitor
description: Persistent US small/micro-cap catalyst monitor that polls news feeds on an interval and pings on new matches — mergers/acquisitions, earnings & profit beats, and positive PR (FDA decisions, contract wins), with optional share-price and volume filters
---

# Stock Alert Monitor

Watch US equities for actionable catalysts on small- and micro-cap names and get
pinged the moment a new headline matches. Built for traders who care about three
event types on lower-priced stocks (e.g. under $20):

- **Mergers / acquisitions** — buyouts, definitive agreements, tender offers, go-shops
- **Profit reports** — earnings beats, record revenue/net income, raised guidance
- **Positive PR** — FDA approvals/filings, clinical readouts, contract & partnership wins

## When to Use This Skill

- You want a hands-off, always-on watcher for catalyst-driven moves in cheap stocks
- You trade micro/small caps where a single press release moves the tape
- You need de-duplicated, near-real-time alerts pushed to chat, phone, or a webhook

## How It Works

`monitor.py` (stdlib only, no deps) polls one or more RSS/Atom feeds, keyword-matches
each headline against the catalyst groups, extracts the ticker, optionally pulls a
live price/volume quote, filters by max price, de-duplicates against a seen-state
file, and emits **one JSON line per new match** on stdout.

```
python skills/stock-alert-monitor/monitor.py --interval 120 --max-price 20
```

Key flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--feeds URL ...` | M&A + biotech feeds | News sources to poll (use ones reachable from your network) |
| `--interval N` | `300` | Seconds between polls |
| `--max-price P` | `20` | Only alert on tickers at/under this price (`0` disables) |
| `--quotes/--no-quotes` | on | Fetch live price + volume per ticker |
| `--webhook URL` | `$ALERT_WEBHOOK` | POST each match to Slack/Discord-style webhook |
| `--once` | off | Single pass then exit (for cron or `/loop`) |
| `--state PATH` | `~/.cache/stock-alert-monitor/seen.txt` | De-dup memory |

## Running It Persistently

**Inside Claude Code (recommended):** wrap it with the `Monitor` tool so every new
match becomes a chat/phone notification:

> Monitor: `python skills/stock-alert-monitor/monitor.py --interval 120 --max-price 20`
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
  "ticker": "TNXP",
  "catalysts": ["positive_pr"],
  "title": "Tonix Pharmaceuticals Awarded $34M DoD Contract for TNX-4200",
  "link": "https://...",
  "quote": {"price": 13.18, "volume": 241680, "currency": "USD"},
  "text": "📈 TNXP [positive_pr] $13.18 vol 241,680 :: Tonix ... $34M DoD Contract"
}
```

## Caveats

- Headline keyword matching is intentionally broad; verify each alert before trading.
- Ticker/price extraction is best-effort — not every release names its ticker cleanly.
- Quotes are delayed/last-close depending on the source; this is a discovery tool,
  not an execution feed. Pair with the `risk-management` and `position-sizing` skills.
