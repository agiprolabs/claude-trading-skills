# Crypto-Native Indicator Formulas

Formulas, parameters, and signal ranges for all nine crypto indicators.

## 1. NVT Ratio (Network Value to Transactions)

### Formula

```
NVT = Market Cap / Daily On-Chain Tx Volume (USD)
NVT Signal = SMA(NVT, period)
```

Analogous to P/E ratio: market cap is the "price", on-chain tx volume is
the "earnings". High NVT = overvalued relative to usage.

### Parameters

| Timeframe | SMA Period | Overbought | Oversold |
|-----------|-----------|------------|----------|
| Short-term | 14 days | > 65 | < 25 |
| Medium-term | 28 days | > 80 | < 20 |
| Long-term | 90 days | > 100 | < 15 |

### Signal Table

| NVT Range | Signal | Interpretation |
|-----------|--------|----------------|
| < 15 | Strong bullish | Extremely undervalued or high usage spike |
| 15–25 | Bullish | Healthy usage relative to valuation |
| 25–65 | Neutral | Fair value zone |
| 65–100 | Bearish | Overvalued relative to throughput |
| > 100 | Strong bearish | Speculative premium, correction likely |

### Data Sources

- **Market cap**: CoinGecko `/coins/{id}` → `market_data.market_cap.usd`
- **Tx volume**: Blockchain RPC (sum of transfer values), DeFiLlama

## 2. MVRV Ratio (Market Value to Realized Value)

### Formula

```
MVRV = Market Cap / Realized Cap
Realized Cap = Σ (tokens_in_UTXO_i × price_when_UTXO_i_last_moved)
```

For non-UTXO chains (Solana, Ethereum tokens):

```
Estimated Realized Cap = Σ (wallet_balance_i × average_entry_price_i)
```

### Parameters

| Asset Type | Overbought | Oversold |
|------------|-----------|----------|
| Bitcoin | > 3.5 | < 1.0 |
| Ethereum | > 3.0 | < 0.8 |
| Large-cap alts | > 2.5 | < 0.7 |
| Small-cap tokens | > 2.0 | < 0.5 |

### Signal Table

| MVRV | Signal | Interpretation |
|------|--------|----------------|
| < 0.5 | Strong bullish | Deep capitulation, most holders at loss |
| 0.5–1.0 | Bullish | Aggregate holders near breakeven |
| 1.0–2.0 | Neutral | Moderate unrealized profit |
| 2.0–3.5 | Bearish | Significant unrealized profit, distribution risk |
| > 3.5 | Strong bearish | Euphoria zone, historically precedes corrections |

### Data Sources

- **Bitcoin/Ethereum**: Glassnode, CryptoQuant (direct MVRV)
- **Solana tokens**: Estimate from Helius DAS holder data + DEX trade history


## 3. Exchange Flow

### Formula

```
Netflow = Deposits_to_exchanges (USD) - Withdrawals_from_exchanges (USD)
Netflow Ratio = Netflow / Market Cap
Netflow Z-Score = (Netflow - SMA(Netflow, 30)) / StdDev(Netflow, 30)
```

### Parameters

| Metric | Bearish Threshold | Bullish Threshold |
|--------|------------------|------------------|
| Netflow Ratio | > 0.01 (1% of mcap) | < -0.01 |
| Netflow Z-Score | > 2.0 | < -2.0 |

### Signal Table

| Netflow Z-Score | Signal | Interpretation |
|----------------|--------|----------------|
| < -2.0 | Strong bullish | Abnormal withdrawal (accumulation) |
| -2.0 to -0.5 | Bullish | Above-average withdrawal |
| -0.5 to 0.5 | Neutral | Normal flow |
| 0.5 to 2.0 | Bearish | Above-average deposits |
| > 2.0 | Strong bearish | Abnormal deposit spike (selling) |

### Data Sources

- **CEX flows**: CryptoQuant, Glassnode
- **Solana SPL tokens**: Track transfers to/from known exchange wallets via
  Helius `getAssetTransfers` or Solana RPC `getSignaturesForAddress`


## 4. Funding Rate Signal

### Formula

```
VW Funding Rate = Σ (rate_i × volume_i) / Σ volume_i
Funding Rate MA = SMA(VW_Funding_Rate, periods)
Cumulative Funding = Σ (funding_rate × 3)  [3 payments/day]
Annualized Funding = Cumulative Funding * 365
```

### Parameters

| Period | SMA Length | Extreme Threshold |
|--------|-----------|-------------------|
| Scalp (4h) | 3 periods | ±0.1% |
| Swing (1-7d) | 7 periods | ±0.05% |
| Position (1-4w) | 14 periods | ±0.03% |

### Signal Table

| VW Funding Rate | Signal | Interpretation |
|----------------|--------|----------------|
| < -0.1% | Strong bullish | Shorts massively overleveraged |
| -0.1% to -0.03% | Bullish | Moderate short bias |
| -0.03% to 0.03% | Neutral | Balanced market |
| 0.03% to 0.1% | Bearish | Moderate long bias |
| > 0.1% | Strong bearish | Longs massively overleveraged |

### Data Sources

