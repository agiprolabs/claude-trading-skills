---
name: position-sizing
description: Trade sizing methods including fixed fractional, volatility-adjusted, Kelly criterion, and liquidity-constrained sizing
---

# Position Sizing

Position sizing is the single most important risk management decision in trading. Your entry signal determines direction; your position size determines survival. A mediocre strategy with proper sizing will outperform a great strategy with reckless sizing over any meaningful time horizon.

**Core principle**: Size determines survival, not entries. Two traders with the same signals but different sizing will have wildly different outcomes. The one who sizes conservatively survives drawdowns and compounds capital; the one who oversizes blows up.

## Methods Covered

| Method | Best For | Key Input |
|--------|----------|-----------|
| Fixed Fractional | General trading, most recommended | Account risk % |
| Volatility-Adjusted | Volatile markets, multi-asset | ATR or realized vol |
| Kelly Criterion | Quantified edge with track record | Win rate + payoff ratio |
| Liquidity-Constrained | Low-liquidity Solana tokens | Pool depth |
| Anti-Martingale | Trend-following strategies | Recent P&L streak |

---

## 1. Fixed Fractional Sizing

The most recommended method for most traders. Risk a fixed percentage of your account on each trade.

### Formula

```
risk_amount = account_value * risk_percentage
price_risk_per_unit = entry_price - stop_loss_price
position_size_units = risk_amount / price_risk_per_unit
position_value = position_size_units * entry_price
```

### Risk Tiers

| Tier | Risk Per Trade | Use Case |
|------|---------------|----------|
| Conservative | 0.5–1% | New strategies, drawdown recovery |
| Standard | 1–2% | Most traders, proven strategies |
| Aggressive | 3–5% | High-conviction setups with strong, measured edge |

### Example

```python
account = 10_000  # $10,000 or 100 SOL
risk_pct = 0.02   # 2%
entry = 1.50
stop_loss = 1.30

risk_amount = account * risk_pct          # $200
price_risk = entry - stop_loss            # $0.20
position_units = risk_amount / price_risk # 1,000 tokens
position_value = position_units * entry   # $1,500
```

With this sizing, if the stop loss is hit, you lose exactly 2% of your account regardless of the token's price or volatility.

---

## 2. Volatility-Adjusted Sizing

Scale position size inversely with volatility. When volatility is high, take smaller positions; when low, take larger positions. This normalizes the dollar risk across different market conditions.

### Formula

```
adjusted_size = base_size * (target_vol / current_vol)
```

Where:
- `target_vol`: your desired daily portfolio volatility (e.g., 2%)
- `current_vol`: the token's current daily volatility (from ATR or realized vol)

### Using ATR

```python
atr_14 = 0.12          # 14-period ATR
close_price = 1.50
daily_vol_pct = atr_14 / close_price  # 8%

target_daily_vol = account * 0.02      # $200 target daily move
position_size = target_daily_vol / atr_14  # 1,667 units
```

This automatically reduces exposure in volatile markets and increases it in calm ones.

---

## 3. Kelly Criterion

The mathematically optimal fraction of capital to risk, maximizing long-term growth rate. Derived from maximizing expected logarithmic utility.

### Formula

```
f* = (p * b - q) / b
```

Where:
- `p` = win rate (probability of winning trade)
- `q` = 1 - p (probability of losing trade)
- `b` = average win / average loss (payoff ratio)
- `f*` = optimal fraction of capital to risk

Equivalent form: `f* = (p * (b + 1) - 1) / b`

### Critical Rule: NEVER Use Full Kelly

Full Kelly assumes perfect knowledge of your edge. In practice, edge estimates are noisy. Always use fractional Kelly:

| Fraction | Use Case | Notes |
|----------|----------|-------|
| 0.25x Kelly | Conservative, recommended default | Robust to edge estimation error |
| 0.50x Kelly | Moderate, for well-measured edges | Still significant drawdown risk |
| 1.0x Kelly | Never in practice | Theoretical maximum, catastrophic if edge is overestimated |

### Example

```python
win_rate = 0.55       # 55% win rate
avg_win = 2.0         # Average win is 2x the average loss
avg_loss = 1.0
payoff_ratio = avg_win / avg_loss  # b = 2.0

kelly = (win_rate * payoff_ratio - (1 - win_rate)) / payoff_ratio
# kelly = (0.55 * 2.0 - 0.45) / 2.0 = 0.325 = 32.5%

quarter_kelly = kelly * 0.25  # 8.1% — use this
half_kelly = kelly * 0.50     # 16.25%
```

**If Kelly is negative, you have no edge. Do not trade.**

See `references/sizing_formulas.md` for the full mathematical derivation.

---

## 4. Liquidity-Constrained Sizing

Critical for Solana tokens. Even if your risk model says you can take a large position, the pool may not support it without unacceptable slippage.

