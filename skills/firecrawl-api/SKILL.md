---
name: firecrawl-api
description: >-
  Optional web data source for trading research. Search news, scrape project
  sites and docs to Markdown, and pull SEC EDGAR filings through Firecrawl
  Alexandria. Use when price and on-chain data need context from the web.
license: MIT
metadata:
  author: firecrawl
  version: "1.0.0"
  category: market-data
---

# Firecrawl API: News, project pages and filings

Firecrawl turns web pages into clean Markdown or JSON. Use it next to the price and on-chain skills when research needs text: news on a token or company, a project's docs or tokenomics page, or an SEC filing. It is optional, and no other skill depends on it.

## Prerequisites

- A Firecrawl API key in the `FIRECRAWL_API_KEY` environment variable ([get one here](https://www.firecrawl.dev/?utm_source=claude-trading-skills&utm_medium=integration)). Never hardcode it.
- `uv pip install httpx` for the Python example.

## Quick start

```bash
# Search recent news
curl -s https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "Solana ETF", "sources": ["news"], "limit": 5, "origin": "claude-trading-skills"}'

# Scrape a project page to Markdown
curl -s https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://jup.ag", "formats": ["markdown"], "origin": "claude-trading-skills"}'
```

```python
import os

import httpx

resp = httpx.post(
    "https://api.firecrawl.dev/v2/search",
    headers={"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"},
    json={"query": "Solana ETF", "sources": ["news"], "limit": 5, "origin": "claude-trading-skills"},
    timeout=60,
)
resp.raise_for_status()
for item in resp.json()["data"]["news"]:
    print(item["title"], item["url"])
```

## SEC filings through Firecrawl Alexandria

[Firecrawl Alexandria](https://alexandria.firecrawl.dev/categories/finance?utm_source=claude-trading-skills&utm_medium=integration) gives structured finance sources such as SEC EDGAR. Find a tool with a search, then run it with scrape:

```bash
# Find tools (no Firecrawl credits used)
curl -s https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "SEC EDGAR company filings", "sources": ["alexandria"], "origin": "claude-trading-skills"}'

# Latest 10-K filings for a ticker
curl -s https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"alexandria": {"provider": "sec-gov", "capability": "filings/filings", "options": {"ticker": "COIN", "forms": ["10-K"], "limit": 2}}, "origin": "claude-trading-skills"}'
```

A run bills the tool's listed price in Firecrawl credits, and the response shows the cost. Provider errors come back inside an HTTP 200 response, so check `data.alexandria[0].error` before reading `data.alexandria[0].data`.

## Agent setup (optional)

```bash
# Firecrawl's own Agent Skills, including firecrawl-search, firecrawl-scrape and firecrawl-alexandria
npx skills add firecrawl/skills

# Or install the Firecrawl CLI and its skills in one step
npx -y firecrawl-cli@latest init
```

## Use cases

- Pull recent news on a token, protocol or listed company before a trade review.
- Read a project's docs, tokenomics or audit page as Markdown for the token-economics skill.
- Check a listed company's latest 10-K, 10-Q or 8-K filings.

## References

- [Firecrawl docs](https://docs.firecrawl.dev/introduction?utm_source=claude-trading-skills&utm_medium=integration)
- [Firecrawl Agent Skills](https://github.com/firecrawl/skills)

Outputs are information for research, not financial advice.
