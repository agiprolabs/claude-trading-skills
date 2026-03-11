---
name: cost-basis-engine
description: Multi-method cost basis computation including specific identification, FIFO, LIFO, HIFO, and proportional average cost with partial sell handling
license: MIT
metadata:
  author: agipro
  version: "0.1.0"
  category: trading
---

# Cost Basis Engine

Compute cost basis for crypto trades using multiple accounting methods and compare the resulting tax liability across methods. This skill handles the full complexity of on-chain activity: partial sells, token migrations, airdrops, staking rewards, LP entry/exit, and multi-hop swaps.

> **Disclaimer**: This skill provides computational tools for informational purposes only. It does not constitute tax, legal, or financial advice. Consult a qualified tax professional for your specific situation. Tax law varies by jurisdiction and changes frequently.

## Prerequisites

- Python 3.10+
- No external dependencies required (standard library only)
- Trade history as a list of dicts or CSV with columns: `date`, `action`, `token`, `quantity`, `price_usd`, `fee_usd`

## Methods Overview

| Method | Logic | Best For |
|--------|-------|----------|
| **FIFO** | First lots purchased are sold first | Simplicity, many jurisdictions' default |
| **LIFO** | Last lots purchased are sold first | Deferring gains when prices rise over time |
| **HIFO** | Highest-cost lots are sold first | Minimizing current tax liability |
| **Specific ID** | Trader selects which lots to sell | Maximum control, requires record-keeping |
| **Average Cost** | Weighted average of all held lots | Simplicity, required in some jurisdictions |

---

## 1. FIFO (First-In, First-Out)

Sell the oldest lots first. This is the default method in the US if no other method is elected.

```python
def fifo_sell(lots: list[dict], sell_qty: float, sell_price: float) -> list[dict]:
    """Sell using FIFO. lots sorted oldest-first."""
    remaining = sell_qty
    realized = []
    while remaining > 0 and lots:
        lot = lots[0]
        used = min(lot["qty"], remaining)
        gain = (sell_price - lot["cost_per_unit"]) * used
        realized.append({"qty": used, "basis": lot["cost_per_unit"], "gain": gain})
        lot["qty"] -= used
        remaining -= used
        if lot["qty"] <= 0:
            lots.pop(0)
    return realized
```

### Partial sell example

You hold three lots of TOKEN:
- Lot A: 100 units @ $1.00 (oldest)
- Lot B: 50 units @ $2.00
- Lot C: 75 units @ $1.50

You sell 120 units at $3.00:
- 100 from Lot A: gain = (3.00 - 1.00) * 100 = $200
- 20 from Lot B: gain = (3.00 - 2.00) * 20 = $20
- Total realized gain: **$220**
- Lot B remainder: 30 units @ $2.00

---

## 2. LIFO (Last-In, First-Out)

Sell the newest lots first. Reverses the order compared to FIFO.

```python
def lifo_sell(lots: list[dict], sell_qty: float, sell_price: float) -> list[dict]:
    """Sell using LIFO. Pops from end (newest first)."""
    remaining = sell_qty
    realized = []
    while remaining > 0 and lots:
        lot = lots[-1]
        used = min(lot["qty"], remaining)
        gain = (sell_price - lot["cost_per_unit"]) * used
        realized.append({"qty": used, "basis": lot["cost_per_unit"], "gain": gain})
        lot["qty"] -= used
        remaining -= used
        if lot["qty"] <= 0:
            lots.pop()
    return realized
```

Using the same lots and selling 120 at $3.00 with LIFO:
- 75 from Lot C: gain = (3.00 - 1.50) * 75 = $112.50
- 45 from Lot B: gain = (3.00 - 2.00) * 45 = $45
- Total realized gain: **$157.50**

---

## 3. HIFO (Highest-In, First-Out)

Sell the highest-cost lots first to minimize realized gains.

```python
def hifo_sell(lots: list[dict], sell_qty: float, sell_price: float) -> list[dict]:
    """Sell using HIFO. Sort by cost descending, consume highest first."""
    lots.sort(key=lambda x: x["cost_per_unit"], reverse=True)
    remaining = sell_qty
    realized = []
    for lot in lots:
        if remaining <= 0:
            break
        used = min(lot["qty"], remaining)
        gain = (sell_price - lot["cost_per_unit"]) * used
        realized.append({"qty": used, "basis": lot["cost_per_unit"], "gain": gain})
        lot["qty"] -= used
        remaining -= used
    lots[:] = [l for l in lots if l["qty"] > 0]
    return realized
```

