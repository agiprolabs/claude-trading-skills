# Wallet Discovery for Copy Trading

Methods, sources, and scoring for finding wallets worth copying on Solana.

## Discovery Sources

### SolanaTracker — Top Traders per Token

The primary discovery source. Returns the highest-PnL wallets for any given token.

- **Endpoint**: `GET https://data.solanatracker.io/top-traders/{token_address}`
- **Authentication**: `x-api-key` header (optional for basic access)
- **Rate Limit**: 10 req/min (free), 60 req/min (paid)
- **Response fields**: `wallet`, `pnl`, `trades`, `bought`, `sold`, `volume`

```bash
curl -H "x-api-key: $ST_API_KEY" \
  "https://data.solanatracker.io/top-traders/So11111111111111111111111111111111111111112"
```

**Workflow**: Identify a token that recently performed well, pull top traders, then evaluate each wallet independently.

### SolanaTracker — Wallet PnL

Retrieve full trade-level PnL for a specific wallet.

- **Endpoint**: `GET https://data.solanatracker.io/pnl/{wallet_address}`
- **Response fields**: `summary.total_pnl`, `summary.total_trades`, `summary.win_rate`, `summary.profit_factor`, `tokens[]` (per-token breakdown)

```bash
curl -H "x-api-key: $ST_API_KEY" \
  "https://data.solanatracker.io/pnl/WALLET_ADDRESS_HERE"
```

### Birdeye — Trader Rankings

Birdeye provides token-level and global trader leaderboards.

- **Endpoint**: `GET https://public-api.birdeye.so/defi/v3/token/trade/top-traders`
- **Parameters**: `address` (token mint), `time_frame` (1h, 4h, 24h, 7d, 30d), `sort_by` (pnl, volume)
- **Authentication**: `X-API-KEY` header
- **Rate Limit**: 100 req/min (free tier)

```bash
curl -H "X-API-KEY: $BIRDEYE_API_KEY" \
  "https://public-api.birdeye.so/defi/v3/token/trade/top-traders?address=TOKEN&time_frame=24h&sort_by=pnl"
```

### Helius — Transaction History

Not a discovery source per se, but essential for building a wallet's complete trade history after discovery.

- **Endpoint**: `POST https://api.helius.xyz/v0/addresses/{address}/transactions?api-key={key}`
- **Returns**: Parsed transaction history with swap details, token transfers, and program interactions
- **Use case**: After finding a wallet via SolanaTracker/Birdeye, fetch full history to build the profile

### Community and Social Sources

- **GMGN.ai**: Wallet leaderboards by timeframe and chain
- **Cielo Finance**: Multi-chain wallet tracking with P&L
- **Twitter/X**: Alpha callers often share wallet addresses
- **Telegram groups**: Whale alert channels, alpha groups
- **Arkham Intelligence**: Institutional-grade wallet labeling

**Caution**: Social sources have strong survivorship bias. Always run independent evaluation before adding to a copy list.

## Discovery Workflow

### Step 1 — Seed Token Selection

Start with tokens that recently had significant price moves:

1. Pull trending tokens from DexScreener or Birdeye
2. Filter for tokens with > $100K 24h volume (sufficient liquidity)
3. Filter for tokens that gained > 50% in the last 24h (someone profited)

### Step 2 — Extract Top Traders

For each seed token, pull top traders:

```python
import httpx

async def get_top_traders(token: str, api_key: str) -> list[dict]:
    """Get top PnL wallets for a token from SolanaTracker."""
    url = f"https://data.solanatracker.io/top-traders/{token}"
    headers = {"x-api-key": api_key}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()
```

### Step 3 — Deduplicate Across Tokens

The same wallet may appear as a top trader on multiple tokens. Track unique wallets and how many seed tokens they appear in — appearing on multiple tokens is a positive signal of breadth.

### Step 4 — Quick Filter

Before running full evaluation, apply quick filters to reduce the candidate set:

```python
def quick_filter(wallet_data: dict) -> bool:
    """Fast pre-filter before expensive evaluation."""
    pnl = wallet_data.get("pnl", 0)
    trades = wallet_data.get("trades", 0)
    if trades < 10:
        return False  # Not enough data from this token alone
    if pnl <= 0:
        return False  # Not profitable on this token
    return True
```

### Step 5 — Full Evaluation

Run comprehensive evaluation on each candidate (see `scripts/evaluate_wallet.py`).

### Step 6 — Rank and Select

Sort evaluated wallets by composite copy score. Select the top N (typically 3-10) for your copy list.

## Scoring Wallets for Copy Suitability

### Composite Score Components

| Component | Weight | Source | Calculation |
|-----------|--------|--------|-------------|
| Trade count | 15% | PnL API | `min(count / 200, 1.0) * 100` |
| Win rate | 20% | PnL API | `max((wr - 0.40) / 0.30, 0) * 100` |
| Profit factor | 25% | PnL API | `min((pf - 1.0) / 3.0, 1.0) * 100` |
| Consistency | 20% | Computed | `(1.0 - rolling_wr_stddev) * 100` |
| Recency | 10% | PnL API | `max(1.0 - days_inactive / 14, 0) * 100` |
| Human probability | 10% | Computed | `(1.0 - bot_prob) * 100` |

### Automated Thresholds

| Score Range | Label | Action |
|-------------|-------|--------|
| 80-100 | Excellent | Add to copy list, standard allocation |
| 60-79 | Good | Add with reduced allocation, review weekly |
| 40-59 | Marginal | Watchlist only, do not copy yet |
| 0-39 | Poor | Reject |

## Red Flags

### New Wallets
Wallets created in the last 7 days with high PnL are likely insider wallets or airdrop farmers. Require at least 30 days of history.

### Single-Token Profits
If > 50% of a wallet's total PnL comes from one token, the track record is not diversified enough. One lucky trade does not indicate skill.

### Insider Patterns
Wallets that consistently buy tokens within the first few transactions after pool creation, across many tokens, may have insider access to launch schedules. Their edge is not replicable.

### Wash Trading
Wallets that buy and sell the same token repeatedly in small amounts to inflate trade count and win rate. Use the `sybil-detection` skill to check for cluster behavior.

### Abnormal Timing
Trades at perfectly regular intervals (e.g., exactly every 60 seconds) indicate a bot. Bots have latency advantages that cannot be replicated by copy trading.

### Concentration in Low-Liquidity Tokens
High PnL on tokens with < $10K daily volume may reflect price manipulation rather than genuine alpha. Verify that the tokens traded had real liquidity.

## Batch Discovery Example

```python
async def discover_candidates(
    seed_tokens: list[str],
    api_key: str,
    min_trades: int = 10,
) -> dict[str, dict]:
    """Discover unique profitable wallets across seed tokens."""
    candidates: dict[str, dict] = {}
    for token in seed_tokens:
        traders = await get_top_traders(token, api_key)
        for t in traders:
            wallet = t.get("wallet", "")
            if not quick_filter(t):
                continue
            if wallet in candidates:
                candidates[wallet]["appearances"] += 1
                candidates[wallet]["tokens"].append(token)
            else:
                candidates[wallet] = {
                    "appearances": 1,
                    "tokens": [token],
                    "first_seen_pnl": t.get("pnl", 0),
                }
    return candidates
```

Wallets appearing across 3 or more seed tokens are strong candidates for further evaluation.
