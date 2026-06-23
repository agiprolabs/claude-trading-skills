# Structure & Modeling — Kalshi Crypto & Index Range Markets

Detailed reference for series definitions, bracket anatomy, volatility-derived σ, decision timing, and settlement. Read `SKILL.md` first for context.

---

## Series Definitions

| Series ticker | Underlying | Market type | Cadence |
|--------------|------------|-------------|---------|
| `KXINX` | S&P 500 index (INX) | `index` | Daily only |
| `KXNASDAQ100` | Nasdaq-100 (NDX) | `index` | Daily only |
| `KXBTC` | Bitcoin / USD | `crypto` | Daily + hourly |
| `KXETH` | Ethereum / USD | `crypto` | Daily + hourly |

Code convention:

```python
SERIES_MARKET = {
    "KXINX":       "index",
    "KXNASDAQ100": "index",
    "KXBTC":       "crypto",
    "KXETH":       "crypto",
}
```

---

## Bracket Anatomy

Each event `E` at settlement time `T` is a price-level partition:

```
  … | tail_low | B_1 | B_2 | … | B_n | tail_high | …
  (−∞, floor_1)  [floor_1, cap_1]  …  [floor_n, cap_n]  (cap_n, +∞)
```

- **Interior bracket** `B_k`: covers the closed interval `[floor_k, cap_k]`. Settlement YES iff the reference price `∈ [floor_k, cap_k]`.
- **Low tail**: YES iff reference price `< floor_1`.
- **High tail**: YES iff reference price `> cap_n`.
- Exactly one market is YES at settlement.
- Bracket width is set per-event; do not assume a fixed width — read the market list from the API.

### Overround

```python
overround = sum(p_yes for all brackets in event)
# fair = 1.0; typical live overround = 1.05–1.20
```

Overround is concentrated in the cheap tails. The interior brackets near the current underlying level tend to be fairly priced.

---

## Modeling: σ from Underlying Volatility

### Daily markets

Use the log-return diffusion approximation to express annual volatility in price-level units:

```python
import numpy as np
from scipy.stats import norm

def price_sigma_daily(underlying_price: float, annual_vol: float) -> float:
    """
    Convert annualized % vol to 1-day price-unit sigma.
    annual_vol: e.g. 0.20 for 20% annualized
    Returns sigma in the same units as the price.
    """
    daily_log_sigma = annual_vol / np.sqrt(252)          # index (trading days)
    # For crypto (24/7), use 365:
    # daily_log_sigma = annual_vol / np.sqrt(365)
    return underlying_price * daily_log_sigma


def p_yes_bracket(mu: float, sigma: float, floor: float, cap: float) -> float:
    """
    P(YES) for an interior bracket [floor, cap] under N(mu, sigma).
    mu: forecast mean price at settlement
    sigma: price-unit standard deviation
    NO half-integer correction (continuous settlement price).
    """
    return norm.cdf((cap - mu) / sigma) - norm.cdf((floor - mu) / sigma)


def p_yes_low_tail(mu: float, sigma: float, floor: float) -> float:
    return norm.cdf((floor - mu) / sigma)


def p_yes_high_tail(mu: float, sigma: float, cap: float) -> float:
    return 1.0 - norm.cdf((cap - mu) / sigma)
```

### Hourly markets (BTC/ETH)

For a 1-hour horizon, scale from daily:

```python
def price_sigma_hourly(underlying_price: float, daily_vol_pct: float) -> float:
    hourly_log_sigma = daily_vol_pct / np.sqrt(24)
    return underlying_price * hourly_log_sigma
```

IV-derived σ is preferable to realized-vol for hourlies because the market's own distributional expectation for the next hour is embedded in the options surface. Use the ATM 1-hour or shortest-dated expiry.

### σ sources (preferred order)

| Source | Notes |
|--------|-------|
| ATM IV from listed options | Forward-looking; preferred. SPX/NDX options for index; CME BTC/ETH or Deribit for crypto |
| Realized vol (5-day rolling) | Backward-looking; more stable, slower to adapt to vol regime changes |
| Realized vol (1-day) | Noisy; useful for fast-adapting hourly estimates |

Always verify that the vol source is in the same units (annualized %) before converting.

---

## Decision Timing

### Index daily

| Event | Time (ET) |
|-------|-----------|
| Market open | 9:30 AM |
| Decision book read | ~2:00 PM (2h before close) |
| Settlement close | 4:00 PM |

```python
from datetime import time
DECISION_OFFSET_MINUTES = 120
# decision_ts = settlement_close_ts - timedelta(minutes=DECISION_OFFSET_MINUTES)
```

### Crypto daily

Settlement close time is defined in the market's rulebook (varies; often midnight UTC or a Kalshi-specified time). Apply the same 120-min default offset and adjust based on fill observations.

### Crypto hourly

Each hourly market settles at the top of the hour. The decision window is short — on the order of 10–30 minutes before the close. The offset should be tighter:

```python
HOURLY_DECISION_OFFSET_MINUTES = 15  # indicative; tune per fill data
```

At this frequency, the dominant risk is not model error but HFT front-running in the final minutes. See the HFT caveat in `SKILL.md`.

---

## Settlement

**Always use Kalshi's own `result` field.** Do not re-derive settlement from an external price feed.

Key questions to answer per-series before backtesting or trading:

1. **Settlement price source:** Exchange official close? A composite of multiple exchanges? A Kalshi-computed VWAP? Read the per-market rulebook.
2. **Settlement time:** The exact UTC timestamp. For S&P 500 this is the 4:00 PM ET official close; for crypto it is market-specified.
3. **Bracket boundary condition:** Is the boundary inclusive or exclusive? (Kalshi temperature brackets use both-ends-inclusive; price brackets should be checked per-market.)
4. **Corporate actions / index rebalances:** For index markets, large rebalance events (Russell reconstitution, S&P additions) can cause out-of-distribution moves. Flag these dates in any backtest.

### Common backtest error

Substituting Yahoo Finance or Binance closing prices for the Kalshi-defined settlement reference will produce small but systematic settlement mismatches that corrupt P&L attribution. The mismatch is usually < 0.5% on price but can shift a bracket outcome at the boundary.

---

## Sizing and Risk

Use the same sizing framework as weather markets (Kelly/SLSQP under EV threshold). Key differences to account for:

- **Correlation:** BTC and ETH daily returns are highly correlated (~0.85). Treat them as a correlated pair, not independent bets, when sizing simultaneously.
- **Index–crypto correlation:** BTC/ETH daily returns correlate with equity risk-on/off at ~0.4–0.6 in high-volatility regimes. Portfolio-level risk is higher than the individual-market EV suggests.
- **Tail risk:** Price distributions have fat tails relative to Gaussian. The Gaussian model will underestimate the probability of extreme brackets. Apply a tail-inflation factor (e.g., model with a Student-t ν=5) or add a vol-of-vol buffer to σ.

See `prediction-market-strategy` for the full Kelly/SLSQP optimizer and EV-threshold filter.

---

## Related Files

- `SKILL.md` — Strategy overview, edge evidence, HFT caveat
- `../prediction-markets/references/brackets-and-settlement.md` — Shared bracket/overround formulas
