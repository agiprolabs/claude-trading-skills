# Sentiment Data Sources

Complete reference for social, aggregator, and on-chain sentiment data APIs.

## Social Media APIs

### Twitter/X API

- **Base URL**: `https://api.twitter.com/2/`
- **Auth**: OAuth 2.0 Bearer Token
- **Key Endpoints**:
  - `GET /tweets/search/recent` — Search tweets from last 7 days
  - `GET /tweets/counts/recent` — Tweet volume over time
  - `GET /users/:id/tweets` — User timeline
- **Rate Limits**:
  - Free tier: 1 app, read-only, 1,500 tweets/month
  - Basic ($100/mo): 10,000 tweets/month, 2 apps
  - Pro ($5,000/mo): 1M tweets/month, full archive search
- **Search Query Examples**:
  ```
  $SOL lang:en -is:retweet           # SOL mentions, English, no RTs
  (solana OR $SOL) (pump OR moon)    # Bullish keywords
  ```
- **Response Fields**: `id`, `text`, `created_at`, `public_metrics.like_count`,
  `public_metrics.retweet_count`, `author_id`
- **Notes**: Pricing changed significantly in 2023. Free tier is very limited.
  Consider third-party aggregators for cost-effective access.

### Reddit API

- **Base URL**: `https://oauth.reddit.com/`
- **Auth**: OAuth2 with client ID and secret
- **Key Endpoints**:
  - `GET /r/{subreddit}/search` — Search within subreddit
  - `GET /r/{subreddit}/hot` — Hot posts
  - `GET /r/{subreddit}/new` — New posts
  - `GET /r/{subreddit}/comments/{article}` — Post comments
- **Rate Limits**: 100 requests/minute per OAuth client
- **Relevant Subreddits**:
  - `r/cryptocurrency` — General crypto discussion
  - `r/solana` — Solana ecosystem
  - `r/defi` — DeFi protocols
  - `r/CryptoMoonShots` — Speculative tokens (high noise)
- **Response Fields**: `title`, `selftext`, `score`, `num_comments`,
  `created_utc`, `author`, `upvote_ratio`
- **Notes**: Free and accessible. High signal in r/cryptocurrency daily threads.

### Telegram

- **Bot API URL**: `https://api.telegram.org/bot{token}/`
- **Key Methods**:
  - `getUpdates` — Receive messages from channels the bot is in
  - `getChatMemberCount` — Channel subscriber count
- **Rate Limits**: 30 messages/second, 20 messages/minute to same chat
- **Access Pattern**: Create a bot via @BotFather, add to target channels.
  Cannot search across public channels without scraping.
- **Monitoring Approach**:
  ```python
  # Poll for new messages in monitored channels
  updates = httpx.get(f"{BOT_URL}/getUpdates?offset={last_id}").json()
  for update in updates["result"]:
      text = update.get("channel_post", {}).get("text", "")
      # Score text for sentiment
  ```
- **Notes**: Many crypto alpha groups use Telegram. Signal quality varies.

### Discord

- **Bot Gateway**: WebSocket-based, requires bot token
- **REST API**: `https://discord.com/api/v10/`
- **Key Endpoints**:
  - `GET /channels/{id}/messages` — Channel message history
  - `GET /guilds/{id}` — Server info including member count
