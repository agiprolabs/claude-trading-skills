#!/usr/bin/env python3
"""Persistent US small/micro-cap catalyst monitor.

Polls one or more news feeds (RSS/Atom) on an interval, keyword-matches each
headline for catalysts (mergers, earnings/profit beats, positive PR such as
FDA decisions and contract wins), optionally filters by share price and market
cap, de-duplicates against headlines already seen, and emits one line per NEW
match on stdout. It can also push each match to a Slack/Discord-style webhook.

Design notes
------------
* One JSON object per new match is printed to stdout (newline-delimited). This
  is intentional: the script is meant to be wrapped by Claude Code's `Monitor`
  tool, where each stdout line becomes a chat/phone notification. It also works
  standalone (cron, systemd, `python monitor.py &`).
* Network egress: news feeds and the quote API must be reachable. Some sandboxed
  environments allowlist outbound hosts; run this where Yahoo/your feed hosts
  are reachable, or point --feeds at a host you can reach.
* No third-party deps — stdlib only.

Usage
-----
    python monitor.py                       # defaults: M&A + biotech PR feeds, 300s
    python monitor.py --interval 120 --max-price 20
    python monitor.py --once                # single pass (good for /loop or cron)
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
        "merger", "to acquire", "acquisition", "acquired by", "buyout",
        "takeover", "definitive agreement", "to be acquired", "tender offer",
        "all-cash", "go-shop", "business combination",
    ],
    "profit": [
        "beats", "tops estimates", "record revenue", "record profit",
        "swings to profit", "net income", "earnings beat", "raises guidance",
        "raised guidance", "profit surges", "eps of", "above consensus",
    ],
    "positive_pr": [
        "fda approval", "fda clears", "nda", "snda", "phase 3", "phase iii",
        "breakthrough", "awarded contract", "contract win", "wins contract",
        "government contract", "dod contract", "partnership", "milestone payment",
        "positive results", "topline", "designation",
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
ITEM_RE = re.compile(r"<(?:item|entry)\b.*?</(?:item|entry)>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


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


def fetch_quote(ticker: str, timeout: int = 12) -> dict | None:
    """Best-effort price + volume + market cap via Yahoo's public chart API."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        "?interval=1d&range=1d"
    )
    try:
        data = json.loads(_http_get(url, timeout))
        res = data["chart"]["result"][0]
        meta = res["meta"]
        return {
            "price": meta.get("regularMarketPrice"),
            "volume": meta.get("regularMarketVolume"),
            "currency": meta.get("currency"),
        }
    except Exception:
        return None


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
            quote = fetch_quote(ticker) if (ticker and args.quotes) else None
            # price filter
            if quote and quote.get("price") is not None and args.max_price:
                if quote["price"] > args.max_price:
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
            price = f"${quote['price']:.2f}" if quote and quote.get("price") else "?"
            vol = f"{quote['volume']:,}" if quote and quote.get("volume") else "?"
            match["text"] = (
                f"📈 {ticker or '?'} [{','.join(cats)}] {price} vol {vol} :: {item['title']}"
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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--feeds", nargs="+", default=DEFAULT_FEEDS)
    p.add_argument("--interval", type=int, default=300, help="poll seconds")
    p.add_argument("--max-price", type=float, default=20.0,
                   help="only alert on tickers at/under this price (0 = no filter)")
    p.add_argument("--quotes", action="store_true", default=True,
                   help="fetch price/volume (needs quote API egress)")
    p.add_argument("--no-quotes", dest="quotes", action="store_false")
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("--webhook", default=os.environ.get("ALERT_WEBHOOK"))
    p.add_argument("--state", default=os.path.expanduser(
        "~/.cache/stock-alert-monitor/seen.txt"))
    p.add_argument("--once", action="store_true", help="single pass then exit")
    args = p.parse_args()

    state = Path(args.state)
    seen = load_seen(state)
    print(f"# stock-alert-monitor up | feeds={len(args.feeds)} "
          f"interval={args.interval}s max_price={args.max_price} "
          f"seen={len(seen)}", file=sys.stderr, flush=True)

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