Same lots, selling 120 at $3.00 with HIFO:
- 50 from Lot B ($2.00, highest): gain = (3.00 - 2.00) * 50 = $50
- 70 from Lot C ($1.50, next highest): gain = (3.00 - 1.50) * 70 = $105
- Total realized gain: **$155**
- Remaining: Lot A 100 @ $1.00, Lot C 5 @ $1.50

---

## 4. Specific Identification

The trader explicitly selects which lots to sell. Provides maximum control but requires meticulous record-keeping. Each lot must be uniquely identifiable (e.g., by purchase date and time, or a lot ID).

```python
def specific_id_sell(lots: dict[str, dict], lot_ids: list[tuple[str, float]],
                     sell_price: float) -> list[dict]:
    """Sell specific lots by ID. lot_ids = [(lot_id, qty_to_sell), ...]"""
    realized = []
    for lot_id, sell_qty in lot_ids:
        lot = lots[lot_id]
        used = min(lot["qty"], sell_qty)
        gain = (sell_price - lot["cost_per_unit"]) * used
        realized.append({"lot_id": lot_id, "qty": used, "basis": lot["cost_per_unit"], "gain": gain})
        lot["qty"] -= used
        if lot["qty"] <= 0:
            del lots[lot_id]
    return realized
```

---

## 5. Proportional / Average Cost Method

Compute a single weighted-average cost per unit across all held lots. Every sell uses that average cost. The average updates after each buy.

```python
def average_cost_basis(lots: list[dict]) -> float:
    """Compute weighted average cost per unit across all lots."""
    total_cost = sum(l["qty"] * l["cost_per_unit"] for l in lots)
    total_qty = sum(l["qty"] for l in lots)
    if total_qty == 0:
        return 0.0
    return total_cost / total_qty

def average_cost_sell(lots: list[dict], sell_qty: float, sell_price: float) -> dict:
    """Sell using average cost. Reduces all lots proportionally."""
    avg = average_cost_basis(lots)
    total_qty = sum(l["qty"] for l in lots)
    sell_qty = min(sell_qty, total_qty)
    gain = (sell_price - avg) * sell_qty
    # Reduce each lot proportionally
    ratio = sell_qty / total_qty
    for lot in lots:
        lot["qty"] *= (1 - ratio)
    lots[:] = [l for l in lots if l["qty"] > 1e-12]
    return {"qty": sell_qty, "avg_basis": avg, "gain": gain}
```

### Partial sell with average cost

Lots: 100 @ $1.00, 50 @ $2.00, 75 @ $1.50. Total: 225 units, total cost $312.50.

Average cost = $312.50 / 225 = **$1.3889/unit**

Sell 120 at $3.00: gain = (3.00 - 1.3889) * 120 = **$193.33**

After the sell, 105 units remain at the same $1.3889 average.

---

## 6. Special Events

### Airdrops

Airdrops are treated as income at fair market value (FMV) on the date received. The FMV becomes the cost basis for future sales.

```python
airdrop_lot = {
    "date": "2025-03-15",
    "qty": 1000,
    "cost_per_unit": 0.05,   # FMV at time of receipt
    "income_recognized": 50.0,  # 1000 * 0.05 reported as income
    "source": "airdrop"
}
```

### Staking Rewards

Staking rewards are income at FMV when received (similar to airdrops). Each reward event creates a new lot.

```python
staking_lot = {
    "date": "2025-04-01",
    "qty": 5.2,
    "cost_per_unit": 150.0,  # SOL price at receipt
    "income_recognized": 780.0,
    "source": "staking_reward"
}
```

### Token Splits and Migrations

A token split or migration (old token to new token 1:1 or N:M) is generally not a taxable event. The total cost basis transfers to the new tokens.

```python
def apply_split(lots: list[dict], split_ratio: float) -> None:
    """Apply a token split. split_ratio > 1 means more tokens."""
    for lot in lots:
        lot["qty"] *= split_ratio
        lot["cost_per_unit"] /= split_ratio
```

For a 1:10 split of 100 tokens @ $5.00: result is 1000 tokens @ $0.50. Total basis unchanged at $500.

---

## 7. LP Entry/Exit as Token Swaps

Entering an LP position is treated as selling the deposited tokens and receiving LP tokens. Exiting is the reverse.

**LP Entry** (deposit 10 SOL + 1500 USDC into SOL/USDC pool):
1. Dispose of 10 SOL at current FMV → capital gain/loss event
2. Dispose of 1500 USDC at current FMV → usually negligible gain/loss
3. Receive LP tokens with cost basis = FMV of deposited assets