- **Binance**: `GET /fapi/v1/fundingRate`
- **Bybit**: `GET /v5/market/funding/history`
- **dYdX**: `GET /v3/markets` → `nextFundingRate`


## 5. Open Interest Momentum

### Formula

```
OI Momentum (%) = (OI_t - OI_{t-n}) / OI_{t-n} × 100
OI-Price Divergence = sign(ΔPrice) ≠ sign(ΔOI)
```

### Parameters

| Lookback | Use Case |
|----------|----------|
| 1 day | Intraday sentiment shift |
| 3 days | Short-term positioning |
| 7 days | Swing trade signal |
| 14 days | Trend confirmation |

### Signal Matrix

| OI Trend | Price Trend | Signal | Meaning |
|----------|-------------|--------|---------|
| Rising | Rising | Trend confirmation | New longs entering |
| Rising | Falling | Bearish buildup | New shorts entering |
| Falling | Rising | Short squeeze | Shorts closing |
| Falling | Falling | Long liquidation | Longs capitulating |

### Data Sources

- **CoinGlass**: Aggregated OI across exchanges
- **Binance**: `GET /fapi/v1/openInterest`


## 6. Holder Momentum

### Formula

```
Holder Momentum = (Holders_t - Holders_{t-n}) / Holders_{t-n}
Holder Acceleration = Momentum_t - Momentum_{t-1}
Growth Rate (annualized) = ((Holders_t / Holders_{t-n})^(365/n) - 1) × 100
```

### Parameters

| Lookback | Signal Threshold |
|----------|-----------------|
| 7 days | ±3% momentum |
| 14 days | ±5% momentum |
| 30 days | ±10% momentum |

### Signal Table

| Momentum | Acceleration | Signal |
|----------|-------------|--------|
| Positive | Positive | Strong bullish — accelerating adoption |
| Positive | Negative | Weakening bullish — adoption slowing |
| Negative | Negative | Strong bearish — accelerating departures |
| Negative | Positive | Weakening bearish — departures slowing |

### Data Sources

- **Solana**: Helius DAS `getAssetsByGroup`, Birdeye holder stats
- **Ethereum**: Etherscan token holder count, Dune Analytics


## 7. Liquidity Score (Composite)

### Formula

```
Depth Score = min(1, bids_within_2pct / position_size)
Spread Score = max(0, 1 - spread_bps / 100)
Pool Score = min(1, pool_tvl / (position_size × 10))

Liquidity Score = 0.4 × Depth_Score + 0.3 × Spread_Score + 0.3 × Pool_Score
```

### Weight Recommendations

| Context | Depth Weight | Spread Weight | Pool Weight |
|---------|-------------|--------------|-------------|
| CEX-dominant token | 0.5 | 0.3 | 0.2 |
| DEX-only token | 0.2 | 0.2 | 0.6 |
| Hybrid | 0.4 | 0.3 | 0.3 |

### Signal Table

| Score | Rating | Action |
|-------|--------|--------|
| 0.8–1.0 | Excellent | Full position size acceptable |
| 0.5–0.8 | Good | Reduce position by 25% |
| 0.3–0.5 | Fair | Reduce position by 50%, use limit orders |
| < 0.3 | Poor | Avoid or use very small size with patience |


## 8. Smart Money Flow

### Formula

```
SMF = Σ smart_buys (USD) - Σ smart_sells (USD)
SMF Ratio = SMF / Total Volume (USD)
SMF Z-Score = (SMF - SMA(SMF, 14)) / StdDev(SMF, 14)
```

Smart wallet = meets 2+ of: win rate >60% (50+ trades), avg ROI >20%,
portfolio >$500K, early entry in 3+ tokens that 5x+.

### Signal Table

| SMF Ratio | Signal | Interpretation |
|-----------|--------|----------------|
| < -0.15 | Strong bearish | Smart money actively distributing |
| -0.15 to -0.05 | Bearish | Smart money net selling |
| -0.05 to 0.05 | Neutral | No clear smart money conviction |
| 0.05 to 0.15 | Bullish | Smart money net buying |
| > 0.15 | Strong bullish | Smart money aggressively accumulating |

### Data Sources

- **Solana**: Helius parsed transactions + wallet profiling
- **Ethereum**: Nansen smart money labels
- **Cross-chain**: Arkham Intelligence


## 9. Token Velocity

### Formula

```
Token Velocity = Daily Volume (tokens) / Circulating Supply
Velocity MA = SMA(Velocity, 14)
Velocity Trend = Velocity / Velocity_MA
```

### Signal Table

| Velocity | Signal | Interpretation |
|----------|--------|----------------|
| < 0.02 | Very low | Strong holders, low speculation |
| 0.02–0.05 | Low | Healthy holding pattern |
| 0.05–0.15 | Moderate | Normal trading activity |
| 0.15–0.30 | High | Elevated speculation |
| > 0.30 | Very high | Frenzied trading, dump risk |

### Data Sources

- **Volume**: CoinGecko `/coins/{id}` → `market_data.total_volume`
- **Supply**: CoinGecko → `market_data.circulating_supply`
- **DEX volume**: DeFiLlama `/overview/dexs` or Jupiter aggregator stats
