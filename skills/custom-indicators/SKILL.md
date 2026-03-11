---
name: custom-indicators
description: Crypto-native indicators including NVT ratio, exchange flow, funding rate signals, holder momentum, and smart money flow
---

# Custom Crypto Indicators

## Why Standard TA Falls Short for Crypto

Traditional technical analysis was built for equities and forex — markets with
fixed supply, regulated exchanges, and institutional-dominated order flow.
Crypto markets have unique properties that demand purpose-built indicators:

- **On-chain transparency**: Every transaction is public. We can measure real
  economic activity, not just price and volume on a single exchange.
- **Supply mechanics**: Fixed or programmatic supply schedules make
  supply-side analysis (velocity, holder distribution) meaningful.
- **Derivatives dominance**: Perpetual futures funding rates and open interest
  often drive spot price, not the other way around.
- **Whale concentration**: A small number of wallets hold outsized supply.
  Tracking their behavior provides alpha that equity-market TA cannot.
- **Exchange flows**: On-chain deposit/withdrawal to centralized exchanges
  signals intent to sell or accumulate.

This skill covers nine crypto-native indicators. Each section includes the
formula, interpretation guide, data sources, and a working code snippet.

## Files

| File | Description |
|------|-------------|
| `references/indicator_formulas.md` | Full formulas, parameter tables, signal ranges for all 9 indicators |
| `references/signal_interpretation.md` | Composite scoring, divergence detection, false signal filtering |
| `scripts/compute_crypto_indicators.py` | Computes all 9 indicators from free APIs or demo data |
| `scripts/holder_momentum.py` | Holder count tracking with momentum signals |

---

## Indicator 1: NVT Ratio

**Network Value to Transactions** — the crypto equivalent of a P/E ratio.

```
NVT = Market Cap / Daily On-Chain Transaction Volume (USD)
```

- **High NVT (> 65)**: Network is overvalued relative to its economic
  throughput. Bearish signal.
- **Low NVT (< 25)**: Network is undervalued or seeing heavy real usage.
  Bullish signal.
- **Data sources**: CoinGecko (market cap), blockchain explorers or
  DeFiLlama (transaction volume).

```python
def nvt_ratio(market_cap: float, daily_tx_volume_usd: float) -> float:
    """Compute NVT ratio.

    Args:
        market_cap: Current market capitalization in USD.
        daily_tx_volume_usd: 24h on-chain transaction volume in USD.

    Returns:
        NVT ratio value.
    """
    if daily_tx_volume_usd <= 0:
        return float("inf")
    return market_cap / daily_tx_volume_usd
```

**Smoothing**: Apply a 14-day or 28-day moving average to NVT (called
NVT Signal) to reduce noise from daily volume spikes.

---

## Indicator 2: MVRV Ratio

**Market Value to Realized Value** — compares the current market cap to the
aggregate cost basis of all holders.

```
MVRV = Market Cap / Realized Cap
Realized Cap = Sum of (each UTXO * price when it last moved)
```

- **MVRV > 3.5**: Most holders are in deep profit. Distribution likely.
- **MVRV < 1.0**: Most holders are underwater. Historically marks bottoms.
- **Data sources**: Glassnode, CryptoQuant (Bitcoin/Ethereum). For Solana
  tokens, approximate via average entry price of top holders.

```python
def mvrv_ratio(market_cap: float, realized_cap: float) -> float:
    """Compute MVRV ratio.

    Args:
        market_cap: Current market capitalization in USD.
        realized_cap: Realized capitalization (aggregate cost basis).

    Returns:
        MVRV ratio value.
    """
    if realized_cap <= 0:
        return float("inf")
    return market_cap / realized_cap
```

For tokens without UTXO-based realized cap, estimate using average purchase
price from DEX trade history multiplied by circulating supply.

---

## Indicator 3: Exchange Flow

**Net exchange deposits minus withdrawals** — signals selling or accumulation
intent.

```
Exchange Netflow = Deposits to Exchanges - Withdrawals from Exchanges
```

- **Positive netflow (large deposits)**: Holders moving tokens to exchanges,
  likely to sell. Bearish.
- **Negative netflow (withdrawals)**: Tokens leaving exchanges to cold
  storage. Bullish accumulation signal.
