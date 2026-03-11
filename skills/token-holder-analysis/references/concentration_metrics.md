# Concentration Metrics — Formulas & Interpretation

## Top-N Holder Percentage

The simplest concentration measure. Sums the holdings of the N largest holders as a percentage of total supply.

**Formula**:
```
Top_N% = (Σ holdings[i] for i=1..N) / total_supply × 100
```

**Thresholds for Solana tokens**:

| Top 10 % | Risk Level | Interpretation |
|----------|------------|----------------|
| < 20% | Very Low | Exceptionally well distributed |
| 20-30% | Low | Good distribution |
| 30-50% | Moderate | Typical for mid-cap tokens |
| 50-80% | High | Significant dump risk |
| > 80% | Extreme | Likely controlled by a few actors |

**Important**: Always exclude known program accounts (DEX pools, bridge escrows, burn addresses) from holder counts. Including pool liquidity as a "holder" skews the metric.

---

## Gini Coefficient

Measures inequality of distribution. Originally from economics (income inequality), applied here to token holdings.

**Formula**:
```
G = (2 × Σ(i × x_i)) / (n × Σ(x_i)) - (n + 1) / n

where x_i are amounts sorted ascending, i is 1-indexed position, n is holder count
```

**Equivalent formula** (via mean absolute difference):
```
G = Σ_i Σ_j |x_i - x_j| / (2 × n² × μ)

where μ is the mean holding
```

**Range**: 0 to 1
- 0 = perfectly equal (every holder has the same amount)
- 1 = maximally unequal (one holder owns everything)

**Crypto-specific thresholds**:

| Gini | Interpretation |
|------|---------------|
| < 0.5 | Rare — very egalitarian distribution |
| 0.5-0.7 | Well distributed for crypto |
| 0.7-0.85 | Typical for established tokens |
| 0.85-0.95 | Common for newer/smaller tokens |
| > 0.95 | Extreme concentration |

**Limitations**:
- Gini is sensitive to the number of holders included. Computing over top 20 holders (RPC limit) vs. all holders gives different values.
- For meaningful comparison, always compute over the same sample size.
- Gini doesn't distinguish between distributions with the same inequality but different shapes (e.g., one whale vs. several large holders).

---

## Herfindahl-Hirschman Index (HHI)

Sum of squared market shares. Originally used for antitrust analysis (market concentration). More sensitive to large holders than Gini.

**Formula**:
```
HHI = Σ(s_i²)

where s_i = (holding_i / total_supply) × 100  (percentage share)
```

**Range**: 0 to 10,000
- Minimum (n equal holders): HHI = 10000/n
- Maximum (one holder): HHI = 10,000

**Thresholds** (adapted from DOJ antitrust guidelines):

| HHI | Interpretation |
|-----|---------------|
| < 1,500 | Unconcentrated (competitive) |
| 1,500-2,500 | Moderately concentrated |
| 2,500-5,000 | Highly concentrated |
| > 5,000 | Extremely concentrated |

**Advantage over Gini**: HHI is more sensitive to the presence of dominant holders. A distribution with one 50% holder and many small holders will have a much higher HHI than a distribution with several 10% holders, even if both have similar Gini values.

---

## Nakamoto Coefficient

Minimum number of entities needed to control >50% of the system. Named after Satoshi Nakamoto.

**Formula**:
```
N = min k such that Σ(holding_i for top k holders) > 0.51 × total_supply
```

**Interpretation**:

| Nakamoto | Meaning |
|----------|---------|
| 1 | Single entity controls majority — maximum centralization |
| 2-3 | Small cartel can control the token |
| 4-10 | Moderate decentralization |
| > 10 | Good decentralization |

**Notes**:
- Lower bound for Nakamoto is 1. If the largest holder owns >50%, Nakamoto = 1.
- The 51% threshold can be adjusted (e.g., 33% for tokens where 1/3 can block governance).
- Nakamoto coefficient is particularly useful for governance tokens where voting power matters.

---

## Shannon Entropy

Information-theoretic measure of distribution randomness. Not commonly used but provides additional perspective.

**Formula**:
```
H = -Σ(p_i × log2(p_i))

where p_i = holding_i / total_supply
```

**Range**: 0 to log2(n)
- 0 = one holder owns everything
- log2(n) = perfectly equal distribution

Higher entropy = more decentralized.

---

## Combining Metrics

No single metric tells the full story. Use them together:

```python
def comprehensive_risk(top_10_pct, gini, hhi, nakamoto):
    """Combine metrics into a single risk score."""
    scores = {
        "top10": 3 if top_10_pct > 80 else 2 if top_10_pct > 50 else 1 if top_10_pct > 30 else 0,
        "gini": 3 if gini > 0.95 else 2 if gini > 0.85 else 1 if gini > 0.7 else 0,
        "hhi": 3 if hhi > 5000 else 2 if hhi > 2500 else 1 if hhi > 1500 else 0,
        "nakamoto": 3 if nakamoto <= 1 else 2 if nakamoto <= 3 else 1 if nakamoto <= 5 else 0,
    }
    total = sum(scores.values())
    if total >= 9: return "EXTREME"
    if total >= 6: return "HIGH"
    if total >= 3: return "MODERATE"
    return "LOW"
```
