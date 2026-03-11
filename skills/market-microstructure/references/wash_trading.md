# Wash Trading Detection on Solana DEXes

## What Is Wash Trading?

Wash trading is the practice of simultaneously buying and selling the same asset to
create the illusion of market activity. On Solana DEXes, wash trading is common because:

- Transaction fees are very low (~$0.001 per swap)
- No KYC — anyone can create unlimited wallets
- Volume attracts attention on aggregator sites (DexScreener, Birdeye)
- High volume rankings drive organic trader interest

## Why Detection Matters

- **Inflated volume** makes tokens appear more liquid and popular than they are
- **False confidence** — traders size positions based on volume that is not real
- **Slippage risk** — real liquidity is much lower than volume suggests
- **Rug risk correlation** — tokens with heavy wash trading are more likely to rug

## Detection Methods

### Method 1: Self-Trading (Same Wallet)

The simplest form. A single wallet buys and sells within a short window.

**Detection:**
```python
def detect_self_trades(
    trades: list[dict], window_seconds: int = 300
) -> list[dict]:
    """Find wallets that buy and sell within a short time window."""
    from collections import defaultdict
    wallet_trades = defaultdict(list)
    for t in trades:
        wallet_trades[t["wallet"]].append(t)

    suspicious = []
    for wallet, wtrades in wallet_trades.items():
        buys = [t for t in wtrades if t["side"] == "buy"]
        sells = [t for t in wtrades if t["side"] == "sell"]
        for buy in buys:
            for sell in sells:
                if abs(buy["timestamp"] - sell["timestamp"]) < window_seconds:
                    suspicious.append({
                        "wallet": wallet,
                        "buy_time": buy["timestamp"],
                        "sell_time": sell["timestamp"],
                        "buy_amount": buy["volume_usd"],
                        "sell_amount": sell["volume_usd"],
                    })
    return suspicious
```

**Threshold:** If self-trading wallets account for > 20% of volume, flag as suspicious.

### Method 2: Cluster Trading (Funded-Together Wallets)

More sophisticated wash traders use multiple wallets funded from a common source.

**Detection approach:**
1. For each trading wallet, look up its funding history (first SOL transfer in)
2. Group wallets that received initial funding from the same parent
3. If a cluster of funded-together wallets accounts for high volume, flag it

This requires Helius or Solana RPC to trace funding. See the `helius-api` skill.

### Method 3: Uniform Trade Sizes

Bots often execute trades of identical or near-identical sizes.

**Detection:**
```python
def detect_uniform_sizes(
    trades: list[dict], tolerance: float = 0.02
) -> dict:
    """Detect suspiciously uniform trade sizes.

    Args:
        trades: List of trade records.
        tolerance: Maximum relative deviation to consider 'same size'.

    Returns:
        Dict with uniformity score and flagged groups.
    """
    from collections import Counter
    # Round to tolerance band
    rounded = []
    for t in trades:
        band = round(t["volume_usd"] / (t["volume_usd"] * tolerance + 1))
        rounded.append(band)

    counts = Counter(rounded)
    if not counts:
        return {"uniformity_score": 0, "max_cluster_pct": 0}

    max_cluster = max(counts.values())
    total = len(trades)
    return {
        "uniformity_score": max_cluster / total,
        "max_cluster_pct": max_cluster / total,
        "max_cluster_size": max_cluster,
        "total_trades": total,
    }
```

**Threshold:** If > 40% of trades fall in the same size band, flag as suspicious.

### Method 4: Low Unique Trader Ratio

Organic markets have many distinct participants. Wash traded tokens have few.

**Formula:**
```
unique_trader_ratio = unique_wallets / total_trade_count
```

| Ratio | Interpretation |
|-------|---------------|
| > 0.60 | Healthy — many unique participants |
| 0.30 – 0.60 | Normal — some repeat traders |
| 0.10 – 0.30 | Suspicious — few wallets generating many trades |
| < 0.10 | Almost certainly wash trading |

### Method 5: Volume/Liquidity Anomaly

Real volume is constrained by available liquidity. If daily volume far exceeds TVL,
much of it is likely wash traded.

**Formula:**
```
volume_tvl_ratio = daily_volume_usd / pool_tvl_usd
```

| Ratio | Interpretation |
|-------|---------------|
| < 2.0 | Normal — volume within liquidity capacity |
| 2.0 – 5.0 | Active but plausible |
| 5.0 – 20.0 | Suspicious — check other signals |
| > 20.0 | Very likely wash traded |

**Rationale:** For volume to be 20x TVL, the same liquidity must turn over 20 times
per day. While possible in high-frequency pools (SOL/USDC), it is implausible for
small-cap tokens.

## Composite Wash Trading Score

Combine detection signals into a 0–100 risk score:

```python
def wash_trading_score(
    unique_ratio: float,
    volume_tvl: float,
    uniformity: float,
    self_trade_pct: float,
) -> float:
    """Compute wash trading risk score (0 = clean, 100 = definitely wash).

    Args:
        unique_ratio: unique_wallets / trade_count (0 to 1).
        volume_tvl: daily_volume / pool_tvl.
        uniformity: max_cluster_pct from uniform size detection.
        self_trade_pct: Fraction of volume from self-trading wallets.
    """
    # Low unique ratio -> higher risk (weight: 30)
    ratio_score = max(0, (0.5 - unique_ratio) / 0.5) * 30

    # High volume/TVL -> higher risk (weight: 25)
    vtl_score = min(25, max(0, (volume_tvl - 2.0) / 18.0) * 25)

    # High uniformity -> higher risk (weight: 20)
    uniform_score = min(20, uniformity * 50)

    # Self-trading -> higher risk (weight: 25)
    self_score = min(25, self_trade_pct * 100)

    return min(100, ratio_score + vtl_score + uniform_score + self_score)
```

## Score Interpretation

| Score | Risk Level | Recommended Action |
|-------|-----------|-------------------|
| 0 – 20 | Low | Volume appears organic |
| 20 – 40 | Moderate | Some red flags — reduce position sizing |
| 40 – 60 | High | Significant wash trading likely — use caution |
| 60 – 80 | Very High | Most volume is likely fake — avoid or size tiny |
| 80 – 100 | Extreme | Almost certainly wash traded — do not rely on volume |

## Practical Adjustments

When wash trading is detected, adjust other metrics:

1. **Effective volume** = reported_volume * (1 - wash_score/100)
2. **Effective unique traders** = reported_traders * unique_ratio
3. **Adjusted velocity** = velocity * (1 - wash_score/100)

These adjusted metrics give a more realistic picture of genuine market activity.

## Limitations

- Cluster detection requires on-chain funding trace data (expensive)
- Sophisticated wash traders use randomized sizes and timing
- New legitimate tokens may trigger false positives due to low unique traders
- Volume/TVL ratio depends on accurate TVL data, which can lag
- Self-trading detection requires wallet-attributed trade data (not always available)

Always use multiple detection methods together. No single signal is definitive.
