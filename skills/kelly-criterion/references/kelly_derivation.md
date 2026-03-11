# Kelly Criterion — Mathematical Derivation

## Objective

Maximize the expected logarithm of wealth, which is equivalent to maximizing the long-term geometric growth rate of capital. This is known as the **Kelly objective** or **log-optimal** criterion.

## Single Binary Bet Derivation

### Setup

You have wealth `W`. You bet fraction `f` of `W` on a binary outcome:
- With probability `p`, you win and gain `f * b * W` (payoff ratio `b`)
- With probability `q = 1 - p`, you lose and lose `f * W`

After one bet:
- Win: `W_new = W * (1 + f * b)`
- Lose: `W_new = W * (1 - f)`

### Growth Rate

The expected log growth rate per bet is:

```
G(f) = p * log(1 + f * b) + q * log(1 - f)
```

We want to find `f*` that maximizes `G(f)`.

### First Derivative

```
dG/df = p * b / (1 + f * b) - q / (1 - f)
```

Set equal to zero:

```
p * b / (1 + f * b) = q / (1 - f)
```

Cross-multiply:

```
p * b * (1 - f) = q * (1 + f * b)
p * b - p * b * f = q + q * b * f
p * b - q = p * b * f + q * b * f
p * b - q = b * f * (p + q)
p * b - q = b * f * 1        [since p + q = 1]
f = (p * b - q) / b
```

Therefore:

```
f* = (p * b - q) / b = p - q / b = p - (1 - p) / b
```

### Second Derivative (Verify Maximum)

```
d²G/df² = -p * b² / (1 + f * b)² - q / (1 - f)²
```

This is always negative for `0 < f < 1`, confirming that `f*` is a maximum.

### Edge Condition

Kelly fraction is positive only when `p * b - q > 0`, i.e., the expected value of the bet is positive. If `p * b - q <= 0`, the optimal bet is `f* = 0`.

---

## Growth Rate at the Optimum

Substituting `f*` back into `G(f)`:

```
G* = p * log(1 + f* * b) + q * log(1 - f*)
```

With `f* = (p * b - q) / b`:

```
1 + f* * b = 1 + p * b - q = p * b + p = p * (b + 1)
1 - f* = 1 - p + q / b = q + q / b = q * (b + 1) / b
```

Therefore:

```
G* = p * log(p * (b + 1)) + q * log(q * (b + 1) / b)
G* = p * log(p) + q * log(q) + log(b + 1) + q * log(1/b)
G* = p * log(p) + q * log(q/b) + log(b + 1)
```

### Numerical Example

Win rate `p = 0.55`, payoff ratio `b = 1.5`:

```
f* = (0.55 * 1.5 - 0.45) / 1.5 = (0.825 - 0.45) / 1.5 = 0.375 / 1.5 = 0.25
G* = 0.55 * log(1 + 0.25 * 1.5) + 0.45 * log(1 - 0.25)
G* = 0.55 * log(1.375) + 0.45 * log(0.75)
G* = 0.55 * 0.3185 + 0.45 * (-0.2877)
G* = 0.1752 - 0.1295 = 0.0457
```

Growth rate of ~4.57% per bet at full Kelly.

---

## Overbetting vs. Underbetting Asymmetry

### At 2x Kelly (f = 2f*)

```
G(2f*) = p * log(1 + 2f* * b) + q * log(1 - 2f*)
```

For the example above (`f* = 0.25`):

```
G(0.50) = 0.55 * log(1.75) + 0.45 * log(0.50)
G(0.50) = 0.55 * 0.5596 + 0.45 * (-0.6931)
G(0.50) = 0.3078 - 0.3119 = -0.0041
```

Growth rate is **negative** at 2x Kelly. Overbetting by 2x leads to long-term ruin.

### At 0.5x Kelly (f = 0.5f*)

```
G(0.125) = 0.55 * log(1.1875) + 0.45 * log(0.875)
G(0.125) = 0.55 * 0.1719 + 0.45 * (-0.1335)
G(0.125) = 0.0945 - 0.0601 = 0.0345
```

Growth rate is 0.0345, which is **75.4%** of the optimal 0.0457. Half Kelly sacrifices only ~25% of growth but dramatically reduces variance and drawdown.

