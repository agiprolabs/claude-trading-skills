---
name: options-pricing
description: "[STUB] Options pricing models including Black-Scholes, binomial trees, Monte Carlo, implied volatility surfaces, and Greeks for crypto options"
---

# Options Pricing

> **Status: STUB** — This skill provides a basic Black-Scholes implementation and an overview of planned capabilities. Full implementation is awaiting community contribution.

Options pricing is the quantitative foundation of derivatives trading. For crypto markets, options on BTC and ETH trade actively on Deribit, Lyra, and Aevo, while Solana options are emerging on platforms like Zeta Markets and PsyOptions. Understanding pricing models, implied volatility surfaces, and Greeks is essential for hedging, volatility trading, and constructing structured products.

This skill is informational and analytical only. It does not provide financial advice or trading recommendations.

---

## Current Capabilities

This stub includes a working Black-Scholes calculator with Greeks computation and a basic implied volatility solver. See `scripts/black_scholes.py` for the implementation.

```python
import math
from scipy.stats import norm

def black_scholes_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Price a European call option using Black-Scholes.

    Args:
        S: Current underlying price.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate (annualized).
        sigma: Volatility (annualized).

    Returns:
        Theoretical call option price.
    """
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
```

Run the demo:

```bash
python scripts/black_scholes.py --demo
```

---

## Planned Capabilities

When fully implemented, this skill will cover:

### Pricing Models

| Model | Option Style | Use Case |
|-------|-------------|----------|
| Black-Scholes | European | Vanilla calls/puts, quick Greeks |
| Binomial Tree | American | Early exercise, dividend-paying assets |
| Monte Carlo | Exotic | Path-dependent, barrier, Asian options |
| Black-76 | Futures | Futures options on crypto perpetuals |

### Greeks

| Greek | Measures | Formula Basis |
|-------|----------|---------------|
| Delta | Price sensitivity to underlying | dC/dS |
| Gamma | Delta sensitivity to underlying | d²C/dS² |
| Theta | Time decay per day | dC/dT |
| Vega | Sensitivity to volatility | dC/dσ |
| Rho | Sensitivity to interest rates | dC/dr |

### Implied Volatility

- Newton-Raphson and bisection IV solvers
- Volatility smile and skew analysis
- IV surface construction (strike x expiry)
- IV term structure analysis
- Vol-of-vol estimation

### Crypto Options Platforms

| Platform | Chain | Assets | Style |
|----------|-------|--------|-------|
| Deribit | Off-chain | BTC, ETH | European |
| Lyra | Optimism/Arbitrum | ETH, BTC | European |
| Aevo | Ethereum L2 | BTC, ETH, alts | European |
| Zeta Markets | Solana | SOL, BTC | European |
| PsyOptions | Solana | SOL, various | American |

### Structured Products

- Covered calls and protective puts
- Straddles and strangles for volatility trading
- Vertical spreads for directional exposure
- Iron condors for range-bound markets
- Calendar spreads for term structure trades

---

## Prerequisites

```bash
# Core (for full implementation)
uv pip install numpy scipy

# Optional (for visualization)
uv pip install matplotlib
```

The included `scripts/black_scholes.py` uses only the Python standard library (`math` module) and runs without any dependencies.

---

## Use Cases

### Hedging
Compute delta-neutral hedge ratios for crypto spot positions using options. Calculate the number of put contracts needed to protect a portfolio against downside moves.

### Volatility Trading
Compare implied volatility to realized volatility to identify over/underpriced options. When IV significantly exceeds realized vol, selling premium may be favorable (and vice versa).

### Structured Products
Price structured products that combine options at different strikes and expirations. Analyze payoff profiles and breakeven points before execution.

### Risk Assessment
Use Greeks to understand portfolio-level exposure to price moves (delta), acceleration (gamma), time decay (theta), and volatility changes (vega).

---

## Quick Reference: Black-Scholes Formulas

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
```

**Put-call parity:**
```
C - P = S - K * e^(-rT)
```

---

## Files

| File | Description |
|------|-------------|
| `references/planned_features.md` | Planned features, formulas, data sources, and implementation priorities |
| `scripts/black_scholes.py` | Black-Scholes calculator with Greeks and implied vol solver |

---

## Contributing

This skill is a stub awaiting full implementation. To contribute:

1. Implement binomial tree pricing for American-style options
2. Add Monte Carlo simulation for exotic payoffs
3. Build IV surface construction from market quotes
4. Integrate Deribit API for live options chain data
5. Add portfolio Greeks aggregation

See `references/planned_features.md` for the full feature list and implementation priorities.

---

*This skill provides analytical tools and mathematical models for informational purposes only. It does not constitute financial advice. Options trading involves substantial risk of loss.*
