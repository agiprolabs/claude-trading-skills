# Execution Quality Measurement

How to evaluate whether your trades were executed well. This reference covers
standard benchmarks, slippage decomposition, and practical measurement.

---

## Benchmarks

### VWAP — Volume-Weighted Average Price

The most common benchmark for passive execution. VWAP represents the average
price weighted by volume over a period:

```
VWAP = Σ(price_i * volume_i) / Σ(volume_i)
```

**When to use**: evaluating execution of orders that are not time-sensitive.
VWAP is a fair benchmark when you have discretion over execution timing
within a window.

**Limitations**: VWAP is manipulable (your own trades affect it), does not
penalize delay, and is meaningless for orders that dominate the volume.

```python
import numpy as np

def compute_vwap(
    prices: np.ndarray,
    volumes: np.ndarray,
) -> float:
    """Compute VWAP from arrays of prices and volumes."""
    return float(np.sum(prices * volumes) / np.sum(volumes))

def vwap_slippage_bps(
    fill_price: float,
    vwap: float,
    side: str,
) -> float:
    """Compute slippage vs VWAP in basis points.

    Positive = you paid more than VWAP (bad for buys).
    """
    sign = 1.0 if side == "buy" else -1.0
    return sign * (fill_price - vwap) / vwap * 10_000
```

### TWAP — Time-Weighted Average Price

Simple average of prices at equal time intervals. Less common as a benchmark
but used as an execution strategy:

```
TWAP = (1/N) * Σ(price_i)
```

**When to use**: when volume profile is unknown or irrelevant.

### Arrival Price (Decision Price)

The midprice at the moment you decide to trade. This is the theoretically
correct benchmark because it captures the full cost of execution including
delay and market impact.

```
arrival_slippage = (avg_fill_price - arrival_price) * trade_sign
```

### Previous Close

Used mainly in TradFi for overnight order evaluation. Less relevant for
24/7 crypto markets, but applicable for comparing daily strategy signals.

---

## Implementation Shortfall (Perold, 1988)

The total cost of turning a trading decision into a completed position.
Decomposes into four components:

### Formula

```
IS = (execution_price - decision_price) * filled_qty
   + (closing_price - decision_price) * unfilled_qty
```

### Decomposition

| Component | Formula | What It Measures |
|---|---|---|
| **Delay cost** | (broker_price - decision_price) * qty | Cost of waiting to start |
| **Market impact** | (avg_fill - broker_price) * filled_qty | Your order moving the price |
| **Timing cost** | Σ(slice_price - arrival_price) * slice_qty | Cost of splitting over time |
| **Opportunity cost** | (close_price - decision_price) * unfilled_qty | Cost of not filling entirely |

### Example

```
Decision price: $100.00 (midprice when you decide to buy 1000 shares)
Order start:    $100.05 (30 seconds delay)
Fill 1:         $100.10 (500 shares)
Fill 2:         $100.15 (400 shares)
Unfilled:       100 shares (market moved to $100.50 by close)

Delay cost:     ($100.05 - $100.00) * 1000     = $50
Market impact:  ($100.12 - $100.05) * 900       = $63
Opportunity:    ($100.50 - $100.00) * 100        = $50
Total IS:       $163 (16.3 bps on a $100K order)
```

---

## Slippage Decomposition for Crypto

Crypto-specific slippage sources:

### 1. Spread Cost
The bid-ask spread you cross to get a fill.

```
spread_cost = 0.5 * quoted_spread * trade_sign
```

### 2. Depth Cost (Market Impact)
Consuming liquidity beyond the top of book.

```python
def depth_cost(
    order_size: float,
    book_levels: list[tuple[float, float]],
) -> float:
    """Compute cost of walking the book.

    Args:
        order_size: Quantity to fill.
        book_levels: List of (price, quantity) tuples from best to worst.

    Returns:
        Average fill price.
    """
    filled = 0.0
    cost = 0.0
    for price, qty in book_levels:
        fill_at_level = min(qty, order_size - filled)
        cost += fill_at_level * price
        filled += fill_at_level
        if filled >= order_size:
            break
    return cost / filled if filled > 0 else 0.0
```