---

## Fractional Kelly Growth Rates

For fractional Kelly `f = α * f*` where `0 < α < 1`:

### Approximation

Near the optimum, growth rate is approximately parabolic:

```
G(α * f*) ≈ G* * (2α - α²) = G* * α * (2 - α)
```

This gives:
- `α = 0.25`: `G ≈ G* * 0.4375` (~44% of optimal growth)
- `α = 0.50`: `G ≈ G* * 0.75` (~75% of optimal growth)
- `α = 0.75`: `G ≈ G* * 0.9375` (~94% of optimal growth)
- `α = 1.00`: `G = G*` (100% of optimal growth)

### Variance Scaling

The variance of log-wealth growth scales with `α²`:

```
Var(log growth) ∝ α²
```

So half Kelly has 25% of the variance of full Kelly, while retaining 75% of the growth rate. This is the core argument for fractional Kelly.

### Maximum Drawdown Scaling

Expected maximum drawdown scales approximately linearly with `α`:

```
E[max drawdown] ∝ α
```

Half Kelly roughly halves the expected maximum drawdown compared to full Kelly.

---

## Continuous Kelly (Gaussian Returns)

When returns follow a continuous distribution rather than binary outcomes:

### Setup

Strategy has expected return `μ` and standard deviation `σ` per period. Risk-free rate is `r`. Invest fraction `f` of wealth.

Portfolio return per period: `R_p = r + f * (R - r)` where `R` is the strategy return.

### Log Growth Rate

```
G(f) = E[log(1 + R_p)]
     ≈ E[R_p] - Var(R_p) / 2     [second-order Taylor expansion]
     = r + f * (μ - r) - f² * σ² / 2
```

### Optimal Fraction

```
dG/df = (μ - r) - f * σ² = 0
f* = (μ - r) / σ²
```

### Relation to Sharpe Ratio

With Sharpe ratio `S = (μ - r) / σ`:

```
f* = S / σ = S² / (μ - r)
```

Optimal growth rate: `G* = r + S² / 2`

### Example

Strategy: `μ = 0.10` (10% per period), `σ = 0.20`, `r = 0`:

```
f* = 0.10 / 0.04 = 2.5
```

Kelly says lever 2.5x. In practice, use 0.5x → lever 1.25x.

---

## Multi-Outcome Kelly

When outcomes are not binary but have multiple possible returns `r_1, r_2, ..., r_n` with probabilities `p_1, p_2, ..., p_n`:

### Optimization Problem

```
maximize  Σ p_i * log(1 + f * r_i)
subject to  0 ≤ f ≤ 1
```

### First-Order Condition

```
Σ p_i * r_i / (1 + f * r_i) = 0
```

This generally requires numerical solution (Newton's method or bisection).

### Practical Approach

For trade P&L data with many distinct outcomes:

```python
from scipy.optimize import minimize_scalar

def neg_growth_rate(f: float, returns: list[float]) -> float:
    """Negative expected log growth rate (for minimization)."""
    n = len(returns)
    g = sum(math.log(1 + f * r) for r in returns if (1 + f * r) > 0)
    # Penalize if any outcome leads to ruin
    if any((1 + f * r) <= 0 for r in returns):
        return 1e10
    return -g / n

result = minimize_scalar(neg_growth_rate, bounds=(0, 1), method='bounded',
                         args=(returns,))
kelly_fraction = result.x
```

This approach handles arbitrary return distributions and automatically accounts for fat tails, skewness, and multi-modal outcomes.

---

## Key Takeaways

1. **f* = (pb - q) / b** for binary outcomes. Only bet when edge `pb - q > 0`.
2. **Overbetting is catastrophic**. At 2x Kelly, growth rate drops to zero. At 3x Kelly, you go broke.
3. **Half Kelly retains ~75% of growth** with ~25% of the variance. This is the practical sweet spot.
4. **Continuous Kelly: f* = (μ - r) / σ²**. Use when you have return streams rather than win/loss data.
5. **Multi-outcome Kelly** requires numerical optimization but handles real-world return distributions.
6. **All Kelly variants assume known parameters**. Estimation error always pushes you toward using smaller fractions.
