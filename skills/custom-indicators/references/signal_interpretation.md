# Signal Interpretation Guide

How to combine multiple crypto-native indicators into actionable composite
scores, detect divergences, and filter false signals.

---

## Building Composite Scores

### Weighted Scoring Framework

Assign each indicator a score from -2 (strong bearish) to +2 (strong bullish),
then compute a weighted average.

```python
WEIGHTS = {
    "nvt": 0.10,
    "mvrv": 0.10,
    "exchange_flow": 0.15,
    "funding_rate": 0.15,
    "oi_momentum": 0.10,
    "holder_momentum": 0.10,
    "liquidity_score": 0.05,
    "smart_money_flow": 0.15,
    "token_velocity": 0.10,
}

def composite_score(signals: dict[str, int]) -> float:
    """Compute weighted composite score.

    Args:
        signals: Indicator name to score (-2 to +2).

    Returns:
        Weighted score from -2.0 to +2.0.
    """
    total = 0.0
    weight_sum = 0.0
    for name, score in signals.items():
        w = WEIGHTS.get(name, 0.1)
        total += score * w
        weight_sum += w
    return total / weight_sum if weight_sum > 0 else 0.0
```

### Composite Score Interpretation

| Score Range | Label | Suggested Bias |
|------------|-------|----------------|
| 1.5 to 2.0 | Strong bullish | Consider adding to position |
| 0.5 to 1.5 | Bullish | Favor long bias |
| -0.5 to 0.5 | Neutral | No directional edge |
| -1.5 to -0.5 | Bearish | Favor reducing exposure |
| -2.0 to -1.5 | Strong bearish | Consider defensive positioning |

### Weight Adjustments by Market Regime

- **Trending market**: Increase weight on OI momentum and funding rate
  (momentum indicators confirm trends).
- **Range-bound market**: Increase weight on exchange flow and smart money
  flow (accumulation/distribution drives breakouts).
- **High-volatility regime**: Increase weight on liquidity score (exit
  difficulty rises) and funding rate (leverage extremes cause squeezes).
- **Low-liquidity regime**: Increase weight on holder momentum and token
  velocity (supply-side dynamics dominate).

---

## Divergence Detection

Divergences between price action and on-chain/derivatives indicators often
signal reversals or trend exhaustion.

### Key Divergence Patterns

| Price | Indicator | Divergence Type | Meaning |
|-------|-----------|-----------------|---------|
| Rising | NVT expanding | Bearish | Price rising but tx volume not keeping up |
| Rising | MVRV > 3.0 | Bearish | Holders in deep profit, distribution risk |
| Rising | Exchange deposits spiking | Bearish | Holders sending to exchanges to sell |
| Rising | Funding rate very positive | Bearish | Overleveraged longs, squeeze risk |
| Rising | Holder count falling | Bearish | Price up but adoption declining |
| Rising | Smart money selling | Bearish | Informed wallets distributing |
| Falling | NVT contracting | Bullish | Tx volume growing despite price drop |
| Falling | MVRV < 1.0 | Bullish | Holders underwater, capitulation near end |
| Falling | Exchange withdrawals spiking | Bullish | Accumulation despite price decline |
| Falling | Funding rate very negative | Bullish | Overleveraged shorts, squeeze risk |
| Falling | Holder count rising | Bullish | New buyers despite price weakness |
| Falling | Smart money buying | Bullish | Informed wallets accumulating |

### Divergence Confirmation

A divergence is more reliable when:
1. **Multiple indicators diverge** — 3+ indicators disagreeing with price
   is a stronger signal than a single divergence.
2. **Divergence persists** — A divergence lasting 3+ days is more
   meaningful than a single-day spike.
3. **Volume supports it** — High-volume divergences are more significant.

