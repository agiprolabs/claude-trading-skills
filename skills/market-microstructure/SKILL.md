---
name: market-microstructure
description: DEX orderflow analysis, trade classification, buyer/seller pressure, and microstructure signals for Solana tokens
---

# Market Microstructure — DEX Orderflow Analysis

## Overview

Market microstructure on Solana DEXes differs fundamentally from traditional finance.
There are no orderbooks on AMMs — every trade is a swap against a liquidity pool. Yet
trade flow analysis remains powerful: the sequence, size, and direction of swaps reveal
accumulation, distribution, whale activity, and wash trading patterns.

This skill covers:
- **Trade classification** — identifying buys vs sells from swap direction
- **Volume profiles** — time-based and size-based breakdowns
- **Buyer/seller pressure** — ratio metrics, net flow, trade count asymmetry
- **Trade size distribution** — whale detection, retail vs institutional flow
- **Flow momentum signals** — acceleration, volume spikes, composite scores
- **Token velocity** — turnover rate as a sentiment proxy
- **Wash trading detection** — spotting fake volume and bot patterns

## Why Microstructure Matters on DEXes

On CEXes, microstructure means orderbook depth, bid-ask spread, and queue position.
On AMMs, liquidity sits in pool curves — there is no spread or queue. But the **trade
tape** (the chronological list of swaps) contains rich signal:

1. **Who is trading?** — Whale wallets vs retail, smart money vs bots
2. **How are they trading?** — Large single swaps vs DCA-style splits
3. **When are they trading?** — Volume clustering around events or time zones
4. **What direction?** — Net buy vs sell pressure over sliding windows

These signals feed into entry/exit timing, position sizing, and token quality scoring.

## Trade Classification

### Buy vs Sell Identification

On Solana DEXes, every swap has an input token and output token:

| Swap Direction | Classification | Meaning |
|----------------|---------------|---------|
| SOL → Token | **Buy** | Trader spending SOL to acquire token |
| USDC → Token | **Buy** | Trader spending stables to acquire token |
| Token → SOL | **Sell** | Trader converting token back to SOL |
| Token → USDC | **Sell** | Trader converting token to stables |
| Token A → Token B | Context-dependent | Classify based on which token you're analyzing |

### From API Data Sources

**Birdeye Trade History** (`/defi/txs/token`):
- Returns `side` field: `"buy"` or `"sell"`
- Includes `from` (input token) and `to` (output token) amounts

**DexScreener Pair Trades:**
- Returns `type` field indicating swap direction relative to the pair

**Helius Parsed Transactions:**
- Parse swap instructions to extract input/output mints and amounts
- Classify based on which mint matches your target token

See `references/trade_classification.md` for detailed classification logic and size buckets.

## Volume Profiles

### Time-Based Profiles

Aggregate trade volume into fixed time buckets to identify patterns:

```python
# Hourly volume profile
hourly_volume = {}
for trade in trades:
    hour = trade["timestamp"] // 3600 * 3600
    hourly_volume.setdefault(hour, {"buy_vol": 0, "sell_vol": 0})
    if trade["side"] == "buy":
        hourly_volume[hour]["buy_vol"] += trade["volume_usd"]
    else:
        hourly_volume[hour]["sell_vol"] += trade["volume_usd"]
```

Key metrics from time profiles:
- **Peak hours** — when is the token most actively traded?
- **Volume trend** — is volume increasing, decreasing, or stable?
- **Volume anomalies** — spikes exceeding 3x the rolling average

### Size-Based Profiles

Classify trades into size buckets to separate whale activity from retail:

| Bucket | SOL Range | Typical Actor |
|--------|-----------|---------------|
| Micro | < 0.1 SOL | Dust / test trades |
| Small | 0.1 – 1 SOL | Retail traders |
| Medium | 1 – 10 SOL | Active traders |
| Large | 10 – 50 SOL | Serious positions |
| Whale | 50+ SOL | Whales / institutions |

## Buyer/Seller Pressure Metrics

### Core Ratios

```python
def compute_pressure(trades: list[dict], period_seconds: int = 3600) -> dict:
    """Compute buy/sell pressure metrics over a time period."""
    buy_vol = sum(t["volume_usd"] for t in trades if t["side"] == "buy")
    sell_vol = sum(t["volume_usd"] for t in trades if t["side"] == "sell")
    total_vol = buy_vol + sell_vol

    buy_trades = sum(1 for t in trades if t["side"] == "buy")
    sell_trades = sum(1 for t in trades if t["side"] == "sell")
    total_trades = buy_trades + sell_trades

    return {
        "buy_sell_ratio": buy_vol / sell_vol if sell_vol > 0 else float("inf"),
        "buy_volume_pct": buy_vol / total_vol if total_vol > 0 else 0.5,
        "net_flow_usd": buy_vol - sell_vol,
        "trade_count_ratio": buy_trades / total_trades if total_trades > 0 else 0.5,
    }
```

### Signal Interpretation

| Metric | Bullish | Neutral | Bearish |
|--------|---------|---------|---------|
| Buy Volume % | > 60% | 40–60% | < 40% |
| Net Flow | Positive, increasing | Near zero | Negative, increasing |
| Trade Count Ratio | > 0.55 | 0.45–0.55 | < 0.45 |
| Large Trade Ratio | High buy-side | Balanced | High sell-side |

See `references/flow_signals.md` for the full signal catalog and composite scoring.

## Trade Size Distribution

Analyzing the distribution of trade sizes reveals market structure:

