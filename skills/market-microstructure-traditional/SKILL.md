---
name: market-microstructure-traditional
description: Traditional market microstructure concepts applied to crypto — order book dynamics, market making theory, price formation models, execution quality measurement, and CEX vs DEX structural differences
---

# Market Microstructure (Traditional)

Market microstructure studies how orders become trades and how trades become
prices.  Understanding these mechanics is essential for execution optimization,
market making, and detecting informed flow.  This skill covers limit order book
(LOB) theory as applied to crypto markets on centralized exchanges, and compares
LOB mechanics to the AMM-based structure of DEXes.

## Core Concepts

| Concept | What It Tells You |
|---|---|
| **Bid-ask spread** | Cost of immediacy — how much you pay to trade now vs later |
| **Price impact** | How your order moves the market price |
| **Order book imbalance** | Short-term directional predictor from queue sizes |
| **Adverse selection** | Risk of trading against informed counterparties |
| **Inventory risk** | Market maker exposure from accumulated positions |
| **Execution quality** | How well your fills compare to a benchmark |

---

## Bid-Ask Spread Decomposition

The bid-ask spread is not a single thing.  It decomposes into three components
(Roll, 1984; Glosten & Harris, 1988):

1. **Adverse selection** — compensation for trading against informed traders
2. **Inventory holding** — compensation for carrying risk
3. **Order processing** — fixed costs of providing liquidity (fees, infrastructure)

### Spread Measures

```python
# Quoted spread: what you see on the order book
quoted_spread = best_ask - best_bid
quoted_spread_bps = (best_ask - best_bid) / midprice * 10_000

# Effective spread: what you actually pay (accounts for price improvement)
effective_half_spread = abs(trade_price - midprice_at_trade)
effective_spread_bps = effective_half_spread / midprice_at_trade * 10_000

# Realized spread: market maker's actual profit (after price moves)
# Measured at trade_price vs midprice N seconds later
realized_spread = trade_sign * (trade_price - midprice_after_delay)
```

The **effective spread** matters most for execution quality.  The difference
between effective and realized spread measures adverse selection — what the
market maker loses to informed flow.

---

## Price Formation Models

### Glosten-Milgrom (1985)

A sequential trade model where the market maker sets bid and ask prices to
break even against a mix of informed and uninformed traders.

- Market maker quotes reflect *expected value conditional on trade direction*
- Spread exists purely due to adverse selection
- Prices converge to true value as information is revealed through trades

Key insight: the spread is wider when:
- Probability of informed trading (PIN) is higher
- Information asymmetry is larger
- Uninformed trading volume is lower

### Kyle's Lambda (1985)

Kyle models a single informed trader, noise traders, and a market maker.
The market maker sets price as a linear function of net order flow:

```
price_change = lambda * net_order_flow
```

**Lambda (λ)** measures permanent price impact per unit of signed volume.
Higher lambda = less liquid market.  Lambda is estimated by regressing
price changes on signed volume:

```python
import numpy as np
from numpy.linalg import lstsq

def estimate_kyle_lambda(
    price_changes: np.ndarray,
    signed_volumes: np.ndarray,
) -> float:
    """Estimate Kyle's lambda from trade data.

    Args:
        price_changes: Midprice changes between trades.
        signed_volumes: Trade volume * trade_sign (+1 buy, -1 sell).

    Returns:
        Estimated lambda (price impact per unit volume).
    """
    X = signed_volumes.reshape(-1, 1)
    beta, _, _, _ = lstsq(X, price_changes, rcond=None)
    return float(beta[0])
```

See `references/price_formation.md` for full model derivations and the PIN
model for measuring informed trading probability.

---

## Price Impact Models

### Temporary vs Permanent Impact (Almgren-Chriss)

When executing a large order:

- **Temporary impact** — price displacement that reverts after your order.
  Caused by consuming standing liquidity.
- **Permanent impact** — information content of your trade that moves the
  equilibrium price.  Does not revert.

```
total_impact = permanent_impact + temporary_impact
permanent = gamma * (shares / ADV)
temporary = eta * (shares / time_horizon) ^ alpha
```

Typical alpha values: 0.5-0.7 (square root impact is a robust empirical finding).

### Square Root Impact Law

Empirically, price impact scales as the square root of order size relative
to daily volume:

```python
def square_root_impact(
    order_size: float,
    daily_volume: float,
    volatility: float,
    impact_coefficient: float = 0.1,
) -> float:
    """Estimate price impact using the square root model.

    Args:
        order_size: Number of units to trade.
        daily_volume: Average daily volume.
        volatility: Daily return volatility (decimal).
        impact_coefficient: Empirical constant (typically 0.05-0.20).

    Returns:
        Expected price impact as a fraction.
    """
    return impact_coefficient * volatility * (order_size / daily_volume) ** 0.5
```

---

## Order Book Imbalance

The ratio of bid-side to ask-side depth near the top of the book predicts
short-term price direction:

```python
def order_book_imbalance(
    bid_qty: float,
    ask_qty: float,
) -> float:
    """Compute order book imbalance.

    Returns:
        Imbalance in [-1, 1]. Positive = more bids (bullish).
    """
    total = bid_qty + ask_qty
    if total == 0:
        return 0.0
    return (bid_qty - ask_qty) / total
```

Imbalance at levels 1-5 is a strong short-term predictor (Cont et al., 2014).
Deeper levels add predictive power but decay quickly.

---

## Trade Arrival Processes

### Poisson Process

Simplest model: trades arrive at a constant rate λ.  Inter-arrival times are
exponentially distributed.  Useful as a baseline but too simple for real
order flow.

### Hawkes Process

