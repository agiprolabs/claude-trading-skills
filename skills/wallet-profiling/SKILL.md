---
name: wallet-profiling
description: Behavioral classification, performance analysis, and trading style detection for Solana wallets
---

# Wallet Profiling

Behavioral classification, performance analysis, and trading style detection for Solana wallets. Profile any wallet to understand how it trades, how well it performs, and whether it is worth following.

## Why Wallet Profiling Matters

### Copy-Trade Evaluation
Before mirroring another wallet's trades, you need evidence that its historical performance is genuine, consistent, and not the result of a single lucky hit. Profiling quantifies win rate, profit factor, hold time, and consistency so you can make informed decisions about which wallets merit attention.

### Smart Money Identification
Wallets that consistently buy tokens early and exit profitably are signal sources. Profiling separates genuinely skilled traders from lucky gamblers and wash-trading bots. Key differentiators: sustained profit factor above 2.0, win rates above 45% across 100+ trades, and diversified token selection.

### Counterparty Analysis
When a large wallet enters a position you hold, understanding its historical behavior (sniper vs. holder, bot vs. human) helps you anticipate what will happen next. A sniper wallet buying suggests a quick dump is coming; a swing trader buying suggests multi-day conviction.

### Risk Assessment
Token holder analysis benefits from knowing whether top holders are bots, snipers, or genuine investors. A token where 60% of holders are classified as snipers has very different risk characteristics than one held primarily by swing traders.

## Wallet Classification

### By Trading Style

Classification is based on the **median hold time** across all closed trades:

| Style | Median Hold Time | Characteristics |
|-------|-----------------|-----------------|
| Sniper | < 5 minutes | First-block buyers, MEV-adjacent, extremely fast exits |
| Scalper | 5 min – 1 hour | Quick momentum trades, high frequency |
| Day Trader | 1 – 24 hours | Intraday positions, moderate frequency |
| Swing Trader | 1 – 7 days | Multi-day conviction holds |
| Position Holder | > 7 days | Long-term accumulation, low frequency |

See `references/classification_methods.md` for the full classification algorithm.

### By Trade Size

Based on **median trade size in SOL**:

| Tier | Median Trade Size | Typical Behavior |
|------|------------------|-----------------|
| Whale | > 100 SOL | Market-moving entries, often front-run |
| Large | 10 – 100 SOL | Significant but not dominant |
| Medium | 1 – 10 SOL | Active retail traders |
| Small | < 1 SOL | Micro-cap gamblers, new wallets |

### By Behavior Type

| Type | Detection Method |
|------|-----------------|
| Bot | Low inter-trade timing variance (CV < 0.3), uniform sizing |
| Human | Variable timing, variable sizing, session-based activity |
| MEV | Sandwich patterns, consistent small profits, high frequency |

### By Focus Area

| Focus | Detection Criteria |
|-------|-------------------|
| PumpFun Specialist | > 70% of trades on PumpFun-launched tokens |
| DEX Trader | Primarily swaps on Raydium/Orca/Meteora |
| DeFi Farmer | Frequent LP add/remove, staking operations |
| NFT Trader | Significant NFT marketplace interactions |
| Multi-Strategy | No single category exceeds 50% |

## Performance Metrics

### Core Metrics

**Win Rate** — Percentage of trades that are profitable.
```
win_rate = count(pnl > 0) / count(all_closed_trades)
```
Minimum 30 trades for statistical significance. A 60% win rate across 200 trades is far more meaningful than 80% across 10 trades.

**Average ROI Per Trade** — Mean return across all closed positions.
```
avg_roi = mean((exit_value - entry_value) / entry_value)
```
Include all fees: platform fees, priority fees, and estimated slippage.

**Profit Factor** — Ratio of gross profits to gross losses.
```
profit_factor = sum(winning_pnl) / abs(sum(losing_pnl))
```
Interpretation: > 2.0 excellent, 1.5–2.0 good, 1.0–1.5 marginal, < 1.0 losing.

**Total PnL** — Cumulative profit/loss in SOL.
```
total_pnl = sum(all_trade_pnl)
```

**Maximum Drawdown** — Largest peak-to-trough decline in cumulative PnL curve.
```
drawdown = (peak_equity - trough_equity) / peak_equity
```

**Sharpe-Like Ratio** — Risk-adjusted return metric.
```
sharpe = mean(trade_returns) / std(trade_returns) * sqrt(trades_per_year)
```

See `references/performance_metrics.md` for detailed formulas, edge cases, and interpretation guidelines.

### Activity Metrics