```python
def count_divergences(
    price_trend: str,
    indicator_signals: dict[str, str],
) -> tuple[int, int]:
    """Count bullish and bearish divergences.

    Args:
        price_trend: "up" or "down".
        indicator_signals: Name to "bullish"/"bearish"/"neutral".

    Returns:
        (bullish_divergence_count, bearish_divergence_count).
    """
    bull_div = 0
    bear_div = 0
    for signal in indicator_signals.values():
        if price_trend == "up" and signal == "bearish":
            bear_div += 1
        elif price_trend == "down" and signal == "bullish":
            bull_div += 1
    return bull_div, bear_div
```

---

## Regime-Dependent Interpretation

The same indicator value can mean different things depending on the market
regime.

### NVT in Different Regimes

- **Bull market**: NVT naturally runs higher because speculation inflates
  market cap. Use higher thresholds (overbought > 100 instead of > 65).
- **Bear market**: NVT compresses. Even NVT = 40 can be overbought.
- **Early cycle**: NVT may spike as price recovers before transaction volume
  catches up — not necessarily bearish.

### Funding Rate in Different Regimes

- **Strong trend**: Persistently positive funding in a bull trend is normal,
  not necessarily a reversal signal. Look for funding rate *acceleration*
  rather than absolute level.
- **Choppy market**: Funding rate extremes in range-bound markets are more
  reliable contrarian signals.

### Exchange Flow in Different Regimes

- **Post-crash**: Large exchange withdrawals after a major crash often mark
  capitulation bottoms — strongest bullish signal.
- **During rally**: Exchange deposits during a rally may just be profit
  taking, not a top signal, unless accompanied by other divergences.

---

## Common False Signals and Filters

### False Signal 1: NVT Spike from Low Volume

**Problem**: A single day of unusually low transaction volume can spike NVT
into "overvalued" territory.

**Filter**: Use NVT Signal (14-day SMA) instead of raw NVT. Require NVT
Signal to stay elevated for 3+ consecutive days.

### False Signal 2: Exchange Flow from Internal Transfers

**Problem**: Exchanges moving tokens between hot and cold wallets creates
false deposit/withdrawal signals.

**Filter**: Exclude transfers between known wallets belonging to the same
exchange. Use labeled wallet databases from Arkham or Nansen.

### False Signal 3: Funding Rate After Liquidation Cascade

**Problem**: A liquidation cascade can briefly push funding to an extreme,
then it immediately normalizes.

**Filter**: Ignore funding rate extremes that last less than 2 funding
periods (16 hours). Require persistence.

### False Signal 4: Holder Count Gaming

**Problem**: Projects can inflate holder count by distributing tiny amounts
to thousands of wallets (dust attacks/airdrops).

**Filter**: Only count holders with balance above a minimum threshold
(e.g., > $10 worth of tokens). Monitor *median* balance, not just count.

### False Signal 5: Smart Money Misclassification

**Problem**: A wallet may look "smart" from past luck but is actually random.

**Filter**: Require a minimum sample size (50+ trades) for smart money
classification. Re-evaluate classification quarterly. Weight recent
performance more heavily.

---

## Integration with Standard TA

Crypto indicators work best when combined with standard technical analysis.

### Confirmation Framework

| Crypto Indicator | Pair With (Standard TA) | Confirmation Logic |
|-----------------|------------------------|-------------------|
| NVT bearish | RSI overbought (> 70) | Double confirmation of overextension |
| Exchange outflow bullish | Price at support level | Accumulation at key level |
| Funding rate extreme | Bollinger Band touch | Mean reversion setup |
| Holder momentum bullish | Volume breakout | Adoption + price confirmation |
| Smart money buying | MACD bullish cross | Informed money + momentum alignment |

### Priority Rules

When crypto indicators and standard TA conflict:
1. **In trending markets**: Favor standard TA (trend indicators).
2. **At extremes**: Favor crypto indicators (on-chain data captures
   positioning that TA cannot see).
3. **At major support/resistance**: Weigh both equally — confluence of
   on-chain accumulation at a technical level is a high-probability setup.

---

## Disclaimer

All signal interpretation guidance is for informational purposes only and
does not constitute financial advice. Indicator signals can and do fail.
Always use proper risk management regardless of signal strength.