### Formula (Constant-Product AMM)

```
slippage ≈ trade_size / pool_liquidity
max_trade = pool_liquidity * max_slippage_pct
```

### Rules of Thumb

| Constraint | Guideline |
|-----------|-----------|
| Max single trade | 2% of pool liquidity |
| Max position | 5% of pool liquidity |
| Minimum pool depth | 10x your desired position size |

### Example

```python
pool_sol = 500          # 500 SOL in pool
max_slippage = 0.02     # 2% max slippage

max_trade_sol = pool_sol * max_slippage  # 10 SOL
# For a $150 SOL price, that's $1,500 max per trade
```

**Always check all pools**, not just the largest. Aggregate liquidity across Raydium, Orca, and Meteora for the full picture. See the `liquidity-analysis` skill for pool depth assessment.

---

## 5. Anti-Martingale Sizing

Increase size after wins, decrease after losses. This is the opposite of the gambler's fallacy (Martingale). The logic: winning streaks may indicate your strategy is in sync with the market; losing streaks may indicate regime change.

### Implementation

```python
def anti_martingale_size(
    base_size: float,
    consecutive_wins: int,
    consecutive_losses: int,
    scale_factor: float = 0.25,
    max_multiplier: float = 2.0,
    min_multiplier: float = 0.5,
) -> float:
    if consecutive_losses > 0:
        multiplier = max(min_multiplier, 1.0 - consecutive_losses * scale_factor)
    elif consecutive_wins > 0:
        multiplier = min(max_multiplier, 1.0 + consecutive_wins * scale_factor)
    else:
        multiplier = 1.0
    return base_size * multiplier
```

Use conservatively. After 3+ consecutive losses, reducing size by 50% protects capital during drawdowns.

---

## Position Sizing Ladder

Combine all methods and take the most conservative result:

```
1. Calculate Kelly size          → theoretical max based on edge
2. Calculate fixed fractional    → risk-based size
3. Calculate volatility-adjusted → vol-normalized size
4. Calculate liquidity-constrained max → market-based ceiling
5. Final size = min(all four)    → binding constraint wins
```

The binding constraint tells you what is limiting your size:
- **Kelly-bound**: your edge is small, size accordingly
- **Risk-bound**: standard risk management is the limit
- **Volatility-bound**: market is too volatile for larger size
- **Liquidity-bound**: pool cannot absorb more without slippage

---

## Account-Level Limits

Individual position sizing is necessary but not sufficient. You also need portfolio-level constraints:

| Limit | Guideline | Rationale |
|-------|-----------|-----------|
| Max single position | 10% of portfolio | Diversification floor |
| Max correlated exposure | 25% of portfolio | Correlated assets move together |
| Max total exposure | 50–80% of portfolio | Cash reserve for opportunities/margin |
| Max positions | 5–10 concurrent | Attention and management bandwidth |

---

## PumpFun / Meme Token Sizing

PumpFun and early-stage meme tokens require special sizing discipline:

- **Very small positions**: 0.1–1 SOL per trade due to extreme risk
- **Scale with bonding curve fill %**: smaller when early (high rug risk), slightly larger when proven (graduated to Raydium)
- **Never size based on expected return** — size based on acceptable total loss
- **Treat as lottery tickets**: expect most to go to zero
- **Position limit**: no more than 5–10% of portfolio across all meme positions combined

```python
# PumpFun sizing example
account_sol = 100
meme_budget = account_sol * 0.05   # 5 SOL total for memes
per_trade = meme_budget / 10       # 0.5 SOL each, 10 shots
```

---

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `risk-management` | Portfolio-level limits, drawdown rules |
| `liquidity-analysis` | Pool depth data for liquidity constraints |
| `kelly-criterion` | Deeper Kelly math, edge estimation |
| `exit-strategies` | Stop loss placement affects fixed fractional sizing |
| `volatility-modeling` | Better vol estimates for volatility-adjusted sizing |
| `slippage-modeling` | Precise slippage estimates for liquidity constraints |

---

## Files

### References
- `references/sizing_formulas.md` — Mathematical derivations for all sizing methods with worked examples
- `references/practical_guide.md` — Sizing by account size, token type, and common mistakes

### Scripts
- `scripts/size_calculator.py` — Calculates position size using all methods, shows binding constraint
- `scripts/portfolio_sizer.py` — Portfolio risk dashboard with per-position risk and available budget

---

## Quick Reference

```python
# Minimal fixed fractional sizing — copy-paste starter
def calc_position_size(
    account: float, risk_pct: float, entry: float, stop: float
) -> float:
    """Return number of units to buy."""
    risk_amount = account * risk_pct
    price_risk = abs(entry - stop)
    if price_risk == 0:
        return 0.0
    return risk_amount / price_risk
```
