# Strategy Types for Crypto Trading

Detailed guide to each strategy archetype with entry/exit logic, expected metrics, and parameter suggestions.

## Momentum / Trend Following

**Edge**: Price trends persist due to behavioral biases (herding, anchoring) and information diffusion lag. In crypto, low institutional participation amplifies trend persistence.

**Entry signals**:
- EMA(12) crosses above EMA(26) with ADX > 20
- SuperTrend flips bullish on primary timeframe
- Price breaks above N-period high with volume confirmation (> 1.5x average)
- MACD histogram turns positive after bearish-to-bullish crossover

**Exit signals**:
- Trailing stop: Chandelier exit at 3.0 × ATR(14) from highest high
- Signal reversal: EMA(12) crosses below EMA(26)
- Trend exhaustion: ADX peaks and turns down from above 40

**Expected metrics**:
- Win rate: 35-45%
- Avg win / avg loss: 2.0-4.0x
- Profit factor: 1.5-2.5
- Best Sharpe: 1.0-2.0 in trending regimes

**Parameter suggestions by timeframe**:

| Timeframe | Fast EMA | Slow EMA | ATR Period | ATR Multiplier |
|-----------|----------|----------|------------|----------------|
| 5m | 8 | 21 | 10 | 1.5 |
| 15m | 9 | 21 | 14 | 2.0 |
| 1H | 12 | 26 | 14 | 2.5 |
| 4H | 12 | 26 | 14 | 3.0 |
| 1D | 20 | 50 | 14 | 3.0 |

**Risk notes**: Trend following suffers in ranging markets. Use ADX > 20 or regime detection as a filter. Expect 5-8 consecutive losers during chop — size accordingly.

## Mean Reversion

**Edge**: Price oscillates around a fair value equilibrium. Overreactions (panic selling, FOMO buying) create temporary dislocations that correct. Works best for established tokens with consistent liquidity.

**Entry signals**:
- RSI(14) < 30 AND price above EMA(200) (oversold in uptrend)
- Price below lower Bollinger Band(20, 2.0) with band width > 0.05
- Z-score of price relative to 20-period mean < -2.0
- Price deviates > 2% below VWAP with increasing volume

**Exit signals**:
- Return to mean: price crosses back above EMA(20) or VWAP
- RSI(14) > 50 (neutral zone)
- Bollinger Band midline touch
- Time stop: 10-20 bars if no mean reversion occurs

**Expected metrics**:
- Win rate: 55-65%
- Avg win / avg loss: 0.8-1.5x
- Profit factor: 1.3-2.0
- Best Sharpe: 1.0-1.5 in ranging regimes

**Parameter suggestions by timeframe**:

| Timeframe | RSI Period | BB Period | BB Std | Z-Score Lookback |
|-----------|-----------|-----------|--------|-----------------|
| 5m | 10 | 15 | 2.0 | 20 |
| 15m | 14 | 20 | 2.0 | 30 |
| 1H | 14 | 20 | 2.0 | 30 |
| 4H | 14 | 20 | 2.5 | 40 |
| 1D | 14 | 20 | 2.5 | 50 |

**Risk notes**: Mean reversion fails catastrophically in trending markets. A "cheap" token can get much cheaper. Always use a hard stop loss. Never mean-revert tokens with broken fundamentals.

## Breakout

**Edge**: Periods of low volatility (consolidation) build potential energy that resolves in directional moves. Volume confirmation distinguishes real breakouts from fakeouts.

**Entry signals**:
- Bollinger Band width contracts to lowest 20% of 100-period range, then expands
- Price breaks above/below Donchian channel (20-period high/low)
- Volume spike > 2.5x 20-period average on breakout bar
- Range contraction (inside bars or narrowing ATR) followed by expansion

**Exit signals**:
- ATR trailing stop: 2.5 × ATR(14) from entry direction
- Time stop: close if no follow-through within 5-10 bars
- Failed breakout: price returns inside prior range within 3 bars

**Expected metrics**:
- Win rate: 30-40%
- Avg win / avg loss: 3.0-5.0x
- Profit factor: 1.5-2.5
- Many false breakouts — accept low win rate for large winners

**Risk notes**: False breakouts are common (50-60% of breakout signals fail). Volume confirmation is critical. Avoid breakout strategies on low-liquidity tokens where a single large order can fake a breakout.

## Copy Trading / Wallet Following

**Edge**: Skilled wallets (early token discoverers, profitable traders) have informational or analytical advantages. Following their trades captures some of their edge.