- **Rate Limits**: 50 requests/second globally
- **Notes**: Requires bot to be invited to servers. Good for project-specific
  sentiment (e.g., monitoring a token's official Discord).

## Aggregator APIs

### Alternative.me Fear & Greed Index

- **Endpoint**: `GET https://api.alternative.me/fng/`
- **Auth**: None required (free)
- **Parameters**:
  - `limit` — Number of days (default 1, max ~4000)
  - `date_format` — `us`, `cn`, `kr`, or `world`
- **Rate Limits**: Undocumented, ~100 requests/minute observed
- **Response**:
  ```json
  {
    "data": [
      {
        "value": "25",
        "value_classification": "Extreme Fear",
        "timestamp": "1709856000"
      }
    ]
  }
  ```
- **Composition**: Volatility (25%), market momentum/volume (25%),
  social media (15%), surveys (15%), Bitcoin dominance (10%), trends (10%)
- **Notes**: Bitcoin-focused but correlates with altcoin sentiment. Updated daily.

### LunarCrush

- **Base URL**: `https://lunarcrush.com/api4/public/`
- **Auth**: API key via `Authorization: Bearer {key}`
- **Key Endpoints**:
  - `GET /coins/{symbol}/time-series/v2` — Social metrics over time
  - `GET /coins/list/v2` — All tracked coins with social stats
  - `GET /coins/{symbol}/meta/v1` — Coin metadata and current social stats
- **Rate Limits**: Free tier 100 calls/day, Pro tier 10,000 calls/day
- **Key Metrics**: `galaxy_score` (0-100 composite), `alt_rank`,
  `social_volume`, `social_score`, `social_dominance`
- **Notes**: Best aggregated social data source. Free tier is usable for
  periodic checks.

### Santiment

- **Base URL**: `https://api.santiment.net/graphql`
- **Auth**: API key via header
- **Key Queries** (GraphQL):
  ```graphql
  {
    getMetric(metric: "social_volume_total") {
      timeseriesData(slug: "solana", from: "2025-01-01", to: "2025-01-31") {
        datetime
        value
      }
    }
  }
  ```
- **Key Metrics**: `social_volume_total`, `social_dominance`,
  `sentiment_positive_total`, `sentiment_negative_total`,
  `weighted_social_sentiment`
- **Rate Limits**: Free tier 100 API calls/month, paid tiers higher
- **Notes**: Highest quality sentiment data but expensive for full access.

## On-Chain Sentiment Proxies

### Binance Funding Rates

- **Endpoint**: `GET https://fapi.binance.com/fapi/v1/fundingRate`
- **Auth**: None required for public endpoints
- **Parameters**: `symbol` (e.g., `SOLUSDT`), `limit` (default 100, max 1000)
- **Rate Limits**: 2400 request weight/minute
- **Response**:
  ```json
  [
    {
      "symbol": "SOLUSDT",
      "fundingRate": "0.00010000",
      "fundingTime": 1709856000000
    }
  ]
  ```
- **Interpretation**:
  - `> 0.01%` — Longs paying premium, bullish crowding
  - `< -0.01%` — Shorts paying premium, bearish crowding
  - `> 0.05%` — Extreme: high liquidation risk for longs
  - `< -0.05%` — Extreme: short squeeze risk
- **Notes**: Funding settles every 8 hours. Use `fundingTime` for alignment.

### Binance Long/Short Ratio

- **Endpoint**: `GET https://fapi.binance.com/futures/data/globalLongShortAccountRatio`
- **Auth**: None required
- **Parameters**: `symbol`, `period` (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d)
- **Response**:
  ```json
  [
    {
      "symbol": "SOLUSDT",
      "longShortRatio": "1.5000",
      "longAccount": "0.6000",
      "shortAccount": "0.4000",
      "timestamp": 1709856000000
    }
  ]
  ```
- **Notes**: Ratio > 2.0 or < 0.5 indicates crowded positioning.

### CoinGecko Community Data

- **Endpoint**: `GET https://api.coingecko.com/api/v3/coins/{id}`
- **Auth**: None for free tier, API key for Pro
- **Rate Limits**: 10-30 calls/minute (free), 500/minute (Pro)
- **Community Fields** (in response):
  ```json
  {
    "community_data": {
      "twitter_followers": 1234567,
      "reddit_subscribers": 456789,
      "reddit_accounts_active_48h": 12345,
      "telegram_channel_user_count": 67890
    },
    "developer_data": {
      "forks": 1234,
      "stars": 5678,
      "commit_count_4_weeks": 200
    },
    "sentiment_votes_up_percentage": 75.5,
    "sentiment_votes_down_percentage": 24.5
  }
  ```
- **Notes**: Free and comprehensive. Community data updates every few hours.
  The `sentiment_votes_up_percentage` field is a direct crowd sentiment gauge.

### CryptoQuant / Glassnode (Exchange Flows)

- **CryptoQuant API**: `https://api.cryptoquant.com/v1/`
  - `GET /btc/exchange-flows/netflow` — Net exchange flow
  - Auth: API key, free tier available with limited data
- **Glassnode API**: `https://api.glassnode.com/v1/metrics/`
  - `GET /transactions/transfers_volume_exchanges_net` — Net transfer volume
  - Auth: API key, free tier with 24h delay
- **Interpretation**:
  - Positive net flow (inflows > outflows) = coins moving to exchanges = sell pressure
  - Negative net flow (outflows > inflows) = coins leaving exchanges = accumulation
- **Notes**: Bitcoin and Ethereum focused. Limited Solana coverage on free tiers.

## Free-Tier Strategy

For cost-effective sentiment monitoring, use these free sources:

1. **Alternative.me Fear & Greed** — Daily market-wide mood (no auth)
2. **CoinGecko community data** — Token-specific social stats (no auth, rate limited)
3. **Binance funding rates** — On-chain positioning (no auth)
4. **Binance long/short ratio** — Crowd positioning (no auth)
5. **Reddit API** — Social text data (free OAuth)

This combination provides market-wide sentiment, token-specific social metrics,
and on-chain positioning data at zero cost.
