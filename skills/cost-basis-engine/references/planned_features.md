# Cost Basis Engine — Method Reference

## 1. Method Formulas

### 1.1 FIFO (First-In, First-Out)

Lots are ordered by acquisition date ascending. On each sell, consume from the oldest lot first.

```
lots = sorted(lots, key=acquisition_date, ascending=True)
for each sell event (qty_sell, price_sell):
    remaining = qty_sell
    while remaining > 0:
        lot = lots[0]  # oldest
        used = min(lot.qty, remaining)
        realized_gain += (price_sell - lot.cost_per_unit) * used
        lot.qty -= used
        remaining -= used
        if lot.qty == 0: remove lot
```

### 1.2 LIFO (Last-In, First-Out)

Lots ordered by acquisition date descending. On each sell, consume from the newest lot first.

```
lots = sorted(lots, key=acquisition_date, descending=True)
# Same consumption loop as FIFO but starting from newest
```

### 1.3 HIFO (Highest-In, First-Out)

Lots ordered by cost per unit descending. On each sell, consume the highest-cost lot first. This minimizes realized gain (or maximizes realized loss).

```
lots = sorted(lots, key=cost_per_unit, descending=True)
# Same consumption loop, starting from highest cost
```

### 1.4 Specific Identification

Trader explicitly designates which lots to sell. Each lot requires a unique identifier (typically acquisition date + time or a sequential ID). The trader must make the designation at the time of sale and maintain records.

```
for each (lot_id, qty_to_sell) in designation:
    lot = lookup(lot_id)
    gain = (sell_price - lot.cost_per_unit) * qty_to_sell
    lot.qty -= qty_to_sell
```

### 1.5 Average Cost (Proportional)

Maintain a running weighted average cost. All units are fungible at the average cost.

```
avg_cost = sum(lot.qty * lot.cost_per_unit for lot in lots) / sum(lot.qty for lot in lots)

On sell of qty_sell at price_sell:
    gain = (price_sell - avg_cost) * qty_sell
    total_qty -= qty_sell
    # avg_cost remains unchanged until next buy

On buy of qty_buy at price_buy:
    new_total_cost = avg_cost * old_qty + price_buy * qty_buy
    new_total_qty = old_qty + qty_buy
    avg_cost = new_total_cost / new_total_qty
```

---

## 2. Partial Sell Worked Examples

Starting position for all examples:

| Lot | Date | Qty | Cost/Unit | Total Cost |
|-----|------|-----|-----------|------------|
| A | 2025-01-10 | 100 | $1.00 | $100.00 |
| B | 2025-02-15 | 50 | $2.00 | $100.00 |
| C | 2025-03-01 | 75 | $1.50 | $112.50 |

**Total**: 225 units, $312.50 total cost, $1.3889 average cost.

**Sell event**: 120 units at $3.00 on 2025-04-01. Proceeds = $360.00.

### 2.1 FIFO Partial Sell

1. Consume Lot A entirely: 100 units. Gain = (3.00 - 1.00) * 100 = **$200.00**
2. Consume 20 from Lot B: Gain = (3.00 - 2.00) * 20 = **$20.00**

| Result | Value |
|--------|-------|
| Total gain | $220.00 |
| Lots remaining | B: 30 @ $2.00, C: 75 @ $1.50 |
| Remaining basis | $172.50 |

### 2.2 LIFO Partial Sell

1. Consume Lot C entirely: 75 units. Gain = (3.00 - 1.50) * 75 = **$112.50**
2. Consume 45 from Lot B: Gain = (3.00 - 2.00) * 45 = **$45.00**

| Result | Value |
|--------|-------|
| Total gain | $157.50 |
| Lots remaining | A: 100 @ $1.00, B: 5 @ $2.00 |
| Remaining basis | $110.00 |

### 2.3 HIFO Partial Sell

Sorted by cost: B ($2.00) > C ($1.50) > A ($1.00).

1. Consume Lot B entirely: 50 units. Gain = (3.00 - 2.00) * 50 = **$50.00**
2. Consume 70 from Lot C: Gain = (3.00 - 1.50) * 70 = **$105.00**

| Result | Value |
|--------|-------|
| Total gain | $155.00 |
| Lots remaining | A: 100 @ $1.00, C: 5 @ $1.50 |
| Remaining basis | $107.50 |

### 2.4 Average Cost Partial Sell

Average cost = $312.50 / 225 = $1.3889.

Gain = (3.00 - 1.3889) * 120 = **$193.33**

| Result | Value |
|--------|-------|
| Total gain | $193.33 |
| Remaining qty | 105 units |
| Remaining avg cost | $1.3889 (unchanged) |
| Remaining basis | $145.83 |

### 2.5 Method Comparison Summary

| Method | Realized Gain | Tax @ 30% | Remaining Basis |
|--------|--------------|-----------|-----------------|
| FIFO | $220.00 | $66.00 | $172.50 |
| LIFO | $157.50 | $47.25 | $110.00 |
| HIFO | $155.00 | $46.50 | $107.50 |
| Average | $193.33 | $58.00 | $145.83 |

HIFO minimizes current tax liability. Note that remaining basis is also lowest under HIFO, meaning future sells will have higher gains — HIFO defers tax, it does not eliminate it.

