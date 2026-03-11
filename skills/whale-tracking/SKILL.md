---
name: whale-tracking
description: Large wallet monitoring, accumulation and distribution detection, and smart money signal generation for Solana tokens
---

# Whale Tracking for Solana Tokens

Whale tracking monitors the on-chain behavior of large wallets to detect accumulation, distribution, and smart money movements before they become visible in price action. On Solana, where token ownership is highly concentrated and whale transactions can move markets instantly, tracking large holders is one of the highest-signal alpha sources available.

## Why Whale Tracking Matters

A single large wallet selling 5% of a token's supply can crash the price 30-50% on thin Solana DEX liquidity. Conversely, a known profitable wallet accumulating a new token often precedes major price runs. Whale tracking converts on-chain transparency into actionable intelligence.

Key use cases:

- **Early warning**: Detect large holder sells before the price impact fully propagates
- **Smart money following**: Identify wallets with strong track records and monitor their new positions
- **Accumulation detection**: Spot gradual buying by whales who split orders to avoid detection
- **Distribution detection**: Catch insiders or early investors offloading positions
- **Risk assessment**: Evaluate token concentration risk before entering a position

## What Constitutes a Whale

Whale classification depends on context. A wallet holding $50K of a $1M market cap token is a whale; the same $50K in SOL is not. Use relative and absolute thresholds:

### Absolute Thresholds

| Category | Trade Size | Portfolio Size | Typical Behavior |
|----------|-----------|---------------|-----------------|
| Retail | < 10 SOL | < 100 SOL | Reactive, follows trends |
| Mid-size | 10-100 SOL | 100-1,000 SOL | Mixed strategies |
| Whale | 100-1,000 SOL | 1,000-10,000 SOL | Informed, moves markets |
| Mega-whale | > 1,000 SOL | > 10,000 SOL | Market makers, funds, insiders |

### Relative Thresholds (Per Token)

| Metric | Threshold | Significance |
|--------|-----------|-------------|
| % of supply held | > 2% | Significant holder |
| % of daily volume | > 5% single trade | Market-moving transaction |
| Top N holders | Top 20 | Core holder group |
| Concentration ratio | Top 10 hold > 50% | High concentration risk |

Use both absolute and relative metrics. A 50 SOL trade in a $200K market cap token is whale-level; the same trade in a $50M token is retail.

## Accumulation vs Distribution Patterns

### Accumulation Signals

Accumulation is when a whale builds a position over time, often trying to minimize price impact.

**DCA pattern** (Dollar-Cost Averaging):
- Multiple buys of similar size over hours or days
- Buys at regular intervals (e.g., every 30 minutes)
- Position grows steadily without large single transactions

**Dip buying**:
- Buys concentrated during price dips
- Larger-than-usual purchases when price drops > 10%
- Position increases during periods of general selling

**Multi-wallet accumulation**:
- New wallets funded from the same source
- Each wallet buys small amounts of the same token
- Positions later consolidated into a primary wallet

**Detection heuristics**:
```
accumulation_score = 0
if buy_count > sell_count * 2:       accumulation_score += 2
if avg_buy_size > avg_sell_size:     accumulation_score += 1
if position_change_7d > 0:          accumulation_score += 1
if buys_during_dips > buys_on_pump:  accumulation_score += 2
if dca_pattern_detected:             accumulation_score += 2
# Score >= 4 = likely accumulating
```

### Distribution Signals

Distribution is when a whale reduces or exits a position, often gradually to avoid crashing the price.

**Gradual selling**:
- Multiple sells over days, each < 5% of position
- Sells increase in frequency over time
- Position shrinks steadily

**Transfer to exchange**:
- Tokens transferred to known exchange deposit addresses
- Large transfers to Binance, OKX, Bybit hot wallets
- Often precedes selling by hours or days

**Rapid exit**:
- Single large market sell (> 20% of position)
- Often triggers cascading liquidations
- Visible as large red candles with high volume

**Detection heuristics**:
```
distribution_score = 0
if sell_count > buy_count * 2:        distribution_score += 2
if position_change_7d < 0:           distribution_score += 1
if transfers_to_exchanges > 0:       distribution_score += 3
if sell_frequency_increasing:        distribution_score += 2
if position_pct_remaining < 50:      distribution_score += 1
# Score >= 4 = likely distributing
```

## Whale Watchlist Management

Maintain a watchlist of wallets worth tracking. Sources for discovering whale wallets:

### Discovery Methods

1. **Top holders per token**: Query `getTokenLargestAccounts` for any token of interest
2. **Large transaction monitoring**: Watch for trades > 100 SOL on key tokens
3. **Profitable trader rankings**: Use SolanaTracker or Birdeye top trader endpoints
4. **Known fund wallets**: Public wallet addresses of crypto funds and DAOs
5. **Cross-referencing**: Wallets that appear in top holders of multiple successful tokens

### Watchlist Structure

Each watchlist entry should track:

```python
whale_entry = {
    "address": "WhaLe...",
    "label": "Smart money #47",        # Human-readable label
    "discovered": "2026-01-15",         # When added to watchlist
    "discovery_reason": "top_trader",   # How they were found
    "win_rate": 0.72,                   # Historical trade win rate
    "avg_pnl": 3.4,                     # Average PnL multiplier
    "tokens_tracked": 12,               # Number of tokens held
    "last_active": "2026-03-09",        # Last on-chain activity
    "tags": ["dex_trader", "sniper"],   # Classification tags
}
```

### Wallet Classification Tags