- **Data sources**: CryptoQuant, Glassnode. For Solana SPL tokens, track
  transfers to known exchange wallets via Helius or Solana RPC.

```python
def exchange_netflow(
    deposits_usd: float, withdrawals_usd: float
) -> tuple[float, str]:
    """Compute exchange netflow and interpret.

    Returns:
        Tuple of (netflow_value, signal_label).
    """
    netflow = deposits_usd - withdrawals_usd
    if netflow > 0:
        signal = "bearish"
    elif netflow < 0:
        signal = "bullish"
    else:
        signal = "neutral"
    return netflow, signal
```

Normalize by market cap for cross-token comparison:
`Netflow Ratio = Netflow / Market Cap`.

---

## Indicator 4: Funding Rate Signal

Perpetual futures contracts use funding rates to anchor price to spot.

```
Funding Rate = (Perp Mark Price - Spot Price) / Spot Price
             (paid every 8 hours on most exchanges)
```

- **Highly positive (> 0.05%)**: Longs pay shorts. Market is overleveraged
  long. Contrarian bearish.
- **Highly negative (< -0.05%)**: Shorts pay longs. Overleveraged short.
  Contrarian bullish.
- **Data sources**: Binance, Bybit, dYdX APIs. Aggregate across exchanges
  for a volume-weighted average.

```python
def funding_rate_signal(
    rates: list[float], weights: list[float] | None = None
) -> tuple[float, str]:
    """Volume-weighted average funding rate with signal.

    Args:
        rates: Funding rates from multiple exchanges.
        weights: Optional volume weights per exchange.
    """
    import numpy as np

    if weights is None:
        weights = [1.0 / len(rates)] * len(rates)
    vw_rate = float(np.average(rates, weights=weights))
    if vw_rate > 0.0005:
        signal = "bearish"
    elif vw_rate < -0.0005:
        signal = "bullish"
    else:
        signal = "neutral"
    return vw_rate, signal
```

---

## Indicator 5: Open Interest Momentum

Tracks the rate of change in total open interest across derivatives exchanges.

```
OI Momentum = (OI_today - OI_n_days_ago) / OI_n_days_ago * 100
```

- **Rising OI + Rising Price**: New money entering longs. Trend
  confirmation.
- **Rising OI + Falling Price**: New shorts opening. Bearish pressure.
- **Falling OI + Rising Price**: Short squeeze / closing shorts.
- **Falling OI + Falling Price**: Long liquidation.
- **Data sources**: CoinGlass, Binance, Bybit open interest endpoints.

```python
def oi_momentum(
    oi_series: list[float], lookback: int = 7
) -> float:
    """Compute open interest momentum as percentage change.

    Args:
        oi_series: Daily open interest values (newest last).
        lookback: Number of days for momentum calculation.
    """
    if len(oi_series) < lookback + 1:
        return 0.0
    old = oi_series[-(lookback + 1)]
    new = oi_series[-1]
    if old <= 0:
        return 0.0
    return (new - old) / old * 100.0
```

---

## Indicator 6: Holder Momentum

Tracks the net change in unique token holders over time.

```
Holder Momentum = (Holders_today - Holders_n_days_ago) / Holders_n_days_ago
Holder Acceleration = Holder Momentum_today - Holder Momentum_yesterday
```

- **Accelerating growth**: Viral adoption phase. Bullish.
- **Decelerating growth**: Adoption slowing. Watch for reversal.
- **Negative momentum**: Holders leaving. Bearish.
- **Data sources**: Helius DAS API (Solana), Etherscan token holder count,
  Birdeye holder stats.

```python
def holder_momentum(
    holder_counts: list[int], lookback: int = 7
) -> tuple[float, float]:
    """Compute holder momentum and acceleration.

    Returns:
        Tuple of (momentum_pct, acceleration).
    """
    if len(holder_counts) < lookback + 2:
        return 0.0, 0.0
    old = holder_counts[-(lookback + 1)]
    new = holder_counts[-1]
    prev_old = holder_counts[-(lookback + 2)]
    prev_new = holder_counts[-2]
    mom = (new - old) / old if old > 0 else 0.0
    prev_mom = (prev_new - prev_old) / prev_old if prev_old > 0 else 0.0
    accel = mom - prev_mom
    return mom, accel
```