**Entry signals**:
- Tracked wallet buys token matching your criteria
- Wallet has historical PnL > 50% over 30 days
- Wallet has > 60% win rate on similar tokens
- Multiple tracked wallets buy same token within short window (consensus signal)

**Exit signals**:
- Tracked wallet sells (follow their exit)
- Independent stop loss (do not rely solely on wallet exit)
- Time stop: wallet has not exited after N hours
- Your own technical stop loss triggers

**Implementation considerations**:
- Monitor wallets via Helius webhooks or polling (see `helius-api` skill)
- Latency matters: detect and execute within seconds of wallet transaction
- Wallet quality degrades over time — continuously re-evaluate tracked wallets
- Filter by wallet style: sniper, swing trader, accumulator

**Risk notes**: Wallet following has significant latency risk — by the time you buy, the price may have moved. Smart wallets may front-run followers. Diversify across multiple wallets. Re-evaluate wallet quality monthly.

## PumpFun Strategies

**Edge**: PumpFun token lifecycle creates predictable price dynamics at known milestones.

### Sniper Strategy
- **Entry**: Buy within first 10 transactions of token creation
- **Exit**: Sell within 1-5 minutes (quick flip)
- **Win rate**: 20-30% (most new tokens fail immediately)
- **Risk**: Extremely high. Most tokens go to zero. Size very small.
- **Key metric**: The 20-30% of winners must return 5-10x to compensate

### Volume Confirmation Strategy
- **Entry**: Buy after token shows sustained buying volume for 5+ minutes
- **Exit**: Sell on first volume decline or reversal signal
- **Win rate**: 35-45%
- **Risk**: Lower than sniping but still high. Volume can evaporate instantly.

### Graduation Play
- **Entry**: Buy when bonding curve approaches 85 SOL (near graduation threshold)
- **Exit**: Sell during post-graduation pump on Raydium
- **Win rate**: 50-65% (tokens that reach 85 SOL often graduate)
- **Risk**: If graduation fails or dumps immediately post-graduation

**Risk notes**: PumpFun strategies involve extremely high-risk tokens. Never allocate more than 1-2% of portfolio to any single PumpFun trade. Most tokens go to zero.

## Arbitrage

**Edge**: Price discrepancies across DEXs or between spot and perpetual markets.

**Types**:
- **DEX-to-DEX**: Same token priced differently on Raydium vs Orca
- **CEX-DEX**: Price difference between centralized and decentralized exchanges
- **Funding rate**: Long spot, short perp when funding is positive (or vice versa)
- **Triangle**: A→B→C→A across three token pairs

**Entry**: Price discrepancy exceeds transaction costs + slippage + margin of safety

**Exit**: Both legs of the trade execute or unwind immediately

**Expected metrics**:
- Win rate: > 80% (if costs are modeled correctly)
- Avg profit per trade: 0.1-1.0% (thin margins, high frequency)
- Profit factor: > 3.0
- Risk: execution risk (one leg fills, other does not)

**Risk notes**: Arbitrage requires speed (sub-second execution), accurate cost modeling, and capital efficiency. MEV bots compete for the same opportunities. See `mev-analysis` skill.

## Market Making

**Edge**: Capturing bid-ask spread while managing inventory risk. Profitable when spread exceeds adverse selection cost.

**Entry**: Place limit orders on both sides of the market (bid and ask)

**Exit**: Opposing order fills, or inventory limit reached

**Parameters**:
- Spread width: function of volatility and inventory
- Order size: small relative to book depth
- Inventory limits: maximum long/short exposure
- Rebalancing: frequency of quote updates

**Expected metrics**:
- Win rate: > 60%
- Profit per trade: very small (captured spread)
- Volume: high (many trades per day)
- Risk: inventory risk during sharp moves

**Risk notes**: Market making on Solana DEXs is complex due to AMM mechanics. Traditional limit-order market making is mainly on CLOBs (e.g., Phoenix, OpenBook). LP provision on AMMs is a form of passive market making. See `lp-math` and `impermanent-loss` skills.

## Choosing the Right Strategy Type

| Factor | Best Strategy Type |
|--------|--------------------|
| Trending market | Momentum / Trend Following |
| Ranging market | Mean Reversion |
| Low volatility transitioning to high | Breakout |
| Access to skilled wallet data | Copy Trading |
| High retail activity on PumpFun | PumpFun Strategies |
| Multi-venue infrastructure | Arbitrage |
| High capital, low-vol stable pairs | Market Making |
