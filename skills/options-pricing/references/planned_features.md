# Options Pricing — Planned Features

> **Status: STUB** — This document outlines the planned feature set for the options-pricing skill.

---

## 1. Pricing Models

### Black-Scholes-Merton (Implemented in stub)

The foundational closed-form solution for European option pricing.

**Call price:**
```
C = S * N(d1) - K * e^(-rT) * N(d2)
```

**Put price:**
```
P = K * e^(-rT) * N(-d2) - S * N(-d1)
```

**Where:**
```
d1 = [ln(S/K) + (r + σ²/2) * T] / (σ * √T)
d2 = d1 - σ * √T
N(x) = standard normal CDF
```

**Assumptions:** Constant volatility, no dividends, continuous trading, log-normal returns, no transaction costs.

### Binomial Tree (Planned)

Cox-Ross-Rubinstein model for American options with early exercise.

```
u = e^(σ√Δt)          # up factor
d = 1/u                # down factor
p = (e^(rΔt) - d) / (u - d)  # risk-neutral probability
```

Backward induction with early exercise check at each node. Priority: **High** — needed for American-style crypto options.

### Monte Carlo Simulation (Planned)

For path-dependent and exotic options.

```
S(t+dt) = S(t) * exp((r - σ²/2)*dt + σ*√dt*Z)
where Z ~ N(0,1)
```

Variance reduction techniques: antithetic variates, control variates. Priority: **Medium**.

### Black-76 (Planned)

For futures options (relevant to crypto perpetual futures options).

```
C = e^(-rT) * [F*N(d1) - K*N(d2)]
d1 = [ln(F/K) + (σ²/2)*T] / (σ√T)
```

Priority: **Medium** — useful for Deribit futures options.

---

## 2. Greeks Formulas

All Greeks are implemented in the stub `scripts/black_scholes.py`.

| Greek | Call Formula | Put Formula |
|-------|------------|------------|
| Delta | N(d1) | N(d1) - 1 |
| Gamma | n(d1) / (S * σ * √T) | Same as call |
| Theta | -(S*n(d1)*σ)/(2√T) - r*K*e^(-rT)*N(d2) | -(S*n(d1)*σ)/(2√T) + r*K*e^(-rT)*N(-d2) |
| Vega | S * n(d1) * √T | Same as call |
| Rho | K*T*e^(-rT)*N(d2) | -K*T*e^(-rT)*N(-d2) |

Where n(x) is the standard normal PDF.

---

## 3. Implied Volatility

### Solvers (Stub includes bisection method)

| Method | Convergence | Robustness |
|--------|------------|------------|
| Bisection | Slow (linear) | Very robust |
| Newton-Raphson | Fast (quadratic) | Needs good initial guess |
| Brent's method | Fast | Robust, recommended |
| Jaeckel (2015) | Very fast | Industry standard |

### IV Surface Construction (Planned)

- Collect IV across strikes and expirations
- Interpolate using SVI (Stochastic Volatility Inspired) parameterization
- Detect skew, smile, and term structure patterns
- Arbitrage-free surface validation

Priority: **High** — critical for volatility trading.

---

## 4. Crypto Options Data Sources

### Deribit API

- **Base URL:** `https://www.deribit.com/api/v2/`
- **Auth:** API key + secret (public endpoints available without auth)
- **Key endpoints:**
  - `public/get_instruments` — list available options
  - `public/get_order_book` — bid/ask for an option
  - `public/ticker` — mark price, IV, Greeks
  - `public/get_book_summary_by_currency` — all options for BTC/ETH
- **Rate limits:** 20 requests/second (non-matching), 5/second (matching)
- **Assets:** BTC, ETH options (European, cash-settled)

### Lyra API

- On-chain options protocol on Optimism/Arbitrum
- Subgraph queries for historical data
- SDK for pricing and Greeks

### Zeta Markets (Solana)

- Solana-native options and futures
- Program ID-based on-chain data
- Limited API, primarily on-chain interaction

---

## 5. Implementation Priorities

| Priority | Feature | Complexity | Dependencies |
|----------|---------|-----------|-------------|
| 1 (Done) | Black-Scholes pricing | Low | math stdlib |
| 2 (Done) | Greeks computation | Low | math stdlib |
| 3 (Done) | Bisection IV solver | Low | math stdlib |
| 4 | Newton-Raphson IV solver | Low | scipy |
| 5 | Binomial tree pricing | Medium | numpy |
| 6 | Deribit API integration | Medium | httpx |
| 7 | IV surface construction | High | numpy, scipy |
| 8 | Monte Carlo simulation | Medium | numpy |
| 9 | Portfolio Greeks aggregation | Medium | numpy |
| 10 | Strategy payoff diagrams | Low | matplotlib |

---

## 6. Crypto-Specific Considerations

- **24/7 markets:** No market close — theta decay is continuous, adjust T calculation accordingly
- **High volatility:** Crypto vol ranges 50-150% annualized vs 15-30% for equities
- **Funding rates:** Perpetual futures funding affects put-call parity
- **No dividends:** Simplifies Black-Scholes (no dividend adjustment needed for most tokens)
- **Liquidity:** Options liquidity is concentrated in BTC/ETH; Solana options markets are thin
- **Settlement:** Most crypto options are cash-settled in the underlying or USD

---

*This document is for informational and planning purposes only. It does not constitute financial advice.*