| Tag | Description |
|-----|-------------|
| `sniper` | Buys tokens within minutes of launch |
| `dex_trader` | Primarily trades on DEXes |
| `accumulator` | Builds positions gradually |
| `flipper` | Short hold times, quick profit-taking |
| `insider` | Connected to token teams (funded by deployer) |
| `fund` | Institutional or fund wallet |
| `market_maker` | Provides liquidity, two-sided flow |

## Cross-Token Analysis

Whale tracking becomes most powerful when you analyze whale behavior across multiple tokens simultaneously.

### Convergence Signals

When multiple tracked whales buy the same token independently, the signal strength compounds:

| Whale Count | Signal | Confidence |
|-------------|--------|------------|
| 1 whale buying | Informational | Low |
| 2-3 whales buying | Notable | Medium |
| 4+ whales buying | Strong convergence | High |
| Whales + volume spike | Confirmed momentum | Very high |

### Cross-Token Flow Analysis

Track where whale capital flows:

```
Token A (selling) → SOL → Token B (buying)

If multiple whales rotate from A to B:
  - Bearish for Token A (smart money exiting)
  - Bullish for Token B (smart money entering)
```

## Data Sources

Whale tracking on Solana uses multiple data sources. See `references/data_sources.md` for complete details.

| Source | Use Case | Auth Required |
|--------|----------|---------------|
| Helius | Transaction history, webhooks | Yes (free tier available) |
| SolanaTracker | Top traders, wallet PnL | Yes |
| Birdeye | Token holder rankings | Yes (free tier available) |
| Solana RPC | Token accounts, signatures | No (public endpoints) |

### Helius Webhooks for Real-Time Tracking

Helius webhooks enable real-time whale alerts without polling:

```python
# Webhook configuration for whale wallet monitoring
webhook_config = {
    "webhookURL": "https://your-server.com/whale-alerts",
    "transactionTypes": ["SWAP", "TRANSFER"],
    "accountAddresses": [
        "WhaLe1...",  # Tracked whale wallets
        "WhaLe2...",
    ],
    "webhookType": "enhanced",  # Parsed transaction data
}
```

## Signal Generation

Convert whale activity into trading signals. Whale signals are one input to a broader decision framework, not standalone trading triggers.

### Signal Types

**Whale Buy Signal**:
- Whale buys > 100 SOL of a token
- Confidence increases with: whale track record, buy size, number of whales buying
- Weaken signal if: token is very new (< 24h), whale is known flipper, high concentration risk

**Whale Sell Signal**:
- Whale sells > 25% of position or > 100 SOL
- Confidence increases with: multiple whales selling, transfers to exchanges, increasing sell frequency
- Weaken signal if: whale is taking partial profit after large gain, whale is known rebalancer

**Accumulation Signal**:
- Whale accumulation score >= 4 (see scoring above)
- Strongest when: multiple whales accumulating same token, accumulation during price downtrend
- Time horizon: days to weeks (accumulation is a slow signal)

**Distribution Signal**:
- Whale distribution score >= 4
- Strongest when: team/insider wallets distributing, post-unlock distribution, increasing sell pace
- Time horizon: hours to days (distribution can accelerate quickly)

### Signal Scoring

```python
def compute_whale_signal(whale_activity: dict) -> dict:
    """Combine whale activity indicators into a composite signal."""
    score = 0.0

    # Trade direction: +1 for buy, -1 for sell
    direction = 1 if whale_activity["is_buy"] else -1

    # Size factor: larger trades = stronger signal
    size_sol = whale_activity["size_sol"]
    if size_sol > 500:
        score += direction * 3
    elif size_sol > 100:
        score += direction * 2
    else:
        score += direction * 1

    # Whale quality: better track record = stronger signal
    win_rate = whale_activity["whale_win_rate"]
    score *= (0.5 + win_rate)  # 0.5x to 1.5x multiplier

    # Convergence: multiple whales = stronger signal
    whale_count = whale_activity["concurrent_whale_count"]
    score *= (1 + 0.3 * (whale_count - 1))

    return {
        "score": round(score, 2),
        "direction": "bullish" if score > 0 else "bearish",
        "confidence": "high" if abs(score) > 5 else "medium" if abs(score) > 2 else "low",
    }
```

## Integration with Other Skills

Whale tracking works best when combined with other analysis:

| Skill | Integration |
|-------|-------------|
| `token-holder-analysis` | Identify concentration risk, insider wallets |
| `liquidity-analysis` | Estimate price impact of whale trades |
| `solana-onchain` | Wallet profiling, transaction history |
| `slippage-modeling` | Predict slippage for whale-sized trades |
| `risk-management` | Factor whale concentration into position sizing |
| `helius-api` | Transaction fetching, webhook setup |

## Files

### References
- `references/detection_methods.md` — Accumulation/distribution detection algorithms, whale classification, alert thresholds and scoring systems
- `references/data_sources.md` — Complete guide to Helius, SolanaTracker, Birdeye, and on-chain data sources for whale tracking

### Scripts
- `scripts/track_whales.py` — Fetches top holders for a token, classifies whale activity as accumulating/distributing/holding, prints a whale report. Run with `--demo` for synthetic data mode.
- `scripts/whale_alerts.py` — Monitors a watchlist of whale wallets for new large transactions, classifies trades, and prints alerts. Run with `--demo` for simulated whale trades.

## Limitations and Caveats

- **Privacy wallets**: Whales using multiple wallets or mixers can evade tracking
- **Misleading signals**: Whales may intentionally create visible accumulation to attract followers, then dump
- **Latency**: By the time you detect a whale buy, the price impact may already be priced in
- **False positives**: Internal transfers between a whale's own wallets look like buys/sells
- **Exchange wallets**: Centralized exchange hot wallets show massive flows that are not individual whale activity
- **Not financial advice**: Whale activity is informational input for analysis, not a standalone trading recommendation