```python
import statistics

def analyze_trade_sizes(trades: list[dict]) -> dict:
    """Analyze trade size distribution."""
    sizes = [t["volume_usd"] for t in trades]
    if not sizes:
        return {}

    return {
        "mean": statistics.mean(sizes),
        "median": statistics.median(sizes),
        "stdev": statistics.stdev(sizes) if len(sizes) > 1 else 0,
        "skew_indicator": statistics.mean(sizes) / statistics.median(sizes),
        "max_trade": max(sizes),
        "whale_pct": sum(s for s in sizes if s > 5000) / sum(sizes),
    }
```

**Interpreting skew:** A `skew_indicator` (mean/median) well above 1.0 indicates a
fat-tailed distribution — a few large trades dominate. This is normal for tokens with
whale interest but can also signal manipulation.

## Momentum Signals from Trade Flow

### Volume Acceleration

Compare current period volume to the previous period:

```python
acceleration = current_volume / previous_volume if previous_volume > 0 else 0
```

- **acceleration > 2.0** — volume surge, potential breakout or dump
- **acceleration 0.8–1.2** — stable activity
- **acceleration < 0.5** — dying interest

### Buy Pressure Acceleration

Track how the buy ratio changes over time:

```python
current_buy_ratio = current_buy_vol / current_total_vol
previous_buy_ratio = prev_buy_vol / prev_total_vol
buy_momentum = current_buy_ratio - previous_buy_ratio
```

Positive `buy_momentum` with increasing volume is a strong accumulation signal.

## Token Velocity

Token velocity measures how frequently tokens change hands:

```python
velocity = daily_volume / circulating_supply
```

| Velocity | Interpretation |
|----------|---------------|
| < 0.01 | Low activity, illiquid, or strong holders |
| 0.01–0.05 | Normal trading activity |
| 0.05–0.20 | Active trading, possible speculation |
| > 0.20 | Very high turnover, potential wash trading |

High velocity combined with low unique trader count is a wash trading red flag.

## Wash Trading Detection

Wash trading inflates volume to make a token appear more active than it truly is.
Key detection signals:

1. **Low unique trader ratio** — `unique_wallets / trade_count < 0.3`
2. **Volume/TVL anomaly** — `daily_volume / tvl > 10` (volume vastly exceeds liquidity)
3. **Uniform trade sizes** — low entropy in trade size distribution
4. **Self-trading** — same wallet on both sides within short windows
5. **Funded-together clusters** — multiple wallets funded from the same source

See `references/wash_trading.md` for detailed detection methods and scoring.

## Data Sources

### Birdeye API

Primary source for trade history on Solana tokens:
- `GET /defi/txs/token` — recent trades for a token
- `GET /defi/ohlcv` — candle data with volume
- `GET /defi/price/volume` — aggregated volume data

Requires API key. See the `birdeye-api` skill for endpoint details.

### DexScreener API

Free, no-auth alternative for pair-level data:
- `GET /latest/dex/tokens/{address}` — token pairs with volume
- `GET /latest/dex/pairs/solana/{pairAddress}` — pair details

### Helius API

For wallet-level trade analysis and parsed transactions:
- Parse swap transactions to extract trade details
- Attribute trades to specific wallets
- See the `helius-api` skill for transaction parsing.

## Composite Momentum Score

Combine multiple flow signals into a single score (range: -100 to +100):

```python
def compute_momentum_score(
    buy_ratio: float,
    volume_accel: float,
    whale_buy_pct: float,
    unique_trader_trend: float,
) -> float:
    """Compute composite momentum score from flow signals.

    Args:
        buy_ratio: Buy volume / total volume (0 to 1).
        volume_accel: Current vol / previous vol.
        whale_buy_pct: Whale buy volume / total whale volume (0 to 1).
        unique_trader_trend: Change in unique traders vs previous period.

    Returns:
        Score from -100 (strong sell pressure) to +100 (strong buy pressure).
    """
    # Buy ratio component: 0.5 = neutral, maps to [-40, +40]
    buy_component = (buy_ratio - 0.5) * 80

    # Volume acceleration: >1 = growing, maps to [-20, +20]
    vol_component = min(max((volume_accel - 1.0) * 20, -20), 20)

    # Whale direction: 0.5 = neutral, maps to [-25, +25]
    whale_component = (whale_buy_pct - 0.5) * 50

    # Unique trader growth: positive = healthy, maps to [-15, +15]
    trader_component = min(max(unique_trader_trend * 15, -15), 15)

    score = buy_component + vol_component + whale_component + trader_component
    return max(-100, min(100, score))
```

| Score Range | Interpretation |
|-------------|---------------|
| +60 to +100 | Strong accumulation — heavy buy pressure |
| +20 to +60 | Moderate buying — cautious accumulation |
| -20 to +20 | Neutral / balanced flow |
| -60 to -20 | Moderate selling — distribution underway |
| -100 to -60 | Strong distribution — heavy sell pressure |

## Integration with Other Skills

| Skill | How It Connects |
|-------|----------------|
| `birdeye-api` | Primary data source for trade history and volume |
| `helius-api` | Wallet-attributed trade data from parsed transactions |
| `liquidity-analysis` | Volume/TVL ratios, liquidity context for flow signals |
| `whale-tracking` | Identify whale wallets for large trade attribution |
| `token-holder-analysis` | Supply distribution context for velocity metrics |
| `position-sizing` | Use flow signals to adjust entry sizing |
| `regime-detection` | Combine flow momentum with regime classification |

## Files

### References
- `references/trade_classification.md` — Buy/sell classification logic, size buckets, aggregation
- `references/flow_signals.md` — Complete signal catalog with formulas and interpretation
- `references/wash_trading.md` — Detection methods, metrics, and risk scoring

### Scripts
- `scripts/trade_flow_analysis.py` — Fetch trades, classify, compute flow signals and momentum
- `scripts/volume_profile.py` — Hourly volume profiles, trend detection, anomaly identification
