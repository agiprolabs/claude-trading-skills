# Fixed Income — Planned Features

> **Status: STUB** — This document outlines the planned feature set for the fixed-income skill.

---

## 1. Bond Pricing (Implemented in stub)

### Present Value of Cash Flows

The fundamental bond pricing equation:

```
P = Σ [C / (1+y)^t] + F / (1+y)^n
    t=1..n

Where:
  P = bond price (dirty price)
  C = periodic coupon = Face * annual_coupon_rate / frequency
  y = periodic yield = YTM / frequency
  F = face (par) value
  n = total coupon periods remaining
```

### Clean vs Dirty Price

```
Clean Price = Dirty Price - Accrued Interest
Accrued Interest = C * (days since last coupon / days in coupon period)
```

Day count conventions affect accrued interest calculation:
- **30/360**: Assumes 30-day months, 360-day year
- **ACT/360**: Actual days elapsed, 360-day year
- **ACT/365**: Actual days elapsed, 365-day year
- **ACT/ACT**: Actual days in both numerator and denominator

Priority: Day count conventions are **Medium** priority for stub expansion.

---

## 2. Yield Measures

### Yield to Maturity (Implemented — Newton's method solver)

YTM is the discount rate that equates the bond price to the present value of all future cash flows. Solved numerically since no closed-form solution exists for coupon bonds.

### Current Yield (Implemented)

```
Current Yield = Annual Coupon / Clean Price
```

Simple but ignores time value and capital gains/losses.

### Yield to Call (Planned)

For callable bonds, replace maturity with call date and face value with call price:

```
P = Σ [C / (1+y)^t] + Call_Price / (1+y)^n_call
```

### Spread Measures (Planned)

| Spread | Definition |
|--------|-----------|
| Nominal Spread | YTM - Treasury YTM at same maturity |
| Z-Spread | Constant spread over zero curve |
| OAS | Spread over zero curve, adjusting for optionality |

Priority: **Low** for crypto context (no active crypto bond market yet).

---

## 3. Duration and Convexity (Implemented in stub)

### Macaulay Duration

Weighted average time to receive cash flows:

```
D_mac = (1/P) * [Σ t*C/(1+y)^t + n*F/(1+y)^n]
```

Interpretation: A bond with Macaulay duration of 5.2 years behaves like a zero-coupon bond maturing in 5.2 years.

### Modified Duration

Price sensitivity per unit yield change:

```
D_mod = D_mac / (1 + y/freq)

ΔP/P ≈ -D_mod * Δy
```

A modified duration of 4.8 means a 1% yield increase causes approximately a 4.8% price decline.

### Convexity

Second-order price sensitivity (curvature):

```
Convexity = (1/P) * Σ [t*(t+1)*CF_t / (1+y)^(t+2)]

ΔP/P ≈ -D_mod * Δy + 0.5 * Convexity * (Δy)²
```

Convexity improves the duration approximation for large yield changes.

### DV01 / Dollar Duration

Dollar value of a basis point:

```
DV01 = D_mod * P * 0.0001
```

Priority: All duration/convexity measures are **implemented** in the stub calculator.

---

## 4. Yield Curve Construction (Planned)

### Bootstrap Method

Extract spot (zero) rates from par bond prices sequentially:

1. Start with the shortest maturity bond to get the first spot rate
2. Use known spot rates to solve for the next spot rate
3. Repeat until the full curve is constructed

```
For a 2-period bond:
P = C/(1+z1) + (C+F)/(1+z2)^2
Solve for z2 given known z1
```

### Nelson-Siegel Model

Parametric yield curve with three factors:

```
y(τ) = β0 + β1 * [(1-e^(-τ/λ)) / (τ/λ)]
         + β2 * [(1-e^(-τ/λ)) / (τ/λ) - e^(-τ/λ)]

Where:
  β0 = long-term rate level
  β1 = slope (short-term component)
  β2 = curvature (medium-term hump)
  λ  = decay factor
  τ  = time to maturity
```

### Nelson-Siegel-Svensson Extension

Adds a second curvature term for more flexibility:

```
y(τ) = Nelson-Siegel + β3 * [(1-e^(-τ/λ2)) / (τ/λ2) - e^(-τ/λ2)]
```

Priority: **High** — yield curve construction is fundamental for rate analysis.

---

## 5. DeFi Lending Protocols on Solana

### Marginfi

- Variable-rate lending/borrowing
- Utilization-based rate model
- API: On-chain program data via Solana RPC
- Key metric: Supply APY, borrow APY, utilization rate

### Kamino

- Automated lending vaults
- Concentrated liquidity integration
- API: REST API + on-chain data
- Key metric: Vault APY, leverage ratio

### Solend

- Pool-based lending
- Multiple isolated pools by risk tier
- API: REST API at `api.solend.fi`
- Key metric: Pool APY, reserve utilization

### Cross-Protocol Analysis (Planned)

- Rate comparison dashboard
- Historical rate time series
- Utilization-to-rate curve fitting
- Optimal deposit allocation across protocols
- Rate arbitrage detection (borrow low, lend high)

### Rate Model Mathematics

Most DeFi protocols use a kinked utilization model:

```
If utilization ≤ optimal:
  borrow_rate = base_rate + (utilization / optimal) * slope1

If utilization > optimal:
  borrow_rate = base_rate + slope1 + ((utilization - optimal) / (1 - optimal)) * slope2

supply_rate = borrow_rate * utilization * (1 - reserve_factor)
```

Priority: **High** — DeFi lending rate analysis is the primary crypto use case.

---

## 6. Implementation Priorities

| Priority | Feature | Complexity | Dependencies |
|----------|---------|-----------|-------------|
| 1 (Done) | Bond price calculator | Low | math stdlib |
| 2 (Done) | YTM solver | Low | math stdlib |
| 3 (Done) | Duration & convexity | Low | math stdlib |
| 4 | Day count conventions | Low | datetime |
| 5 | Yield curve bootstrap | Medium | numpy |
| 6 | Nelson-Siegel fitting | Medium | scipy |
| 7 | DeFi rate data fetcher | Medium | httpx |
| 8 | Rate comparison tool | Medium | httpx, pandas |
| 9 | Rate model curve fitting | Medium | scipy |
| 10 | Fixed vs variable analysis | High | numpy, scipy |

---

## 7. Crypto-Specific Considerations

- **No standard maturities:** DeFi lending is mostly variable rate with no fixed term
- **Continuous compounding:** Many protocols compound per block or per slot
- **Utilization-driven rates:** Rates change with pool utilization, unlike fixed coupon bonds
- **Smart contract risk:** Lending rate analysis must account for protocol risk premium
- **Cross-chain rates:** Same protocol may offer different rates on different chains
- **Token incentives:** Effective yield includes token rewards (emissions) on top of base APY

---

*This document is for informational and planning purposes only. It does not constitute financial advice.*