### 3. Timing Cost
Price drift during multi-slice execution.

### 4. Fee Cost
Maker/taker fees on CEX, swap fees on DEX.

### 5. MEV Cost (DEX only)
Sandwich attacks and front-running on-chain.

### Total Slippage

```
total_slippage = spread_cost + depth_cost + timing_cost + fee_cost + mev_cost
```

---

## Measuring Execution Quality in Practice

### Step 1: Record Decision Points

For every trade, log:
- Decision timestamp and midprice
- Order submission timestamp
- Each fill: timestamp, price, quantity, fee
- Order completion or cancellation timestamp

### Step 2: Compute Benchmarks

```python
from dataclasses import dataclass

@dataclass
class ExecutionReport:
    """Execution quality report for a single order."""
    decision_price: float
    avg_fill_price: float
    vwap_benchmark: float
    filled_qty: float
    total_qty: float
    fees_paid: float

    @property
    def fill_rate(self) -> float:
        return self.filled_qty / self.total_qty if self.total_qty > 0 else 0.0

    @property
    def is_bps(self) -> float:
        """Implementation shortfall in basis points."""
        return (self.avg_fill_price - self.decision_price) / self.decision_price * 10_000

    @property
    def vs_vwap_bps(self) -> float:
        """Slippage vs VWAP in basis points."""
        return (self.avg_fill_price - self.vwap_benchmark) / self.vwap_benchmark * 10_000

    @property
    def total_cost_bps(self) -> float:
        """Total execution cost including fees."""
        fee_bps = self.fees_paid / (self.avg_fill_price * self.filled_qty) * 10_000
        return self.is_bps + fee_bps
```

### Step 3: Aggregate and Compare

Track execution quality over time:
- By venue (which exchange gives best fills?)
- By time of day (when is liquidity best?)
- By order size bucket (how does impact scale?)
- By urgency (does rushing cost more than waiting?)

### Step 4: A/B Test Execution Strategies

Split order flow between strategies and compare:

```python
def execution_ab_test(
    strategy_a_slippages: list[float],
    strategy_b_slippages: list[float],
) -> dict:
    """Compare two execution strategies via t-test.

    Args:
        strategy_a_slippages: Slippage in bps for strategy A fills.
        strategy_b_slippages: Slippage in bps for strategy B fills.

    Returns:
        Dict with mean difference, t-statistic, p-value.
    """
    from scipy import stats
    t_stat, p_value = stats.ttest_ind(
        strategy_a_slippages,
        strategy_b_slippages,
        equal_var=False,  # Welch's t-test
    )
    return {
        "mean_a_bps": float(np.mean(strategy_a_slippages)),
        "mean_b_bps": float(np.mean(strategy_b_slippages)),
        "difference_bps": float(np.mean(strategy_a_slippages) - np.mean(strategy_b_slippages)),
        "t_statistic": float(t_stat),
        "p_value": float(p_value),
    }
```

---

## Practical Tips for Crypto

1. **Always measure vs arrival price**, not vs VWAP alone — VWAP can hide
   delay costs and adverse selection.

2. **Account for fees in all comparisons** — a 2 bps spread improvement is
   worthless if the venue charges 5 bps more in fees.

3. **Measure realized spread with 5-30 second delays** — this captures the
   adverse selection you face.

4. **Track fill rates** — a strategy that gets great prices but only fills
   50% of the time may cost more in opportunity than one with worse fills
   but 100% completion.

5. **Beware survivorship bias** — don't only measure completed orders.
   Cancelled or partially filled orders often had the worst expected
   execution (that's why they weren't filled).

6. **On DEX, include MEV cost** — check if your transaction was sandwiched
   by comparing your fill to the pre-transaction pool state.
