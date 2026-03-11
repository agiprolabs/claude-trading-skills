# Copy Trading Risk Framework

Portfolio-level controls, per-wallet limits, performance tracking, and decay detection for copy trading on Solana.

## Portfolio-Level Limits

### Total Copy-Trade Allocation

Limit total capital deployed via copy trades to a fraction of your portfolio.

| Risk Profile | Max Copy Allocation | Rationale |
|-------------|--------------------|-----------|
| Conservative | 20% of portfolio | Copy trading as a supplement |
| Moderate | 40% of portfolio | Balanced between copy and independent trades |
| Aggressive | 60% of portfolio | Heavy reliance on copy signals |

Never allocate 100% to copy trades. Maintain capital for independent opportunities and to absorb losses.

### Per-Wallet Allocation

No single copied wallet should dominate your copy-trade portfolio.

```python
def max_wallet_allocation(
    total_portfolio: float,
    total_copy_allocation_pct: float,
    num_wallets: int,
) -> float:
    """Maximum allocation to any single copied wallet."""
    copy_budget = total_portfolio * total_copy_allocation_pct
    # No wallet gets more than 30% of copy budget or 15% of total portfolio
    per_wallet_max = min(copy_budget * 0.30, total_portfolio * 0.15)
    # But also ensure it is at least evenly distributed
    even_split = copy_budget / max(num_wallets, 1)
    return min(per_wallet_max, even_split * 1.5)
```

### Concurrent Position Limits

| Limit Type | Recommended | Purpose |
|-----------|-------------|---------|
| Max positions per wallet | 2-3 | Prevent overexposure to one signal source |
| Max total copy positions | 5-10 | Manageable monitoring load |
| Max positions per token | 1 | Prevent duplicate exposure from multiple wallets |

## Loss Limits (Circuit Breakers)

### Per-Trade Loss Limit
Stop loss on every copy trade. Recommended: -20% from entry price.

### Per-Wallet Daily Loss Limit
If copy trades from a specific wallet lose more than 3% of your portfolio in one day, pause that wallet until the next day.

### Portfolio Daily Loss Limit
If total copy-trade losses exceed 5% of your portfolio in one day, pause all copy trading until the next day.

```python
def check_circuit_breakers(
    daily_pnl_by_wallet: dict[str, float],
    total_portfolio: float,
) -> dict[str, bool]:
    """Check which wallets should be paused due to loss limits."""
    paused: dict[str, bool] = {}
    total_daily_loss = 0.0
    per_wallet_limit = total_portfolio * 0.03
    portfolio_limit = total_portfolio * 0.05

    for wallet, pnl in daily_pnl_by_wallet.items():
        total_daily_loss += min(pnl, 0)
        if pnl < -per_wallet_limit:
            paused[wallet] = True

    if total_daily_loss < -portfolio_limit:
        # Pause all wallets
        for wallet in daily_pnl_by_wallet:
            paused[wallet] = True

    return paused
```

### Weekly Loss Limit
If total copy-trade losses exceed 10% of your portfolio in one week, pause all copy trading and review your wallet selection.

## Correlation Risk

### The Problem
Multiple copied wallets may trade the same tokens, creating unintended concentration. If you copy 5 wallets and 3 of them buy the same memecoin, you have 3x the intended exposure.

### Detection

```python
def detect_correlation(
    active_positions: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Find tokens held via multiple copied wallets."""
    token_to_wallets: dict[str, list[str]] = {}
    for wallet, tokens in active_positions.items():
        for token in tokens:
            token_to_wallets.setdefault(token, []).append(wallet)
    return {t: ws for t, ws in token_to_wallets.items() if len(ws) > 1}
```

### Mitigation
- Track aggregate exposure per token across all copy sources
- If a token appears in 2+ copied wallets, reduce position size proportionally
- Set a hard per-token limit (e.g., 5% of portfolio) regardless of source

## Decay Detection

Wallet performance degrades over time. Markets change, strategies stop working, or the wallet operator changes behavior. Detect decay early.

### Rolling Performance Check

```python
def detect_decay(
    recent_trades: list[dict],
    lookback_trades: int = 20,
    min_win_rate: float = 0.45,
    min_profit_factor: float = 1.1,
) -> tuple[bool, str]:
    """Check if a wallet's recent performance has decayed."""
    recent = recent_trades[-lookback_trades:]
    if len(recent) < lookback_trades:
        return False, "Insufficient recent trades"

    wins = sum(1 for t in recent if t["pnl"] > 0)
    win_rate = wins / len(recent)

    gross_profit = sum(t["pnl"] for t in recent if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in recent if t["pnl"] < 0))
    pf = gross_profit / max(gross_loss, 0.001)

    if win_rate < min_win_rate:
        return True, f"Win rate decayed to {win_rate:.1%} (min: {min_win_rate:.1%})"
    if pf < min_profit_factor:
        return True, f"Profit factor decayed to {pf:.2f} (min: {min_profit_factor:.2f})"
    return False, "Performance acceptable"
```

### When to Remove a Wallet

Remove a wallet from your copy list when:

1. **Win rate drops below 45%** over the last 20 trades
2. **Profit factor drops below 1.1** over the last 20 trades
3. **Inactivity**: no trades in 14+ days
4. **Style change**: median hold time shifts by > 2x (e.g., swing trader becomes sniper)
5. **Loss streak**: 5+ consecutive losing trades
6. **Sybil alert**: wallet flagged by sybil-detection after initial approval

## Diversification Requirements

### By Wallet Style
Copy wallets across different trading styles to reduce correlation:

| Style | Target Allocation | Why |
|-------|------------------|-----|
| Scalper | 20-30% | High frequency, small gains |
| Day Trader | 30-40% | Moderate frequency, balanced risk |
| Swing Trader | 30-40% | Lower frequency, larger moves |
| Sniper | 0-10% | Very high risk, hard to replicate |

### By Token Type
Avoid copying wallets that all trade the same token category:
- Mix PumpFun/memecoin traders with established token traders
- Include at least one wallet that trades higher-cap tokens (top 100)

## Performance Tracking

### Per-Wallet Attribution

Track P&L separately for each copied wallet:

```python
from dataclasses import dataclass, field

@dataclass
class WalletCopyStats:
    wallet: str
    trades_copied: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl_sol: float = 0.0
    total_invested_sol: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / max(self.trades_copied, 1)

    @property
    def roi(self) -> float:
        return self.total_pnl_sol / max(self.total_invested_sol, 0.001)
```

### Aggregate Metrics

Track overall copy-trade performance vs. your independent trades:

| Metric | Calculation | Target |
|--------|------------|--------|
| Copy trade win rate | Wins / total copy trades | > 50% |
| Copy trade ROI | Total copy PnL / total copy capital deployed | > 0% |
| Copy vs. independent | Copy ROI - independent ROI | Positive (copy adds value) |
| Best wallet ROI | Highest per-wallet ROI | Identifies top signal sources |
| Worst wallet ROI | Lowest per-wallet ROI | Identifies wallets to remove |

### Review Cadence

| Frequency | Action |
|-----------|--------|
| Daily | Check circuit breakers, review active positions |
| Weekly | Review per-wallet performance, check for decay |
| Monthly | Full re-evaluation of all copied wallets, update scores |
| Quarterly | Review overall copy-trade strategy effectiveness |