---

## 3. Special Event Handling

### 3.1 Airdrops

- **Tax treatment**: Income at FMV on date of receipt.
- **Cost basis**: FMV at receipt becomes the cost basis for the new lot.
- **Formula**: `income = qty_received * fmv_at_receipt`
- If FMV is zero or indeterminate at receipt, cost basis is $0 and the full proceeds on any future sale are gain.

### 3.2 Staking Rewards

- **Tax treatment**: Income at FMV when the reward is received (i.e., when the tokens become available for withdrawal or transfer).
- **Cost basis**: Same as airdrops — FMV at receipt.
- **Frequency**: Each staking reward event creates a separate lot. For validators receiving rewards every epoch, this can mean hundreds of micro-lots per year.
- **Practical simplification**: Batch rewards by day or week, using the average price over the period.

### 3.3 Token Splits and Migrations

- **Tax treatment**: Generally not a taxable event (analogous to stock splits).
- **Cost basis**: Total basis is preserved; per-unit basis adjusts inversely to the split ratio.
- **Formula for N:M split**:
  ```
  new_qty = old_qty * (M / N)
  new_cost_per_unit = old_cost_per_unit * (N / M)
  total_basis = unchanged
  ```
- **Migration (1:1 swap to new token contract)**: Same treatment. Old token lots transfer directly to new token with identical basis and acquisition dates.

### 3.4 Hard Forks

- If a fork produces a new token with value, the IRS (US) position is that the new token has a cost basis of $0 and FMV at receipt is income. Treatment varies by jurisdiction.

---

## 4. LP Entry/Exit Treatment

### 4.1 LP Entry (Deposit)

Depositing tokens into an LP is treated as a disposal of the component tokens:

1. **Dispose Token A**: qty_a at FMV → realize gain/loss vs. existing basis
2. **Dispose Token B**: qty_b at FMV → realize gain/loss vs. existing basis
3. **Receive LP tokens**: cost basis = total FMV of deposited assets

```
lp_basis = (qty_a * price_a) + (qty_b * price_b)
lp_cost_per_token = lp_basis / lp_tokens_received
```

### 4.2 LP Exit (Withdrawal)

Redeeming LP tokens is treated as disposing the LP tokens and acquiring the component tokens:

1. **Dispose LP tokens**: at FMV of received assets → realize gain/loss vs. LP basis
2. **Receive Token A**: cost basis = FMV at redemption
3. **Receive Token B**: cost basis = FMV at redemption

```
redemption_value = (qty_a_out * price_a) + (qty_b_out * price_b)
lp_gain = redemption_value - (lp_tokens_redeemed * lp_cost_per_token)
```

### 4.3 Impermanent Loss Note

Impermanent loss is embedded in the LP gain/loss calculation. It is not a separate tax event — it shows up as a lower redemption value compared to holding the original tokens.

---

## 5. Multi-Hop Swap Treatment

### 5.1 Why It Matters

DEX aggregators like Jupiter route swaps through intermediate tokens for best pricing. A swap SOL -> TOKEN might actually execute as SOL -> USDC -> TOKEN. Each intermediate swap is a separate taxable event.

### 5.2 Event Decomposition

**Example**: Swap 1 SOL ($150) -> USDC -> TOKEN

| Event | Dispose | Qty | Proceeds | Acquire | Qty | Basis |
|-------|---------|-----|----------|---------|-----|-------|
| 1 | SOL | 1 | $150.00 | USDC | 150 | $150.00 |
| 2 | USDC | 150 | $150.00 | TOKEN | 10,000 | $150.00 |

- Event 1: Gain/loss on SOL depends on your SOL cost basis
- Event 2: USDC gain/loss is typically negligible ($0 if basis = $1.00)
- Final: 10,000 TOKEN with basis $0.015/unit

### 5.3 Practical Concern

Multi-hop routes can create unexpected tax events even when the trader intended a single swap. A 3-hop route creates 3 taxable events. When fetching swap transaction details from Jupiter or on-chain, decompose the full route to capture all intermediate disposals.

### 5.4 Stablecoin Intermediaries

When USDC or USDT is the intermediate token, the gain/loss on the stablecoin leg is usually near zero. However, if stablecoins were acquired at a price other than $1.00 (e.g., during a depeg), there may be a non-trivial gain or loss on that leg.

---

## 6. Holding Period Considerations

- **Short-term**: Held <= 1 year. Taxed at ordinary income rates in many jurisdictions.
- **Long-term**: Held > 1 year. Often taxed at reduced capital gains rates.
- FIFO tends to produce more long-term gains (oldest lots first).
- LIFO and HIFO tend to produce more short-term gains (newer or recently-priced lots first).
- The holding period analysis adds another dimension to method comparison beyond just realized gain amounts.

---

## 7. Record-Keeping Requirements

For specific identification, the trader must:
1. Identify the specific lot at the time of sale (not retroactively)
2. Maintain records showing which lots were designated
3. Receive confirmation from the exchange/platform (where applicable)

For all methods, maintain:
- Date and time of every acquisition and disposal
- Quantity and price for each transaction
- Fee amounts (fees adjust basis or proceeds)
- Source of acquisition (purchase, airdrop, staking, LP redemption)