**LP Exit** (redeem LP tokens for 12 SOL + 1400 USDC):
1. Dispose of LP tokens at FMV of received assets → capital gain/loss
2. Receive 12 SOL with cost basis = FMV at redemption
3. Receive 1400 USDC with cost basis = FMV at redemption

```python
def lp_entry(sol_qty: float, sol_price: float, usdc_qty: float,
             lp_tokens_received: float) -> dict:
    """Model LP entry as disposal of component tokens."""
    total_value = sol_qty * sol_price + usdc_qty * 1.0
    lp_cost_basis = total_value / lp_tokens_received
    return {
        "disposals": [
            {"token": "SOL", "qty": sol_qty, "price": sol_price},
            {"token": "USDC", "qty": usdc_qty, "price": 1.0},
        ],
        "lp_lot": {"qty": lp_tokens_received, "cost_per_unit": lp_cost_basis}
    }
```

---

## 8. Multi-Hop Swaps

A multi-hop swap (e.g., SOL -> USDC -> TOKEN) creates **multiple taxable events**, one for each intermediate step. Jupiter often routes through intermediate tokens.

```python
def multi_hop_events(hops: list[dict]) -> list[dict]:
    """
    Each hop is: {"sell_token", "sell_qty", "sell_price",
                  "buy_token", "buy_qty", "buy_price"}
    Each hop is a separate taxable event.
    """
    events = []
    for i, hop in enumerate(hops):
        events.append({
            "event": i + 1,
            "dispose": hop["sell_token"],
            "dispose_qty": hop["sell_qty"],
            "dispose_value": hop["sell_qty"] * hop["sell_price"],
            "acquire": hop["buy_token"],
            "acquire_qty": hop["buy_qty"],
            "acquire_basis": hop["buy_qty"] * hop["buy_price"],
        })
    return events
```

**Example**: Swap 1 SOL ($150) -> 150 USDC -> 10,000 TOKEN ($0.015 each)
- Event 1: Dispose 1 SOL (basis vs. $150 proceeds) → gain/loss on SOL
- Event 2: Dispose 150 USDC (basis vs. $150 proceeds) → usually ~$0 gain
- Result: 10,000 TOKEN with cost basis = $0.015/unit

---

## 9. Comparison View

The core value of this skill: run the same trade history through all five methods and compare total realized gain and estimated tax liability.

```python
methods = ["FIFO", "LIFO", "HIFO", "Specific ID", "Average Cost"]
# After processing all trades through each method:
comparison = {
    "FIFO":        {"total_gain": 220.00, "tax_at_30pct": 66.00},
    "LIFO":        {"total_gain": 157.50, "tax_at_30pct": 47.25},
    "HIFO":        {"total_gain": 155.00, "tax_at_30pct": 46.50},
    "Specific ID": {"total_gain": 160.00, "tax_at_30pct": 48.00},
    "Average Cost":{"total_gain": 193.33, "tax_at_30pct": 58.00},
}
# HIFO minimizes liability in this example
```

See `scripts/cost_basis_calculator.py` for a full runnable comparison with realistic trade data including partial sells.

---

## Quick Start

```python
from scripts.cost_basis_calculator import CostBasisEngine

engine = CostBasisEngine()

# Add purchases
engine.add_buy("2025-01-10", "TOKEN", 100, 1.00)
engine.add_buy("2025-02-15", "TOKEN", 50, 2.00)
engine.add_buy("2025-03-01", "TOKEN", 75, 1.50)

# Sell and compare methods
results = engine.sell_compare("2025-04-01", "TOKEN", 120, 3.00)
engine.print_comparison(results)
```

---

## Use Cases

1. **Tax season preparation**: Run your full year of trades through all methods before choosing one to report.
2. **Accumulation strategy**: Track partial sells during DCA accumulation, see how each method affects remaining basis.
3. **LP position tracking**: Model LP entry/exit as swaps and capture the associated gain/loss events.
4. **Airdrop and staking income**: Properly record income events and set cost basis for future disposals.
5. **Multi-hop swap decomposition**: Break down Jupiter routes into individual taxable events.

---

## Files

| File | Description |
|------|-------------|
| `references/planned_features.md` | Method formulas, partial sell worked examples, special event handling, multi-hop treatment |
| `scripts/cost_basis_calculator.py` | Full engine with all 5 methods, comparison table, demo mode with realistic trades |

---

> **Remember**: The "best" method depends on your jurisdiction, your specific trade history, and your tax situation. This engine helps you compare — a tax professional helps you decide.