See `scripts/holder_momentum.py` for a full tracking implementation.

---

## Indicator 7: Liquidity Score

A composite metric combining order book depth, bid-ask spread, and DEX pool
depth to estimate how easily a position can be entered/exited.

```
Liquidity Score = w1 * Depth Score + w2 * Spread Score + w3 * Pool Score
```

Where:
- **Depth Score** = `min(1, total_bids_within_2pct / target_position_size)`
- **Spread Score** = `max(0, 1 - spread_bps / 100)`
- **Pool Score** = `min(1, pool_tvl / (target_position_size * 10))`
- Default weights: `w1=0.4, w2=0.3, w3=0.3`

```python
def liquidity_score(
    depth_usd: float,
    spread_bps: float,
    pool_tvl: float,
    position_size: float,
    weights: tuple[float, float, float] = (0.4, 0.3, 0.3),
) -> float:
    """Composite liquidity score from 0 (illiquid) to 1 (highly liquid)."""
    depth_s = min(1.0, depth_usd / position_size) if position_size > 0 else 0
    spread_s = max(0.0, 1.0 - spread_bps / 100.0)
    pool_s = min(1.0, pool_tvl / (position_size * 10)) if position_size > 0 else 0
    return weights[0] * depth_s + weights[1] * spread_s + weights[2] * pool_s
```

---

## Indicator 8: Smart Money Flow

Net buying pressure from wallets identified as "smart money" (historically
profitable, large balances, early entry patterns).

```
Smart Money Flow = Sum(smart_wallet_buys_usd) - Sum(smart_wallet_sells_usd)
SMF Ratio = Smart Money Flow / Total Volume
```

- **SMF Ratio > 0.1**: Smart money is net accumulating. Bullish.
- **SMF Ratio < -0.1**: Smart money is distributing. Bearish.
- **Data sources**: Helius transaction parsing + wallet labeling, Birdeye
  wallet analytics, Nansen (Ethereum).

```python
def smart_money_flow(
    smart_buys_usd: float,
    smart_sells_usd: float,
    total_volume_usd: float,
) -> tuple[float, float, str]:
    """Compute smart money flow and ratio.

    Returns:
        Tuple of (net_flow, smf_ratio, signal).
    """
    net = smart_buys_usd - smart_sells_usd
    ratio = net / total_volume_usd if total_volume_usd > 0 else 0.0
    if ratio > 0.1:
        signal = "bullish"
    elif ratio < -0.1:
        signal = "bearish"
    else:
        signal = "neutral"
    return net, ratio, signal
```

---

## Indicator 9: Token Velocity

Measures how frequently a token changes hands relative to its supply.

```
Token Velocity = Daily Trading Volume (tokens) / Circulating Supply
```

- **High velocity (> 0.3)**: Speculative trading dominates. Token is being
  flipped, not held. Can precede dumps.
- **Low velocity (< 0.05)**: Holders are sitting tight. Strong hands.
- **Data sources**: CoinGecko (volume, supply), DEX aggregator volumes.

```python
def token_velocity(
    daily_volume_tokens: float, circulating_supply: float
) -> tuple[float, str]:
    """Compute token velocity.

    Returns:
        Tuple of (velocity, interpretation).
    """
    if circulating_supply <= 0:
        return 0.0, "unknown"
    vel = daily_volume_tokens / circulating_supply
    if vel > 0.3:
        interp = "high_speculation"
    elif vel > 0.1:
        interp = "moderate"
    elif vel > 0.05:
        interp = "low"
    else:
        interp = "very_low_strong_holders"
    return vel, interp
```

---

## Combining Indicators

No single indicator is reliable in isolation. See
`references/signal_interpretation.md` for guidance on:

- Building composite scores from multiple indicators
- Detecting divergences (e.g., price rising but NVT expanding)
- Adjusting interpretation by market regime
- Filtering false signals

## Dependencies

```bash
uv pip install httpx pandas numpy
```

## Disclaimer

All indicators and analysis provided by this skill are for informational and
educational purposes only. They do not constitute financial advice. Always
conduct your own research before making any investment decisions.
