---
name: copy-trading
description: Wallet evaluation, monitoring, and copy-trade strategy design for Solana DEX trading
---

# Copy Trading

Wallet evaluation, monitoring, and copy-trade strategy design for Solana DEX trading. Identify profitable wallets on-chain, evaluate whether their edge is real and replicable, monitor their activity in real time, and execute proportionally-sized trades with independent risk controls.

## What Copy Trading Means on Solana

Copy trading is the practice of monitoring one or more wallets that have demonstrated consistent profitability and replicating their trades in your own wallet. On Solana, every DEX swap is publicly visible on-chain within seconds, making it technically feasible to detect and follow any wallet's activity.

### How It Differs from TradFi Copy Trading

| Dimension | TradFi (eToro, etc.) | Solana On-Chain |
|-----------|---------------------|-----------------|
| Data source | Platform-reported P&L | Verifiable on-chain transactions |
| Latency | Minutes to hours | Seconds (websocket) to sub-second (gRPC) |
| Front-running risk | Low | High (MEV bots, sandwich attacks) |
| Trade cost | Commissions + spread | Gas + slippage + priority fees |
| Capacity | High (large-cap equities) | Low (micro-cap tokens have thin liquidity) |
| Signal decay | Slow | Fast (PumpFun tokens move in minutes) |
| Transparency | Partial (delayed reporting) | Full (every transaction is public) |

The core tradeoff: Solana provides perfect transparency but introduces execution risk. The wallet you copy got a price that no longer exists by the time you trade.

## The Copy-Trade Pipeline

### Stage 1 — Discovery

Find wallets with strong track records. Sources include:

- **SolanaTracker Top Traders**: `GET /top-traders/{token}` returns the highest-PnL wallets for any token
- **Birdeye Trader Rankings**: wallet-level P&L leaderboards by token or globally
- **On-chain leaderboards**: community-built dashboards (GMGN, Cielo, Arkham)
- **Social signals**: wallets shared on Twitter/X or Telegram alpha groups
- **Your own analysis**: run `token-holder-analysis` on a token that performed well, then profile the top holders

See `references/wallet_discovery.md` for detailed source documentation and scoring methodology.

### Stage 2 — Evaluation

Every discovered wallet must pass quantitative evaluation before it enters a copy list. Use the `wallet-profiling` skill for deep behavioral analysis, then apply copy-trade-specific criteria.

**Minimum thresholds:**

| Metric | Minimum | Why |
|--------|---------|-----|
| Trade count (30d) | >= 50 | Statistical significance |
| Win rate | >= 55% | Edge above random |
| Profit factor | >= 1.5 | Wins meaningfully exceed losses |
| Last active | Within 7 days | Still trading, not abandoned |
| Distinct tokens traded | >= 10 | Not a one-token wonder |
| Max single-trade % of total PnL | < 40% | Not reliant on one lucky hit |
| Bot probability | < 30% | Human-like timing patterns |

Run `scripts/evaluate_wallet.py` for a comprehensive copy-trade suitability assessment.

### Stage 3 — Filtering

After evaluation, apply additional filters:

- **Consistency check**: rolling 7-day win rate should not swing below 40% in any period
- **Style compatibility**: understand whether the wallet is a sniper, scalper, or swing trader — your infrastructure must match their speed
- **Size compatibility**: if they trade 500 SOL per position and you have 10 SOL total, proportional sizing may be too small to cover fees
- **Sybil check**: use the `sybil-detection` skill to verify the wallet is not part of a wash-trading cluster

### Stage 4 — Monitoring

Once a wallet passes evaluation and filtering, set up real-time monitoring.

**Monitoring approaches (fastest to simplest):**

1. **Yellowstone gRPC**: sub-second latency, streams all transactions for subscribed wallets
2. **Helius Enhanced WebSocket**: near-real-time with parsed transaction data
3. **Polling via RPC**: `getSignaturesForAddress` every 5-10 seconds — simple but slower

See `references/execution_strategy.md` for implementation details on each approach.

### Stage 5 — Execution

When a monitored wallet executes a swap:

1. **Detect** the transaction (via monitoring infrastructure)
2. **Parse** the trade: token address, direction (buy/sell), size
3. **Validate** the token: check liquidity, holder distribution, honeypot risk
4. **Size** the position: proportional to your portfolio, not theirs
5. **Execute** via Jupiter aggregator with appropriate slippage tolerance
6. **Record** the copy trade with attribution to the source wallet

### Stage 6 — Risk Management

Copy trades require independent risk controls that do not depend on the copied wallet's behavior.

See `references/risk_framework.md` for the complete framework.

**Key limits:**

