# Performance Metrics Reference

Detailed formulas, interpretation guidelines, and edge case handling for wallet performance analysis.

## Win Rate

**Formula:**
```
win_rate = count(trades where pnl > 0) / count(all_closed_trades)
```

**Requirements:**
- Minimum 30 closed trades for statistical significance
- Only count fully closed positions (all tokens sold)
- Include fees in PnL calculation (a trade that made 0.01 SOL but cost 0.005 SOL in fees is still a win at 0.005 SOL net)

**Interpretation:**
| Win Rate | Assessment | Context |
|----------|-----------|---------|
| > 80% | Suspicious | Possible wash trading or tiny wins with large losses |
| 60–80% | Excellent | Sustainable if profit factor also high |
| 45–60% | Good | Standard for profitable traders with good R:R |
| 30–45% | Acceptable | Can be profitable with high avg win / avg loss ratio |
| < 30% | Poor | Rarely sustainable regardless of win size |

**By token type:**
Separate win rates for PumpFun tokens vs. established tokens. PumpFun win rates are typically lower (30–40%) but winners can be 10x+, while established token trading shows higher win rates (50–60%) with smaller moves.

## ROI Per Trade

**Formula:**
```
roi = (exit_value - entry_value - total_fees) / entry_value
```

Where:
- `entry_value` = total SOL spent buying the token (sum of all buys)
- `exit_value` = total SOL received selling the token (sum of all sells)
- `total_fees` = platform fees + priority fees + estimated slippage

**Handling Partial Exits (FIFO):**
```python
def compute_roi_fifo(buys: list[dict], sells: list[dict]) -> float:
    """Compute ROI using FIFO cost basis.

    Args:
        buys: [{"amount": token_qty, "cost_sol": sol_spent}, ...]
        sells: [{"amount": token_qty, "proceeds_sol": sol_received}, ...]

    Returns:
        ROI as a decimal (0.5 = 50% gain).
    """
    buy_queue = list(buys)  # FIFO queue
    total_cost = 0.0
    total_proceeds = 0.0

    for sell in sells:
        remaining = sell["amount"]
        total_proceeds += sell["proceeds_sol"]

        while remaining > 0 and buy_queue:
            buy = buy_queue[0]
            if buy["amount"] <= remaining:
                total_cost += buy["cost_sol"]
                remaining -= buy["amount"]
                buy_queue.pop(0)
            else:
                fraction = remaining / buy["amount"]
                total_cost += buy["cost_sol"] * fraction
                buy["amount"] -= remaining
                buy["cost_sol"] *= (1 - fraction)
                remaining = 0

    if total_cost == 0:
        return 0.0
    return (total_proceeds - total_cost) / total_cost
```

**Fee Estimation:**
- Solana base fee: 0.000005 SOL per transaction
- Priority fee: variable, typically 0.0001–0.01 SOL
- Jupiter platform fee: 0 (no fee) for basic swaps
- Slippage: estimate from trade size vs. pool liquidity

## Profit Factor

**Formula:**
```
profit_factor = sum(pnl for trades where pnl > 0) / abs(sum(pnl for trades where pnl < 0))
```

**Edge Cases:**
- No losing trades: profit_factor = infinity (use a cap of 99.9)
- No winning trades: profit_factor = 0
- No closed trades: undefined (return None)

**Interpretation:**
| Profit Factor | Rating | Meaning |
|--------------|--------|---------|
| > 3.0 | Exceptional | Very high edge, verify not cherry-picked |
| 2.0–3.0 | Excellent | Strong, sustainable edge |
| 1.5–2.0 | Good | Solid performance |
| 1.0–1.5 | Marginal | Small edge, vulnerable to costs |
| 0.7–1.0 | Poor | Losing after costs |
| < 0.7 | Very Poor | Significant negative edge |

**Rolling Profit Factor:**
Calculate profit factor over rolling windows to detect performance trends:
```python
def rolling_profit_factor(pnl_series: list[float], window: int = 20) -> list[float]:
    """Compute rolling profit factor over a sliding window."""
    results = []
    for i in range(window, len(pnl_series) + 1):
        window_pnl = pnl_series[i - window:i]
        wins = sum(p for p in window_pnl if p > 0)
        losses = abs(sum(p for p in window_pnl if p < 0))
        pf = wins / losses if losses > 0 else 99.9
        results.append(round(pf, 2))
    return results
```

## Sharpe-Like Ratio

**Formula:**
```
sharpe = mean(trade_returns) / std(trade_returns) * sqrt(trades_per_year)
```

**Annualization:**
- Estimate `trades_per_year` from observed frequency
- `trades_per_year = trades_per_day * 365`
- If trading for < 30 days, annualization is unreliable

