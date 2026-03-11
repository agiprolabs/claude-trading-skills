# Position Sizing — Practical Guide

Actionable sizing guidelines by account size, token type, and situation. Covers common mistakes and adjustment rules.

---

## Sizing by Account Size

### Micro Accounts (<$1K / <7 SOL)

- **Fixed amount per trade**: 0.05–0.1 SOL
- **Focus**: Learning, not profit. Treat as tuition.
- **Max concurrent positions**: 3
- **Total exposure**: up to 80% (small accounts need concentration)
- **Key rule**: Never deposit more to "average down"

### Small Accounts ($1K–$10K / 7–70 SOL)

- **Risk per trade**: 1–2% of account
- **Max concurrent positions**: 5
- **Max single position**: 10% of account
- **Total exposure**: 50–70%
- **Key rule**: Fees matter — avoid tokens with wide spreads

### Medium Accounts ($10K–$100K / 70–700 SOL)

- **Risk per trade**: 0.5–1% of account
- **Max concurrent positions**: 7–10
- **Max single position**: 8% of account
- **Total exposure**: 40–60%
- **Key rule**: Start considering liquidity constraints on smaller tokens

### Large Accounts (>$100K / >700 SOL)

- **Risk per trade**: 0.25–0.5% of account
- **Max concurrent positions**: 10–15
- **Max single position**: 5% of account
- **Total exposure**: 30–50%
- **Key rule**: Liquidity is your primary constraint. Split entries across time.

---

## Sizing by Token Type

### Blue Chip (SOL, ETH, BTC)

- **Max position size**: up to 10% of portfolio
- **Sizing method**: Fixed fractional or volatility-adjusted
- **Typical ATR daily vol**: 3–6%
- **Liquidity constraint**: rarely binding (deep pools)
- **Stop loss distance**: 5–10% from entry typical

### Mid-Cap (Top 100 — JUP, BONK, WIF, PYTH)

- **Max position size**: up to 5% of portfolio
- **Sizing method**: Fixed fractional with liquidity check
- **Typical ATR daily vol**: 5–15%
- **Liquidity constraint**: check for accounts >$50K
- **Stop loss distance**: 8–15% from entry typical

### Small-Cap (Top 500)

- **Max position size**: up to 2% of portfolio
- **Sizing method**: Fixed fractional, liquidity-constrained
- **Typical ATR daily vol**: 10–30%
- **Liquidity constraint**: almost always binding
- **Stop loss distance**: 15–25% from entry typical

### PumpFun / Meme / Micro-Cap

- **Max position size**: 0.5–1% of portfolio per token
- **Max total meme allocation**: 5–10% of portfolio
- **Sizing method**: Fixed amount (lottery ticket sizing)
- **Typical ATR daily vol**: 30–100%+
- **Liquidity constraint**: always binding
- **Stop loss**: assume 100% loss is possible; size accordingly

---

## When to Adjust Sizing

### Reduce Size

| Trigger | Action | Rationale |
|---------|--------|-----------|
| 3 consecutive losses | Reduce to 50% normal size | Possible regime change |
| Drawdown > 10% from peak | Reduce to minimum size | Capital preservation mode |
| New/untested strategy | Start at 25% normal size | Earn the right to full size |
| Market volatility spike (VIX-like) | Reduce by vol ratio | Same dollar risk needs less exposure |
| Unusual correlation across positions | Cut weakest positions | Correlated risk compounds |

### Increase Size (Cautiously)

| Trigger | Action | Rationale |
|---------|--------|-----------|
| 50+ trade track record with edge | Scale from 25% to 100% over time | Statistical confidence |
| Win streak > 5 | Allow up to 1.5x normal size | Strategy may be in sync |
| Low volatility regime | Vol-adjusted increase is mechanical | Same risk, larger notional |
| Account growth milestone | Recalculate base size upward | Compound growth |

### Never Increase Size When

- Trying to recover from losses ("revenge trading")
- A single trade seems like a "sure thing" (no such thing)
- You haven't adjusted stops to match the larger size
- Your recent win streak is < 10 trades (not statistically significant)

---

## Position Sizing Mistakes

### 1. Sizing Based on Conviction

**Wrong**: "I'm really confident in this trade, so I'll 5x my normal size."

**Right**: Let the math decide. Conviction is emotional, not quantitative. If you have a measured edge that justifies larger size, the Kelly formula will tell you.

### 2. Not Accounting for Fees and Slippage

**Wrong**: Calculating stop distance as `entry - stop` only.

**Right**: Include round-trip fees (0.3–0.6% typical) and expected slippage (0.1–2% depending on token) in your risk calculation.

### 3. Ignoring Correlation Between Positions

**Wrong**: "I'm risking 2% on each of 10 positions = 20% max risk."

**Right**: If 8 of those positions are meme tokens that all dump together, your effective risk is closer to 16% in a single correlated move. Account for correlation in portfolio limits.

### 4. Increasing Size to Make Back Losses

**Wrong**: After a 10% drawdown, doubling size to "get back to even faster."

**Right**: Reduce size during drawdowns. You need to earn back losses with smaller, consistent gains. The math: a 10% loss needs 11.1% gain to recover; a 50% loss needs 100%.

### 5. Using Position Size as Stop Loss

**Wrong**: "I'll just buy a small amount so if it goes to zero it's fine."

**Right**: Always use an explicit stop loss. "Small size, no stop" leads to holding worthless positions that tie up capital. Exception: PumpFun lottery tickets explicitly sized for 100% loss.

### 6. Not Adjusting for Timeframe

**Wrong**: Using the same 2% risk for a 5-minute scalp and a multi-week swing trade.

**Right**: Shorter timeframes need tighter stops relative to volatility, which means either smaller position sizes or accepting more noise. Scale risk per trade with expected hold time.

### 7. Forgetting Portfolio-Level Limits

**Wrong**: Each trade is individually sized, but no check on total exposure.

**Right**: Before each new position, verify:
- Total portfolio exposure is within limits
- Correlated exposure is within limits
- Total risk-on (sum of all position risks) is acceptable

---

## Quick Decision Tree

```
Want to enter a trade?
│
├─ Do you have a measured edge (50+ trades)?
│  ├─ Yes → Calculate Kelly size (use 0.25x)
│  └─ No  → Use fixed fractional (1% risk)
│
├─ Calculate fixed fractional size
│
├─ Is the token volatile (ATR > 10% daily)?
│  ├─ Yes → Also calculate vol-adjusted size
│  └─ No  → Skip vol adjustment
│
├─ Is pool liquidity < 50x your desired position?
│  ├─ Yes → Calculate liquidity-constrained max
│  └─ No  → Liquidity is not binding
│
├─ Take minimum of all calculated sizes
│
├─ Check portfolio limits:
│  ├─ Single position < 10% portfolio? ✓
│  ├─ Correlated exposure < 25%? ✓
│  └─ Total exposure < 80%? ✓
│
└─ Execute at recommended size
```

---

## SOL-Denominated Quick Reference

For a 100 SOL account ($15,000 at $150/SOL):

| Risk Level | Risk/Trade | SOL at Risk | Typical Position |
|-----------|-----------|-------------|-----------------|
| Conservative (0.5%) | 0.5 SOL | $75 | 2–5 SOL notional |
| Standard (1%) | 1.0 SOL | $150 | 5–10 SOL notional |
| Moderate (2%) | 2.0 SOL | $300 | 10–20 SOL notional |
| Aggressive (3%) | 3.0 SOL | $450 | 15–30 SOL notional |
| PumpFun | 0.1–0.5 SOL | $15–$75 | 0.1–0.5 SOL per play |
