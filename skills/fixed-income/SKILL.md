---
name: fixed-income
description: "[STUB] Bond pricing, yield curves, duration and convexity analysis, and DeFi lending rate modeling"
---

# Fixed Income

> **Status: STUB** — This skill provides a basic bond calculator and an overview of planned capabilities. Full implementation is awaiting community contribution.

Fixed income analysis bridges traditional bond mathematics with DeFi lending rate modeling. Bond pricing fundamentals — present value of cash flows, yield curves, duration, and convexity — translate directly to analyzing DeFi lending protocols where depositors earn variable or fixed rates on crypto assets.

On Solana, lending protocols like Marginfi, Kamino, and Solend offer variable-rate lending/borrowing. Understanding term structure and rate dynamics helps optimize yield farming strategies and compare opportunities across protocols.

This skill is informational and analytical only. It does not provide financial advice or trading recommendations.

---

## Current Capabilities

This stub includes a working bond calculator with price, yield-to-maturity, duration, and convexity computations. See `scripts/bond_calculator.py` for the implementation.

```python
def bond_price(
    face: float, coupon_rate: float, ytm: float, periods: int, freq: int = 2
) -> float:
    """Calculate bond price as present value of all cash flows.

    Args:
        face: Face (par) value of the bond.
        coupon_rate: Annual coupon rate (decimal, e.g., 0.05 for 5%).
        ytm: Yield to maturity (annual, decimal).
        periods: Number of coupon periods remaining.
        freq: Coupon frequency per year (2 = semi-annual).

    Returns:
        Bond price (dirty price).
    """
    coupon = face * coupon_rate / freq
    y = ytm / freq
    pv_coupons = sum(coupon / (1 + y) ** t for t in range(1, periods + 1))
    pv_face = face / (1 + y) ** periods
    return pv_coupons + pv_face
```

Run the demo:

```bash
python scripts/bond_calculator.py --demo
```

---

## Planned Capabilities

When fully implemented, this skill will cover:

### Bond Pricing

| Concept | Description |
|---------|-------------|
| Clean/Dirty Price | Price excluding/including accrued interest |
| Accrued Interest | Interest earned since last coupon date |
| Day Count Conventions | 30/360, ACT/360, ACT/365, ACT/ACT |
| Zero-Coupon Bonds | Discount bonds with no periodic coupons |

### Yield Measures

| Yield Measure | Use Case |
|---------------|----------|
| Yield to Maturity (YTM) | Total return if held to maturity |
| Current Yield | Annual coupon / price |
| Yield to Call | Return if called at first call date |
| Spread to Benchmark | Credit risk premium over risk-free rate |

### Duration and Convexity

| Metric | Measures |
|--------|----------|
| Macaulay Duration | Weighted average time to cash flows |
| Modified Duration | Price sensitivity to yield changes |
| Effective Duration | Duration for bonds with embedded options |
| Convexity | Second-order price sensitivity |
| Dollar Duration (DV01) | Dollar change per 1bp yield move |

### Yield Curve Construction

| Method | Description |
|--------|-------------|
| Bootstrap | Extract spot rates from par bond prices |
| Nelson-Siegel | Parametric model with level, slope, curvature |
| Nelson-Siegel-Svensson | Extended model with additional curvature term |
| Cubic Spline | Non-parametric interpolation |

### DeFi Lending Rate Analysis

| Protocol | Chain | Type |
|----------|-------|------|
| Marginfi | Solana | Variable rate |
| Kamino | Solana | Variable rate |
| Solend | Solana | Variable rate |
| Aave | Ethereum/Multi | Variable + stable rate |
| Compound | Ethereum | Variable rate |

Planned DeFi features:
- Lending rate time series analysis
- Supply/borrow APY comparison across protocols
- Utilization rate impact on lending rates
- Fixed vs variable rate comparison (when fixed-rate protocols available)
- Rate arbitrage opportunity detection

---

## Prerequisites

```bash
# For full implementation
uv pip install numpy scipy

# For visualization
uv pip install matplotlib
```

The included `scripts/bond_calculator.py` uses only the Python standard library and runs without any dependencies.

---

## Use Cases

### Yield Farming Comparison
Compare DeFi lending rates across protocols using fixed income analytics. Annualize variable rates, compute effective yields accounting for compounding frequency, and identify the most capital-efficient opportunities.

### Lending Rate Analysis
Track lending rates over time to understand rate dynamics. Identify periods of rate compression (low utilization) vs rate expansion (high utilization) to time deposits optimally.

### Rate Arbitrage
Borrow at lower rates on one protocol and lend at higher rates on another. Duration and convexity concepts help assess the risk of rate changes during the arbitrage holding period.

### Risk Assessment
Use duration to estimate how lending positions change in value as rates move. Higher duration means greater sensitivity to rate changes.

---

## Quick Reference: Bond Pricing Formulas

**Bond price (present value of cash flows):**
```
P = Σ [C / (1+y)^t] + F / (1+y)^n
    t=1..n

Where:
  C = periodic coupon payment = Face * coupon_rate / frequency
  y = periodic yield = YTM / frequency
  F = face value
  n = total number of periods
```

**Macaulay Duration:**
```
D_mac = (1/P) * Σ [t * C / (1+y)^t] + (n * F) / ((1+y)^n * P)
```

**Modified Duration:**
```
D_mod = D_mac / (1 + y)
```

**Convexity:**
```
Convexity = (1/P) * Σ [t*(t+1) * C / (1+y)^(t+2)] + [n*(n+1)*F] / [(1+y)^(n+2) * P]
```

**Price change approximation:**
```
ΔP/P ≈ -D_mod * Δy + 0.5 * Convexity * (Δy)²
```

---

## Files

| File | Description |
|------|-------------|
| `references/planned_features.md` | Planned features, bond formulas, DeFi protocols, and implementation priorities |
| `scripts/bond_calculator.py` | Bond price, YTM, duration, and convexity calculator |

---

## Contributing

This skill is a stub awaiting full implementation. To contribute:

1. Implement yield curve bootstrapping from market data
2. Add Nelson-Siegel yield curve fitting
3. Build DeFi lending rate data fetcher (Marginfi, Kamino APIs)
4. Add day count convention support for accurate accrued interest
5. Create rate comparison dashboard across protocols

See `references/planned_features.md` for the full feature list and implementation priorities.

---

*This skill provides analytical tools and mathematical models for informational purposes only. It does not constitute financial advice. Fixed income and DeFi lending involve risk of loss.*