Self-exciting point process where each trade increases the probability of
subsequent trades.  Captures clustering in order flow:

```
intensity(t) = mu + sum(alpha * exp(-beta * (t - t_i)))
```

- **mu**: baseline arrival rate
- **alpha**: excitation magnitude (how much each event boosts intensity)
- **beta**: decay rate (how fast excitation fades)
- **alpha/beta < 1**: stationarity condition (branching ratio)

The branching ratio α/β measures the fraction of trades that are
*reactions* rather than *innovations*.  Typical values: 0.5-0.8 in
crypto markets (high reactivity).

---

## Market Maker Economics

A market maker profits from the spread but faces three risks:

1. **Adverse selection** — losing to informed traders
2. **Inventory risk** — accumulated directional exposure
3. **Competition** — other MMs narrowing the spread

### Avellaneda-Stoikov Model

The optimal bid and ask quotes for a market maker with inventory `q`:

```
reservation_price = midprice - q * gamma * sigma^2 * T
optimal_spread = gamma * sigma^2 * T + (2/gamma) * ln(1 + gamma/k)
```

Where:
- `q`: current inventory (positive = long)
- `gamma`: risk aversion parameter
- `sigma`: volatility
- `T`: time remaining
- `k`: order arrival rate parameter

Key insight: the reservation price *skews away from inventory* — a long
market maker lowers their price to encourage sells.

---

## Execution Quality Measurement

### VWAP Benchmark

Volume-Weighted Average Price is the standard benchmark for passive execution:

```python
def vwap(prices: list[float], volumes: list[float]) -> float:
    """Compute VWAP from trade prices and volumes."""
    pv_sum = sum(p * v for p, v in zip(prices, volumes))
    v_sum = sum(volumes)
    return pv_sum / v_sum if v_sum > 0 else 0.0

# Execution quality vs VWAP
slippage_vs_vwap = (avg_fill_price - vwap_benchmark) / vwap_benchmark * 10_000
```

### Implementation Shortfall

Measures total cost of executing vs the decision price (Perold, 1988):

```
implementation_shortfall = (execution_price - decision_price) * quantity
```

Decomposes into:
- **Delay cost**: price drift between decision and first fill
- **Market impact**: price move caused by your order
- **Timing cost**: cost of breaking the order into slices
- **Opportunity cost**: value of unfilled portions

See `references/execution_quality.md` for complete methodology.

---

## CEX Order Book vs DEX AMM

| Dimension | CEX (LOB) | DEX (AMM) |
|---|---|---|
| **Price discovery** | Limit orders express willingness to trade | Algorithmic curve (x·y=k) |
| **Spread** | Set by competing market makers | Determined by pool depth and fee tier |
| **Depth** | Visible order book | Implicit from TVL and curve shape |
| **Adverse selection** | MMs reprice on information | LPs suffer impermanent loss |
| **Execution** | Price-time priority | First-come via block inclusion |
| **Latency** | Microseconds | Block time (400ms Solana, 12s Ethereum) |
| **MEV** | Front-running is harder (colocated MMs) | Sandwich attacks are endemic |
| **Fees** | Maker/taker (often maker rebate) | Fixed tier (e.g., 5, 30, 100 bps) |

**When to use CEX**: large orders, latency-sensitive strategies, tight spreads
needed, BTC/ETH/major pairs.

**When to use DEX**: long-tail tokens, censorship resistance, composability
with DeFi, transparent execution.

See `references/cex_vs_dex.md` for detailed structural comparison.

---

## Maker/Taker Fee Structures

CEX fee tiers create incentive asymmetries:

| Tier | Maker Fee | Taker Fee | Net Spread Required |
|---|---|---|---|
| VIP 0 | 0.10% | 0.10% | 20 bps to break even |
| VIP 5 | 0.02% | 0.05% | 7 bps to break even |
| VIP 9 | -0.005% | 0.03% | 2.5 bps + rebate income |

At high tiers, maker rebates mean market makers are *paid* to provide
liquidity.  This fundamentally changes strategy economics:

```python
def maker_pnl_per_trade(
    spread_captured_bps: float,
    maker_fee_bps: float,
    adverse_selection_bps: float,
) -> float:
    """Compute market maker P&L per round trip.

    Args:
        spread_captured_bps: Half-spread captured on each side.
        maker_fee_bps: Maker fee (negative = rebate).
        adverse_selection_bps: Expected loss to informed flow.

    Returns:
        Net P&L in basis points per round trip.
    """
    gross = 2 * spread_captured_bps  # earn half-spread on each leg
    fees = 2 * maker_fee_bps         # pay/receive fee on each leg
    return gross - fees - adverse_selection_bps
```

---

## Files

### References
- `references/price_formation.md` — Glosten-Milgrom, Kyle model, PIN model, spread decomposition
- `references/execution_quality.md` — VWAP, TWAP, implementation shortfall, slippage decomposition
- `references/cex_vs_dex.md` — Structural comparison of LOB vs AMM, hybrid models, routing decisions

### Scripts
- `scripts/spread_analysis.py` — Analyze bid-ask spreads, compute effective/realized/quoted spread from trade data (--demo mode with synthetic order book)
- `scripts/market_maker_sim.py` — Market maker simulation with inventory management and P&L (--demo mode with synthetic price path)

---

## Dependencies

```bash
uv pip install numpy pandas scipy matplotlib
```

---

## Related Skills

- **market-microstructure** — On-chain DEX microstructure (AMM-specific)
- **slippage-modeling** — Execution cost estimation and modeling
- **liquidity-analysis** — Pool and order book depth analysis
- **order-execution** — Practical execution algorithms
- **mev-analysis** — MEV risk in on-chain execution