**Interpretation:**
| Annualized Sharpe | Rating |
|-------------------|--------|
| > 3.0 | Exceptional (verify data quality) |
| 2.0–3.0 | Excellent |
| 1.0–2.0 | Good |
| 0.5–1.0 | Mediocre |
| < 0.5 | Poor |

**Note:** This is an approximation. True Sharpe uses continuous returns and a risk-free rate. For crypto trading with discrete trade-level returns, this metric provides directional guidance rather than precise comparison with traditional finance Sharpe ratios.

## Maximum Drawdown

**Formula:**
```python
def max_drawdown(cumulative_pnl: list[float]) -> tuple[float, int, int]:
    """Compute maximum drawdown from cumulative PnL series.

    Returns:
        (max_dd_pct, peak_index, trough_index)
    """
    peak = cumulative_pnl[0]
    peak_idx = 0
    max_dd = 0.0
    max_dd_peak = 0
    max_dd_trough = 0

    for i, value in enumerate(cumulative_pnl):
        if value > peak:
            peak = value
            peak_idx = i

        if peak > 0:
            dd = (peak - value) / peak
        else:
            dd = 0

        if dd > max_dd:
            max_dd = dd
            max_dd_peak = peak_idx
            max_dd_trough = i

    return (round(max_dd, 4), max_dd_peak, max_dd_trough)
```

**Interpretation:**
| Max Drawdown | Assessment |
|-------------|-----------|
| < 10% | Very conservative |
| 10–25% | Disciplined risk management |
| 25–50% | Moderate risk, common in crypto |
| 50–75% | High risk tolerance |
| > 75% | Extremely aggressive or poor risk management |

## Performance Decay Detection

Compare recent performance to historical performance to detect declining edge.

```python
def detect_decay(
    trade_pnls: list[float],
    recent_window: int = 30,
) -> dict:
    """Detect performance decay by comparing recent vs. historical metrics.

    Args:
        trade_pnls: Chronological list of trade PnLs.
        recent_window: Number of recent trades to compare.

    Returns:
        Decay assessment with metrics comparison.
    """
    if len(trade_pnls) < recent_window * 2:
        return {"status": "insufficient_data"}

    recent = trade_pnls[-recent_window:]
    historical = trade_pnls[:-recent_window]

    recent_wr = sum(1 for p in recent if p > 0) / len(recent)
    hist_wr = sum(1 for p in historical if p > 0) / len(historical)

    recent_avg = sum(recent) / len(recent)
    hist_avg = sum(historical) / len(historical)

    r_wins = sum(p for p in recent if p > 0)
    r_losses = abs(sum(p for p in recent if p < 0))
    recent_pf = r_wins / r_losses if r_losses > 0 else 99.9

    h_wins = sum(p for p in historical if p > 0)
    h_losses = abs(sum(p for p in historical if p < 0))
    hist_pf = h_wins / h_losses if h_losses > 0 else 99.9

    wr_change = recent_wr - hist_wr
    pf_change = recent_pf - hist_pf

    if wr_change < -0.1 and pf_change < -0.5:
        status = "significant_decay"
    elif wr_change < -0.05 or pf_change < -0.3:
        status = "moderate_decay"
    elif wr_change > 0.05 and pf_change > 0.3:
        status = "improving"
    else:
        status = "stable"

    return {
        "status": status,
        "recent_win_rate": round(recent_wr, 3),
        "historical_win_rate": round(hist_wr, 3),
        "win_rate_delta": round(wr_change, 3),
        "recent_profit_factor": round(recent_pf, 2),
        "historical_profit_factor": round(hist_pf, 2),
        "profit_factor_delta": round(pf_change, 2),
        "recent_avg_pnl": round(recent_avg, 4),
        "historical_avg_pnl": round(hist_avg, 4),
    }
```

## Consistency Metrics

### Rolling Win Rate Stability

```python
def win_rate_stability(trade_pnls: list[float], window: int = 20) -> float:
    """Compute standard deviation of rolling win rate.

    Lower values indicate more consistent performance.
    """
    import statistics
    if len(trade_pnls) < window * 2:
        return -1.0

    rolling_wrs = []
    for i in range(window, len(trade_pnls) + 1):
        chunk = trade_pnls[i - window:i]
        wr = sum(1 for p in chunk if p > 0) / len(chunk)
        rolling_wrs.append(wr)

    return round(statistics.stdev(rolling_wrs), 3)
```

### Consistency Score

Combine stability measures into a composite 0–100 score by summing contributions from win rate stability (lower std = better), drawdown control (lower = better), profit factor sustainability (higher = better), and sample size (more trades = more reliable). Start from a base of 50 and add/subtract up to 20 points per factor.