| Control | Recommended Value | Purpose |
|---------|------------------|---------|
| Max allocation per wallet | 10-20% of portfolio | Diversification across signal sources |
| Max concurrent copy positions | 3-5 | Prevent overexposure |
| Per-trade stop loss | -15% to -25% | Independent downside protection |
| Daily copy-trade loss limit | -5% of portfolio | Circuit breaker |
| Weekly copy-trade loss limit | -10% of portfolio | Longer-term circuit breaker |

## Wallet Scoring for Copy Suitability

Composite score from 0-100 based on weighted criteria:

```
copy_score = (
    trade_count_score * 0.15 +
    win_rate_score * 0.20 +
    profit_factor_score * 0.25 +
    consistency_score * 0.20 +
    recency_score * 0.10 +
    human_probability_score * 0.10
)
```

**Component calculations:**

- **Trade count score**: `min(trade_count / 200, 1.0) * 100` — maxes out at 200 trades
- **Win rate score**: `max((win_rate - 0.40) / 0.30, 0) * 100` — scaled from 40% to 70%
- **Profit factor score**: `min((pf - 1.0) / 3.0, 1.0) * 100` — scaled from 1.0 to 4.0
- **Consistency score**: `(1.0 - std_dev_of_rolling_win_rate) * 100` — lower variance = higher score
- **Recency score**: `max(1.0 - days_since_last_trade / 14, 0) * 100` — decays over 14 days
- **Human probability score**: `(1.0 - bot_probability) * 100`

**Interpretation:**

| Score | Rating | Action |
|-------|--------|--------|
| 80-100 | Excellent | Strong copy-trade candidate |
| 60-79 | Good | Suitable with monitoring |
| 40-59 | Marginal | Proceed with caution, reduce allocation |
| 0-39 | Poor | Do not copy |

## Position Sizing for Copy Trades

Three approaches, from simplest to most nuanced:

### Fixed Amount
Use a constant SOL amount per copy trade (e.g., 0.5 SOL). Simple but ignores the wallet's conviction level.

### Proportional
Match the copied wallet's allocation as a percentage of their estimated portfolio:

```python
your_size = (their_trade_size / their_estimated_portfolio) * your_portfolio
```

Requires estimating their total portfolio, which can be imprecise.

### Confidence-Scaled
Base amount multiplied by your confidence in the wallet:

```python
your_size = base_amount * (copy_score / 100) * conviction_multiplier
```

Where `conviction_multiplier` is higher for wallets with longer track records.

## Anti-Patterns to Avoid

### Copying Bots
Bots have sub-second execution and often use MEV strategies. You cannot match their latency. By the time you detect their trade, the opportunity is gone or you become the exit liquidity. Use the bot probability score to filter these out.

### Survivorship Bias
A wallet with 1000% returns from one PumpFun token is not necessarily skilled. Look for wallets with consistent performance across many tokens, not outlier wins. The max-single-trade-PnL filter catches this.

### Blind Following
Never copy a trade without understanding what the token is. At minimum, run basic safety checks: liquidity depth, holder concentration, contract verification. A 2-second check can prevent buying a honeypot.

### No Independent Exits
The copied wallet may have information you do not have. They may exit for reasons unrelated to the trade. Always maintain your own stop loss. Never rely solely on mirroring their exit.

### Correlation Risk
If you copy 5 wallets and they all buy the same token, you have 5x the intended exposure. Track aggregate position across all copy sources and enforce portfolio-level limits.

### Ignoring Capacity
A wallet profiting on tokens with $50K daily volume cannot be copied at scale. If your trade is 10% of daily volume, you will move the price against yourself.

## Integration with Other Skills

| Skill | How It Integrates |
|-------|-------------------|
| `wallet-profiling` | Deep behavioral analysis of candidate wallets |
| `sybil-detection` | Verify wallet is not part of a wash-trading ring |
| `token-holder-analysis` | Safety check tokens before copying a buy |
| `liquidity-analysis` | Verify sufficient liquidity to enter/exit |
| `helius-api` | WebSocket monitoring and transaction parsing |
| `jupiter-api` / `jupiter-swap` | Trade execution via aggregator |
| `slippage-modeling` | Estimate execution cost of the copy trade |
| `position-sizing` | Portfolio-aware sizing for copy positions |
| `risk-management` | Portfolio-level risk controls |

## Files

### References
- `references/wallet_discovery.md` — Sources and methods for finding copy-trade candidates
- `references/execution_strategy.md` — Monitoring infrastructure and execution approaches
- `references/risk_framework.md` — Portfolio-level risk controls for copy trading

### Scripts
- `scripts/evaluate_wallet.py` — Comprehensive copy-trade suitability scoring for a wallet
- `scripts/monitor_wallet.py` — Real-time wallet transaction monitoring with trade alerts
