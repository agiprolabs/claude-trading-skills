---
name: tax-loss-harvesting
description: Tax-loss harvesting opportunity identification, scoring, and planning with wash sale compliance and annual carryforward tracking
license: MIT
metadata:
  author: agipro
  version: "0.1.0"
  category: trading
---

# Tax-Loss Harvesting

Identify, score, and plan tax-loss harvesting (TLH) opportunities across a crypto portfolio. This skill covers unrealized-loss ranking, net-benefit calculation, wash sale compliance, annual loss carryforward tracking, and year-end "use it or lose it" strategies.

> **Disclaimer:** This skill provides informational analysis only. It is NOT tax advice. Tax rules vary by jurisdiction and change frequently. Consult a qualified tax professional before making any tax-related trading decisions.

## How Tax-Loss Harvesting Works

Tax-loss harvesting is the practice of intentionally realizing investment losses to offset realized capital gains, thereby reducing your current-year tax liability.

### Core Mechanism

1. **Identify** positions with unrealized losses in your portfolio.
2. **Sell** those positions to realize the loss.
3. **Offset** realized gains with the harvested loss, reducing taxable income.
4. **Optionally re-enter** a similar (but not "substantially identical") position to maintain market exposure.

### Short-Term vs Long-Term

| Holding Period | Classification | Typical Tax Rate |
|---------------|---------------|-----------------|
| < 1 year | Short-term capital gain/loss | Ordinary income rate |
| >= 1 year | Long-term capital gain/loss | Preferential rate (0-20%) |

Short-term losses first offset short-term gains; long-term losses first offset long-term gains. Remaining net losses cross over to offset the other category.

### Annual Loss Deduction Limit

If total net losses exceed total gains, the excess is deductible against ordinary income up to **$3,000 per year** ($1,500 if married filing separately). Any remaining loss carries forward indefinitely to future tax years.

## Ranking Unrealized Losses

Not all unrealized losses are equally valuable to harvest. This skill scores each opportunity on four dimensions:

### 1. Loss Magnitude

Larger dollar losses provide more tax savings. The raw loss is the difference between current market value and cost basis.

```
unrealized_loss = current_value - cost_basis  # negative when loss
tax_savings = abs(unrealized_loss) * marginal_tax_rate
```

### 2. Days Until Long-Term Threshold

A position approaching the 1-year holding mark deserves special consideration:
- If close to crossing into long-term territory, harvesting now locks in a **short-term loss** (offsets higher-taxed short-term gains).
- If already long-term, the loss offsets long-term gains (lower tax rate benefit).

```
days_held = (today - acquisition_date).days
days_to_long_term = max(0, 365 - days_held)
```

Positions with fewer days remaining until long-term are **more urgent** to evaluate because once they cross 365 days, a short-term loss becomes a less-valuable long-term loss.

### 3. Wash Sale Risk (Correlation Score)

The IRS wash sale rule prohibits claiming a loss if you buy a "substantially identical" security within 30 days before or after the sale. In crypto, the exact application is evolving, but prudent planning avoids re-entering the same token within the 61-day wash sale window (30 days before + sale day + 30 days after).

**Correlation scoring**: If you hold (or plan to re-enter) a position that is highly correlated with the harvested asset, wash sale risk increases. Score this as:

```
wash_sale_risk = 1.0  # if same token re-entry planned within 30 days
wash_sale_risk = correlation_coefficient  # if correlated substitute held
wash_sale_risk = 0.0  # if no re-entry or uncorrelated substitute
```

Higher wash sale risk reduces the effective score of the opportunity.

### 4. Available Gains to Offset

A harvested loss is only immediately useful if there are realized gains to offset. Score opportunities higher when:
- There are matching-type gains (short-term loss vs short-term gain).
- The loss amount does not greatly exceed available gains (diminishing marginal benefit beyond the $3K deduction cap).

```
offset_efficiency = min(1.0, available_matching_gains / abs(unrealized_loss))
```

### Composite Score

```python
def tlh_score(
    unrealized_loss: float,
    days_to_long_term: int,
    wash_sale_risk: float,
    offset_efficiency: float,
    weights: dict | None = None,
) -> float:
    w = weights or {
        "magnitude": 0.35,
        "urgency": 0.25,
        "wash_safety": 0.20,
        "offset_match": 0.20,
    }
    magnitude_score = min(abs(unrealized_loss) / 10_000, 1.0)
    urgency_score = max(0, 1.0 - days_to_long_term / 365)
    wash_safety_score = 1.0 - wash_sale_risk
    return (
        w["magnitude"] * magnitude_score
        + w["urgency"] * urgency_score
        + w["wash_safety"] * wash_safety_score
        + w["offset_match"] * offset_efficiency
    )
```

## Net Benefit Calculation

Harvesting a loss is not free. Transaction costs (swap fees, slippage, gas) reduce the benefit.

```python
def net_benefit(
    unrealized_loss: float,
    marginal_tax_rate: float,
    transaction_cost: float,
    re_entry_cost: float = 0.0,
) -> float:
    """Compute net dollar benefit of harvesting a loss.

    Args:
        unrealized_loss: Negative number representing the loss.
        marginal_tax_rate: Applicable tax rate (0.0 to 1.0).
        transaction_cost: Cost to execute the sell (fees + slippage).
        re_entry_cost: Cost to re-enter a substitute position.

    Returns:
        Net benefit in dollars. Positive means harvesting is worthwhile.
    """
    tax_savings = abs(unrealized_loss) * marginal_tax_rate
    total_costs = transaction_cost + re_entry_cost
    return tax_savings - total_costs
```

**Rule of thumb**: Only harvest when `net_benefit > 0` by a meaningful margin. Very small losses are not worth the transaction costs and operational complexity.

