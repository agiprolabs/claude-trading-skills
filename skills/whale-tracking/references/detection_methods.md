# Whale Detection Methods

Algorithms and heuristics for identifying whale wallets, classifying their behavior as accumulation or distribution, and generating scored alerts.

## Whale Classification

### By Trade Size

Classify individual transactions by SOL value:

```python
def classify_trade_size(sol_amount: float) -> str:
    """Classify a single trade by size."""
    if sol_amount >= 1000:
        return "mega_whale"
    elif sol_amount >= 100:
        return "whale"
    elif sol_amount >= 10:
        return "mid_size"
    else:
        return "retail"
```

### By Portfolio Value

Classify wallets by total holdings:

```python
def classify_wallet(total_sol_value: float) -> str:
    """Classify a wallet by total portfolio value in SOL."""
    if total_sol_value >= 10_000:
        return "mega_whale"
    elif total_sol_value >= 1_000:
        return "whale"
    elif total_sol_value >= 100:
        return "mid_size"
    else:
        return "retail"
```

### By Token-Relative Holdings

For a specific token, classify by percentage of supply held:

| % of Supply | Classification | Risk Level |
|-------------|---------------|------------|
| > 10% | Dominant whale | Critical |
| 5-10% | Major whale | High |
| 2-5% | Significant holder | Medium |
| 1-2% | Notable holder | Low |
| < 1% | Minor holder | Minimal |

### By Influence Score

Combine multiple factors into an influence score:

```python
def compute_influence_score(
    pct_supply: float,
    trade_count_30d: int,
    avg_trade_sol: float,
    win_rate: float,
    follower_count: int,
) -> float:
    """Compute a 0-100 influence score for a whale wallet.

    Args:
        pct_supply: Percentage of token supply held (0-100).
        trade_count_30d: Number of trades in the last 30 days.
        avg_trade_sol: Average trade size in SOL.
        win_rate: Historical win rate (0-1).
        follower_count: Number of wallets that copy this wallet.

    Returns:
        Influence score from 0 to 100.
    """
    supply_score = min(pct_supply * 5, 30)       # Max 30 points
    activity_score = min(trade_count_30d * 0.5, 20)  # Max 20 points
    size_score = min(avg_trade_sol / 50, 20)     # Max 20 points
    skill_score = win_rate * 15                   # Max 15 points
    social_score = min(follower_count * 0.5, 15)  # Max 15 points
    return round(supply_score + activity_score + size_score + skill_score + social_score, 1)
```

## Accumulation Detection

### DCA Pattern Detection

Detect Dollar-Cost Averaging by looking for regular, similarly-sized buys:

```python
import statistics

def detect_dca_pattern(
    buy_timestamps: list[float],
    buy_amounts: list[float],
    min_buys: int = 4,
    max_cv: float = 0.5,
) -> bool:
    """Detect DCA buying pattern.

    Args:
        buy_timestamps: Unix timestamps of buy transactions.
        buy_amounts: SOL amounts of each buy.
        min_buys: Minimum number of buys to consider.
        max_cv: Maximum coefficient of variation for amounts.

    Returns:
        True if DCA pattern detected.
    """
    if len(buy_timestamps) < min_buys:
        return False

    # Check amount consistency (low coefficient of variation)
    mean_amt = statistics.mean(buy_amounts)
    if mean_amt == 0:
        return False
    cv = statistics.stdev(buy_amounts) / mean_amt
    if cv > max_cv:
        return False

    # Check time regularity (intervals should be somewhat consistent)
    intervals = [
        buy_timestamps[i + 1] - buy_timestamps[i]
        for i in range(len(buy_timestamps) - 1)
    ]
    mean_interval = statistics.mean(intervals)
    if mean_interval == 0:
        return False
    interval_cv = statistics.stdev(intervals) / mean_interval
    return interval_cv < 1.0  # Intervals within 1 CV
```

### Dip Buying Detection

Calculate what fraction of buys occurred during price dips (drawdown > 10% from rolling high). Compare buy timestamps against price history, compute rolling high at each buy point, and check if price was in drawdown. A dip_buy_ratio > 0.5 is a strong accumulation signal.

