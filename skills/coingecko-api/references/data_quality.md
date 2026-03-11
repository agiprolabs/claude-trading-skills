# CoinGecko API — Data Quality Notes

## Free vs Pro Tier Differences

| Feature | Free | Pro (Analyst+) |
|---|---|---|
| Rate limit | 30 calls/min | 500 calls/min |
| Authentication | None required | `x-cg-pro-api-key` header |
| Base URL | `api.coingecko.com` | `pro-api.coingecko.com` |
| Historical granularity | Daily (90+ days) | 5-min, hourly available |
| OHLC intervals | 30m / 4h / 4d | More granular options |
| Data freshness | ~1-2 min delay | ~30 sec delay |
| Market chart range | `max` available | `max` available |
| Endpoints available | Most endpoints | All endpoints + extras |

## Price Data Freshness

- Free tier prices update approximately every 60-120 seconds.
- CoinGecko aggregates prices across all exchanges where a token is listed.
- The reported price is a volume-weighted average, not a single exchange price.
- For Solana DEX tokens, CoinGecko may lag behind on-chain price by several minutes.
- Use Birdeye or DexScreener for real-time Solana DEX prices.

## Historical Data Granularity

The `/coins/{id}/market_chart` endpoint auto-selects granularity based on the
`days` parameter:

| Days Range | Auto Granularity | Approx Data Points |
|---|---|---|
| 1 | ~5 minutes | ~288 |
| 2-90 | Hourly | ~48-2160 |
| 91-365 | Daily | ~91-365 |
| `max` | Daily | Varies (up to ~3650) |

Setting `interval=daily` forces daily granularity for any range. There is no way
to force hourly or minute-level granularity on the free tier for ranges over 90 days.

## OHLC Candle Granularity

The `/coins/{id}/ohlc` endpoint returns different candle sizes depending on the
`days` parameter. You cannot choose the candle size independently.

| Days | Candle Size | Approx Candles |
|---|---|---|
| 1 | 30 minutes | 48 |
| 7 | 4 hours | 42 |
| 14 | 4 hours | 84 |
| 30 | 4 hours | 180 |
| 90 | 4 days | ~23 |
| 180 | 4 days | ~45 |
| 365 | 4 days | ~91 |

## Known Data Gaps

### Missing Early History
Some tokens have gaps in their early trading history. The `/market_chart` endpoint
may return fewer data points than expected, or skip days entirely. Always check
the actual timestamps returned rather than assuming regular intervals.

### Volume Spikes
CoinGecko volume data can include wash trading volume from some exchanges. The
"trust score" on exchanges helps filter this, but aggregated volume numbers should
be treated as approximate.

### Market Cap Accuracy
- `market_cap` = `current_price * circulating_supply`
- `circulating_supply` is manually maintained by CoinGecko and may lag behind
  on-chain reality, especially for tokens with complex unlock schedules.
- `fully_diluted_valuation` uses `total_supply` which may also be approximate.

### ATH/ATL Data
All-time high and low values are based on CoinGecko's own price history. If a
token was listed on CoinGecko after its actual ATH (common for tokens that
launched on DEXes before getting listed), the recorded ATH may be lower than
the true ATH.

## Rate Limit Handling

CoinGecko returns HTTP 429 when rate limited. The response includes no
`Retry-After` header, so implement exponential backoff:

```python
import time
import httpx

def safe_get(url: str, params: dict, max_retries: int = 3) -> dict:
    """Fetch with exponential backoff on rate limits."""
    for attempt in range(max_retries):
        resp = httpx.get(url, params=params, timeout=15.0)
        if resp.status_code == 429:
            wait = 2 ** attempt * 10  # 10s, 20s, 40s
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Rate limited after {max_retries} retries")
```

## Timestamp Format

- All Unix timestamps in responses are in **milliseconds** (not seconds).
- Convert with: `pd.to_datetime(ts, unit='ms')` or `datetime.fromtimestamp(ts / 1000)`.
- The `last_updated_at` field in `/simple/price` is in **seconds** (inconsistency).

## Currency Support

CoinGecko supports ~60 fiat currencies and several crypto currencies as the
`vs_currency` parameter. Common values: `usd`, `eur`, `gbp`, `jpy`, `btc`, `eth`, `sol`.

To get the full list: `GET /simple/supported_vs_currencies`.

## Data Not Available via Free Tier

The following require a paid plan:
- Historical data with sub-daily granularity beyond 90 days
- Exchange-specific OHLCV data
- On-chain DEX data (use Birdeye instead)
- NFT floor price history
- Global DeFi data endpoints (some)

## Comparison with Other Data Sources

| Feature | CoinGecko | Birdeye | DexScreener |
|---|---|---|---|
| Solana DEX coverage | Limited | Comprehensive | Good |
| Historical depth | Years | Months | Days-weeks |
| Real-time latency | 1-2 min | Seconds | Seconds |
| Auth required | No (free) | Yes | No |
| Cross-chain | 100+ chains | Solana only | Multi-chain |
| Token count | 13,000+ | 100,000+ | Varies |
| Best for | Macro, history | Solana trading | Quick lookups |