## Year-End "Use It or Lose It"

Near December 31, evaluate whether to accelerate harvesting:

1. **Tally year-to-date realized gains** (both short-term and long-term).
2. **Identify unrealized losses** that can offset those gains.
3. **Prioritize** losses that offset same-type gains (short-term loss vs short-term gain yields the highest tax rate differential).
4. **Check the $3K excess limit**: If net losses already exceed gains by $3K, additional harvesting this year has no immediate tax benefit (though the carryforward still has value).
5. **Consider settlement timing**: Ensure trades settle before year-end.

## Wash Sale Compliance

### The 61-Day Window

The wash sale rule applies to purchases of substantially identical securities within:
- **30 days before** the sale (retroactive wash sale)
- **The day of** the sale
- **30 days after** the sale

If triggered, the disallowed loss is added to the cost basis of the replacement shares, deferring (not eliminating) the tax benefit.

### Compliance Strategies

| Strategy | Description | Trade-off |
|----------|------------|-----------|
| **Wait 31 days** | Sell, wait 31 days, re-buy | Market exposure gap |
| **Substitute asset** | Sell, immediately buy a non-identical but correlated asset | Tracking error |
| **No re-entry** | Sell and stay out | Lost upside |
| **Double-up** | Buy additional shares, wait 31 days, sell original lot | Capital intensive |

### Crypto-Specific Considerations

- The IRS has not explicitly ruled that the wash sale rule applies to cryptocurrency (as of 2025). However, proposed legislation may extend it.
- Prudent practitioners treat crypto as subject to wash sale rules for conservative planning.
- Different tokens (e.g., SOL vs ETH) are generally considered non-identical.
- Wrapped versions of the same token (e.g., SOL vs wSOL) may be considered substantially identical.

## Annual Loss Carryforward Tracking

```python
def compute_carryforward(
    realized_gains_st: float,
    realized_gains_lt: float,
    realized_losses_st: float,
    realized_losses_lt: float,
    prior_carryforward: float = 0.0,
    annual_deduction_limit: float = 3_000.0,
) -> dict:
    """Compute net tax position and carryforward.

    Returns dict with keys:
        net_st, net_lt, total_net,
        deduction_used, carryforward
    """
    net_st = realized_gains_st + realized_losses_st  # losses are negative
    net_lt = realized_gains_lt + realized_losses_lt
    total_net = net_st + net_lt - prior_carryforward

    if total_net >= 0:
        return {
            "net_st": net_st, "net_lt": net_lt,
            "total_net": total_net, "deduction_used": 0.0,
            "carryforward": 0.0,
        }

    excess_loss = abs(total_net)
    deduction_used = min(excess_loss, annual_deduction_limit)
    carryforward = max(0, excess_loss - annual_deduction_limit)
    return {
        "net_st": net_st, "net_lt": net_lt,
        "total_net": total_net,
        "deduction_used": deduction_used,
        "carryforward": carryforward,
    }
```

## Prerequisites

- Python 3.10+
- No external dependencies for core calculations
- Portfolio data: cost basis, acquisition date, current market value per lot
- Tax parameters: marginal tax rate, filing status, prior carryforward

## Capabilities

| Capability | Description |
|-----------|-------------|
| Opportunity scanning | Identify all positions with unrealized losses |
| Multi-factor scoring | Rank by magnitude, urgency, wash safety, offset match |
| Net benefit analysis | Compare tax savings against transaction costs |
| Wash sale tracking | Flag positions within the 61-day window |
| Carryforward calculator | Track annual $3K limit and loss carryforward |
| Year-end planning | Prioritize harvesting before December 31 |
| Harvesting plan output | Generate actionable plan with sell orders and re-entry dates |

## Quick Start

```python
from datetime import date

# Define a portfolio position
position = {
    "symbol": "TOKEN-A",
    "cost_basis": 10_000.0,
    "current_value": 6_500.0,
    "acquisition_date": date(2025, 8, 15),
    "quantity": 500.0,
}

unrealized_loss = position["current_value"] - position["cost_basis"]  # -3500
days_held = (date.today() - position["acquisition_date"]).days
days_to_lt = max(0, 365 - days_held)

# Score the opportunity
score = tlh_score(
    unrealized_loss=unrealized_loss,
    days_to_long_term=days_to_lt,
    wash_sale_risk=0.0,
    offset_efficiency=0.8,
)
print(f"TLH score: {score:.3f}")

# Calculate net benefit
benefit = net_benefit(
    unrealized_loss=unrealized_loss,
    marginal_tax_rate=0.35,
    transaction_cost=15.0,
    re_entry_cost=15.0,
)
print(f"Net benefit: ${benefit:.2f}")
```

## Use Cases

1. **Quarterly portfolio review**: Scan all positions for harvesting opportunities ranked by composite score.
2. **Year-end tax planning**: Identify optimal set of positions to harvest before December 31 given year-to-date gain/loss totals.
3. **Ongoing monitoring**: Flag positions that are approaching the long-term threshold where harvesting a short-term loss becomes urgent.
4. **Carryforward management**: Track multi-year loss carryforward balances and project when they will be fully utilized.
5. **Transaction cost analysis**: Determine minimum loss threshold worth harvesting given current fee environment.

## Files

| File | Description |
|------|-------------|
| `references/planned_features.md` | TLH mechanics, scoring formula, wash sale interaction, carryforward rules, year-end strategies |
| `scripts/harvest_scanner.py` | Demo scanner: score opportunities, generate harvesting plan, compute net benefit |

> **Important:** This skill provides analytical tools for informational purposes only. All tax-related decisions should be reviewed by a qualified tax professional. Tax laws vary by jurisdiction and are subject to change.