### Composite Accumulation Score

```python
def compute_accumulation_score(
    buy_count: int,
    sell_count: int,
    avg_buy_size: float,
    avg_sell_size: float,
    position_change_7d_pct: float,
    dip_buy_ratio: float,
    is_dca: bool,
) -> int:
    """Compute accumulation score from 0 to 10.

    Score >= 4 indicates likely accumulation.
    Score >= 7 indicates strong accumulation.
    """
    score = 0
    if buy_count > sell_count * 2:
        score += 2
    elif buy_count > sell_count:
        score += 1
    if avg_buy_size > avg_sell_size * 1.5:
        score += 1
    if position_change_7d_pct > 10:
        score += 2
    elif position_change_7d_pct > 0:
        score += 1
    if dip_buy_ratio > 0.5:
        score += 2
    elif dip_buy_ratio > 0.25:
        score += 1
    if is_dca:
        score += 2
    return min(score, 10)
```

## Distribution Detection

### Exchange Transfer Detection

Known Solana exchange deposit addresses (partial list):

| Exchange | Hot Wallet Prefix | Notes |
|----------|------------------|-------|
| Binance | 5tzFkiKsc... | Multiple deposit addresses |
| OKX | JCnc... | Rotates addresses |
| Bybit | AC5R... | Rotates addresses |

Detection approach:
1. Maintain a list of known exchange wallet addresses
2. Flag any SPL token transfers to these addresses
3. Weight: transfer to exchange = strong distribution signal (+3 to distribution score)

### Sell Frequency Analysis

```python
def detect_increasing_sell_frequency(
    sell_timestamps: list[float],
    window_days: int = 7,
) -> bool:
    """Detect whether sell frequency is increasing over time.

    Compares sell count in the most recent window to the prior window.
    """
    if len(sell_timestamps) < 4:
        return False

    now = sell_timestamps[-1]
    window_seconds = window_days * 86400
    recent_cutoff = now - window_seconds
    prior_cutoff = now - (2 * window_seconds)

    recent_sells = sum(1 for t in sell_timestamps if t >= recent_cutoff)
    prior_sells = sum(1 for t in sell_timestamps if prior_cutoff <= t < recent_cutoff)

    return recent_sells > prior_sells * 1.5
```

### Composite Distribution Score

```python
def compute_distribution_score(
    buy_count: int,
    sell_count: int,
    position_change_7d_pct: float,
    transfers_to_exchanges: int,
    sell_frequency_increasing: bool,
    position_pct_remaining: float,
) -> int:
    """Compute distribution score from 0 to 10.

    Score >= 4 indicates likely distribution.
    Score >= 7 indicates aggressive distribution.
    """
    score = 0
    if sell_count > buy_count * 2:
        score += 2
    elif sell_count > buy_count:
        score += 1
    if position_change_7d_pct < -20:
        score += 2
    elif position_change_7d_pct < 0:
        score += 1
    if transfers_to_exchanges > 0:
        score += 3
    if sell_frequency_increasing:
        score += 2
    if position_pct_remaining < 50:
        score += 1
    return min(score, 10)
```

## Alert Thresholds

### Transaction-Level Alerts

| Alert Level | Trigger | Action |
|-------------|---------|--------|
| Info | Tracked whale any trade | Log activity |
| Warning | Whale trade > 100 SOL | Notify if subscribed |
| Critical | Whale sells > 25% of position | Immediate alert |
| Emergency | Multiple whales selling same token | Flash alert |

### Scoring Alert Priority

Score by summing points: trade size (1-3 pts), whale influence (2-3 pts), concurrent whale count (0-3 pts), sell bonus (+1). Map total to priority: 8+ = critical, 5+ = high, 3+ = medium, else low.

## Multi-Wallet Detection

Whales often split holdings across wallets. Detect linked wallets by:

1. **Funding source**: Wallets funded from the same parent wallet
2. **Timing correlation**: Wallets that trade the same tokens at similar times
3. **Consolidation events**: Multiple wallets sending tokens to a single address

When linked wallets are detected, treat their combined holdings as a single whale entity for accumulation/distribution scoring.