| Metric | Calculation | What It Reveals |
|--------|------------|-----------------|
| Trades per day | total_trades / active_days | Activity level and capacity |
| Average hold time | mean(exit_time - entry_time) | Trading style confirmation |
| Token diversity | unique_tokens / total_trades | Specialization vs. diversification |
| Peak hours | mode(hour_of_trade) | Session patterns, timezone hints |
| Activity streaks | consecutive active days | Dedication and consistency |

## Data Sources

### SolanaTracker PnL API (Primary)

The SolanaTracker API provides pre-computed PnL data per wallet per token.

```python
import httpx

url = f"https://data.solanatracker.io/pnl/{wallet_address}"
headers = {"x-api-key": os.getenv("ST_API_KEY")}
resp = httpx.get(url, headers=headers)
pnl_data = resp.json()
```

Response includes per-token: `realized`, `unrealized`, `total_invested`, `total_sold`, `num_buys`, `num_sells`, `last_trade_time`.

### Helius Parsed Transactions (Detailed)

For granular transaction-level analysis, use the `helius-api` skill to fetch parsed transaction history. This provides exact timestamps, amounts, and program interactions.

### Birdeye Trader Data

Birdeye's trader endpoints provide wallet-level analytics. See the `birdeye-api` skill for endpoint details.

### DexScreener (Free Fallback)

DexScreener does not provide wallet-level PnL but can be used to validate token prices at trade timestamps.

## Copy-Trade Evaluation Framework

Before following a wallet's trades, verify these criteria:

### Minimum Requirements
- **Trade history**: At least 50 closed trades (100+ preferred)
- **Time span**: Active for at least 30 days
- **Consistent performance**: Rolling 7-day win rate standard deviation < 15%
- **Reasonable sizing**: No single trade > 20% of observed portfolio
- **Diverse tokens**: At least 10 unique tokens traded

### Green Flags
- Profit factor > 1.8 sustained over 60+ days
- Win rate 45–65% (unrealistically high rates suggest wash trading)
- Moderate trade frequency (2–20 trades/day)
- Mixed hold times indicating adaptive strategy
- Gradual equity curve growth (not step-function jumps)

### Red Flags
- **New wallet** (< 14 days old): Possible sybil or one-hit-wonder
- **Single big win**: One trade accounts for > 50% of total PnL
- **Declining performance**: Last-30-day metrics significantly below all-time
- **Bot-like patterns**: Uniform timing/sizing without proportional edge
- **Extreme win rate**: > 80% often indicates small wins with catastrophic losses
- **Concentration**: > 50% of PnL from a single token
- **Wash trading signals**: Repeated buy/sell of same token with minimal price movement

### Risk Score Calculation

```python
risk_score = 0  # 0 = low risk, 100 = high risk

if wallet_age_days < 14:
    risk_score += 25
if top_trade_pnl_pct > 0.5:
    risk_score += 20
if recent_pf < historical_pf * 0.7:
    risk_score += 15
if bot_probability > 0.7:
    risk_score += 15
if win_rate > 0.8:
    risk_score += 10
if unique_tokens < 5:
    risk_score += 15
```

## Integration with Other Skills

- **`whale-tracking`**: Identify large wallets, then profile them here for behavioral context
- **`token-holder-analysis`**: Profile top holders of a token to assess holder quality
- **`solana-onchain`**: Fetch raw transaction data for deep-dive analysis
- **`helius-api`**: Parsed transaction history for granular trade reconstruction
- **`birdeye-api`**: Token price data for PnL validation

## Quick Start

### Profile a Single Wallet

```python
# Set environment variables
# export WALLET_ADDRESS=YourTargetWallet...
# export ST_API_KEY=your_solanatracker_key  (optional)

python scripts/profile_wallet.py
# Or use demo mode:
python scripts/profile_wallet.py --demo
```

### Compare Multiple Wallets

```python
# export WALLET_ADDRESSES=Wallet1...,Wallet2...,Wallet3...
# export ST_API_KEY=your_solanatracker_key  (optional)

python scripts/compare_wallets.py
# Or use demo mode:
python scripts/compare_wallets.py --demo
```

## Files

| File | Description |
|------|-------------|
| `references/classification_methods.md` | Hold time, size, bot detection, and focus classification algorithms |
| `references/performance_metrics.md` | Detailed metric formulas, interpretation, edge cases, and decay detection |
| `scripts/profile_wallet.py` | Profile a single wallet: fetch data, compute metrics, classify, report |
| `scripts/compare_wallets.py` | Compare multiple wallets side-by-side with ranking |

## Dependencies

```bash
uv pip install httpx
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `WALLET_ADDRESS` | For profile_wallet.py | Solana wallet address to profile |
| `WALLET_ADDRESSES` | For compare_wallets.py | Comma-separated wallet addresses |
| `ST_API_KEY` | No | SolanaTracker API key for PnL data |
