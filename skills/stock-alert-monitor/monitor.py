#!/usr/bin/env python3
"""Persistent US small/micro-cap catalyst momentum monitor.

Polls one or more news feeds (RSS/Atom) on an interval, keyword-matches each
headline for catalysts (FDA/approval, contract, earnings, patent, partnership,
acquisition/merger), pulls a live quote, applies a quantitative momentum screen
(price band, float, average & relative volume, daily % change), de-duplicates
against headlines already seen, and emits one line per NEW match on stdout. It
can also push each match to a Slack/Discord-style webhook.

Default screen (override via flags)
-----------------------------------
* Listing ........... NASDAQ-listed tickers
* Price ............. $0.10 - $10
* Float ............. <= 20,000,000 shares
* Avg daily vol 30d . > 500,000
* Relative volume ... today / 30d-avg > 2x
* Daily % change .... > +10% vs previous close
* Catalyst keywords . FDA, approval, contract, earnings, patent, partnership,
                      acquisition, merge(r)

Design notes
------------
* One JSON object per new match is printed to stdout (newline-delimited). This
  is intentional: the script is meant to be wrapped by Claude Code's `Monitor`
  tool, where each stdout line becomes a chat/phone notification. It also works
  standalone (cron, systemd, `python monitor.py &`).
* Network egress: news feeds AND the quote API must be reachable. The numeric
  screen (float / relative volume / % change) requires the quote feed; in
  `--strict` mode (default) a candidate whose metrics can't be confirmed is
  dropped, so run this where Yahoo + your feed hosts are reachable. Use
  `--no-strict` to fall back to keyword + best-effort-price matching when the
  quote feed is partially blocked.
* No third-party deps — stdlib only.

Usage
-----
    python monitor.py                       # full default momentum screen, 300s
    python monitor.py --interval 120
    python monitor.py --once                # single pass (good for /loop or cron)
    python monitor.py --no-strict           # keyword/price only when quotes blocked
    python monitor.py --webhook https://hooks.slack.com/services/XXX

Exit: runs forever unless --once is given. Ctrl-C / SIGTERM to stop.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from html import unescape
from pathlib import Path

# --- Catalyst keyword groups (lowercased substring match on headline+summary) ---
CATALYSTS = {
    "merger": [
        "merger", "merge", "to acquire", "acquisition", "acquired by", "buyout",
        "takeover", "definitive agreement", "to be acquired", "tender offer",
        "all-cash", "go-shop", "business combination",
    ],
    "profit": [
        "earnings", "beats", "tops estimates", "record revenue", "record profit",
        "swings to profit", "net income", "earnings beat", "raises guidance",
        "raised guidance", "profit surges", "eps of", "above consensus",
    ],
    "positive_pr": [
        "fda", "fda approval", "fda clears", "approval", "nda", "snda",
        "phase 3", "phase iii", "breakthrough", "patent", "contract",
        "awarded contract", "contract win", "wins contract", "government contract",
        "dod contract", "partnership", "milestone payment", "positive results",
        "topline", "designation",
    ],
}

DEFAULT_FEEDS = [
    # Replace/extend with feeds reachable from your environment.
    "https://www.globenewswire.com/RssFeed/subjectcode/22-Mergers%20and%20Acquisitions/feedTitle/GlobeNewswire%20-%20Mergers%20and%20Acquisitions",
    "https://www.globenewswire.com/RssFeed/industry/4577-Biotechnology/feedTitle/GlobeNewswire%20-%20Biotechnology",
]

UA = "Mozilla/5.0 (stock-alert-monitor; +https://github.com/agiprolabs/claude-trading-skills)"

# crude ticker extraction: (NASDAQ: ABCD) / (NYSE: AB) / $ABCD
TICKER_RE = re.compile(r"\((?:NASDAQ|NYSE|NYSE American|AMEX|OTC)[:\s]+([A-Z]{1,5})\)|\$([A-Z]{1,5})\b")
# capture the exchange too, so we can keep NASDAQ-only when --nasdaq-only is set
EXCHANGE_RE = re.compile(r"\((NASDAQ|NYSE|NYSE American|AMEX|OTC)[:\s]+([A-Z]{1,5})\)")
ITEM_RE = re.compile(r"<(?:item|entry)\b.*?</(?:item|entry)>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")

# Yahoo v7 quote fields that back the numeric screen.
QUOTE_FIELDS = (
    "regularMarketPrice,regularMarketVolume,regularMarketChangePercent,"
    "averageDailyVolume3Month,averageDailyVolume10Day,floatShares,"
    "sharesOutstanding,fullExchangeName,currency"
)


def _http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _field(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", block, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    return unescape(TAG_RE.sub("", m.group(1))).strip()


def parse_feed(xml: str) -> list[dict]:
    out = []
    for block in ITEM_RE.findall(xml):
        title = _field(block, "title")
        if not title:
            continue
        link = _field(block, "link")
        summary = _field(block, "description") or _field(block, "summary")
        out.append({"title": title, "link": link, "summary": summary})
    return out


def classify(text: str) -> list[str]:
    t = text.lower()
    return [name for name, kws in CATALYSTS.items() if any(k in t for k in kws)]


def extract_ticker(text: str) -> str | None:
    m = TICKER_RE.search(text)
    if not m:
        return None
    return m.group(1) or m.group(2)


def extract_exchange(text: str) -> str | None:
    m = EXCHANGE_RE.search(text)
    return m.group(1).upper() if m else None


def fetch_quote(ticker: str, timeout: int = 12) -> dict | None:
    """Live quote backing the screen: price, volume, 30d-avg vol, relative
    volume, daily % change, float. Tries Yahoo v7 (rich fundamentals) then
    falls back to the v8 chart endpoint (price/volume/%change only)."""
    v7 = (
        f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
        f"&fields={QUOTE_FIELDS}"
    )
    try:
        data = json.loads(_http_get(v7, timeout))
        q = data["quoteResponse"]["result"][0]
    except Exception:
        q = None
    if q:
        vol = q.get("regularMarketVolume")
        avg = q.get("averageDailyVolume3Month") or q.get("averageDailyVolume10Day")
        flt = q.get("floatShares") or q.get("sharesOutstanding")
        return {
            "price": q.get("regularMarketPrice"),
            "volume": vol,
            "avg_vol_30d": avg,
            "rel_vol": (vol / avg) if (vol and avg) else None,
            "change_pct": q.get("regularMarketChangePercent"),
            "float": flt,
            "exchange": q.get("fullExchangeName"),
            "currency": q.get("currency"),
        }
    # Fallback: v8 chart (no float / avg-vol; derive %change from prev close).
    chart = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        "?interval=1d&range=1d"
    )
    try:
        meta = json.loads(_http_get(chart, timeout))["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        return {
            "price": price,
            "volume": meta.get("regularMarketVolume"),
            "avg_vol_30d": None,
            "rel_vol": None,
            "change_pct": ((price - prev) / prev * 100) if (price and prev) else None,
            "float": None,
            "exchange": meta.get("fullExchangeName"),
            "currency": meta.get("currency"),
        }
    except Exception:
        return None


def passes_screen(q: dict | None, args) -> bool:
    """Apply the quantitative momentum screen. In --strict mode a metric that
    can't be evaluated (missing quote / missing field) fails the candidate; with
    --no-strict, unconfirmed metrics are allowed through (keyword/price mode)."""
    if q is None:
        return not args.strict

    def chk(val, ok) -> bool:
        if val is None:
            return not args.strict
        return ok(val)

    if args.nasdaq_only:
        exch = (q.get("exchange") or "")
        # only enforce when we actually know the exchange
        if exch and "nasdaq" not in exch.lower():
            return False

    price = q.get("price")
    if args.min_price and not chk(price, lambda v: v >= args.min_price):
        return False
    if args.max_price and not chk(price, lambda v: v <= args.max_price):
        return False
    if args.max_float and not chk(q.get("float"), lambda v: v <= args.max_float):
        return False
    if args.min_avg_vol and not chk(q.get("avg_vol_30d"), lambda v: v >= args.min_avg_vol):
        return False
    if args.min_rel_vol and not chk(q.get("rel_vol"), lambda v: v >= args.min_rel_vol):
        return False
    if args.min_change_pct and not chk(q.get("change_pct"), lambda v: v >= args.min_change_pct):
        return False
    return True


def notify_webhook(url: str, payload: dict) -> None:
    body = json.dumps({"text": payload["text"]}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", "User-Agent": UA}
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # webhook failure must not kill the monitor
        print(f"# webhook error: {e}", file=sys.stderr, flush=True)


def run_pass(args, seen: set, webhook: str | None) -> int:
    new_count = 0
    for feed in args.feeds:
        try:
            xml = _http_get(feed, timeout=args.timeout)
        except Exception as e:
            print(f"# feed error {feed}: {e}", file=sys.stderr, flush=True)
            continue
        for item in parse_feed(xml):
            key = item["link"] or item["title"]
            if key in seen:
                continue
            text = f"{item['title']} {item['summary']}"
            cats = classify(text)
            if not cats:
                seen.add(key)
                continue
            ticker = extract_ticker(text)
            # cheap NASDAQ-only prefilter when the headline names the exchange
            if args.nasdaq_only:
                exch = extract_exchange(text)
                if exch and exch != "NASDAQ":
                    seen.add(key)
                    continue
            quote = fetch_quote(ticker) if (ticker and args.quotes) else None
            if not passes_screen(quote, args):
                seen.add(key)
                continue
            seen.add(key)
            new_count += 1
            match = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "ticker": ticker,
                "catalysts": cats,
                "title": item["title"],
                "link": item["link"],
                "quote": quote,
            }
            q = quote or {}
            price_s = f"${q['price']:.2f}" if q.get("price") is not None else "?"
            chg_s = f"{q['change_pct']:+.1f}%" if q.get("change_pct") is not None else "?"
            rv_s = f"{q['rel_vol']:.1f}x" if q.get("rel_vol") else "?"
            vol_s = f"{q['volume']:,}" if q.get("volume") else "?"
            flt_s = f"{q['float'] / 1e6:.1f}M" if q.get("float") else "?"
            match["text"] = (
                f"🚀 {ticker or '?'} [{','.join(cats)}] {price_s} {chg_s} "
                f"relvol {rv_s} vol {vol_s} float {flt_s} :: {item['title']}"
            )
            print(json.dumps(match), flush=True)
            if webhook:
                notify_webhook(webhook, match)
    return new_count


def load_seen(path: Path) -> set:
    if path.exists():
        return set(path.read_text().splitlines())
    return set()


def save_seen(path: Path, seen: set) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # cap memory of the seen file so it can't grow unbounded
    path.write_text("\n".join(list(seen)[-5000:]))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--feeds", nargs="+", default=DEFAULT_FEEDS)
    p.add_argument("--interval", type=int, default=300, help="poll seconds")
    # --- quantitative screen (defaults = the standing momentum criteria) ---
    p.add_argument("--min-price", type=float, default=0.10,
                   help="min share price (0 = no floor)")
    p.add_argument("--max-price", type=float, default=10.0,
                   help="max share price (0 = no cap)")
    p.add_argument("--max-float", type=float, default=20_000_000,
                   help="max float in shares (0 = no limit)")
    p.add_argument("--min-avg-vol", type=float, default=500_000,
                   help="min 30-day avg daily volume (0 = no limit)")
    p.add_argument("--min-rel-vol", type=float, default=2.0,
                   help="min relative volume today/30d-avg (0 = no limit)")
    p.add_argument("--min-change-pct", type=float, default=10.0,
                   help="min daily %% change vs prev close (0 = no limit)")
    p.add_argument("--nasdaq-only", action="store_true", default=True,
                   help="restrict to NASDAQ-listed tickers")
    p.add_argument("--any-exchange", dest="nasdaq_only", action="store_false")
    p.add_argument("--strict", action="store_true", default=True,
                   help="drop candidates whose screen metrics can't be confirmed")
    p.add_argument("--no-strict", dest="strict", action="store_false",
                   help="allow unconfirmed metrics (keyword/price mode)")
    # --- plumbing ---
    p.add_argument("--quotes", action="store_true", default=True,
                   help="fetch price/volume/float (needs quote API egress)")
    p.add_argument("--no-quotes", dest="quotes", action="store_false")
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("--webhook", default=os.environ.get("ALERT_WEBHOOK"))
    p.add_argument("--state", default=os.path.expanduser(
        "~/.cache/stock-alert-monitor/seen.txt"))
    p.add_argument("--once", action="store_true", help="single pass then exit")
    args = p.parse_args()

    state = Path(args.state)
    seen = load_seen(state)
    print(
        "# stock-alert-monitor up | "
        f"nasdaq_only={args.nasdaq_only} price={args.min_price}-{args.max_price} "
        f"float<={args.max_float:g} avgvol>{args.min_avg_vol:g} "
        f"relvol>{args.min_rel_vol}x chg>{args.min_change_pct}% "
        f"strict={args.strict} interval={args.interval}s seen={len(seen)}",
        file=sys.stderr, flush=True,
    )

    try:
        while True:
            n = run_pass(args, seen, args.webhook)
            save_seen(state, seen)
            if args.once:
                print(f"# pass complete, {n} new match(es)", file=sys.stderr, flush=True)
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
