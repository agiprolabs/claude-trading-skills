# Forecasting for Brackets

How to turn a weather forecast into per-bracket probabilities — and why a *good* forecast is usually **not** a trading edge.

## Ensemble quantiles → (μ, σ)

Take the forecast as quantiles (p10, p50, p90) from a multi-model ensemble, then:

```
sigma_raw = max((p90 − p10) / 2.56, 0.5) · sigma_scale · sigma_mult
mu        = p50                                   # or nowcast-blended (below)
sigma     = max(sigma_raw, 0.1)                   # hard floor
```

The **2.56 divisor** spans the 10th–90th percentile range of a standard normal (= 2 × 1.28σ). The σ floors prevent overconfident degenerate distributions.

## Nowcast blending (`t0_blend`) — same-day path

Once an intraday observation is available, pull μ toward reality and shrink σ:

- **HIGH:** clamp μ to `[obs, obs + drift · hours_remaining]`
- **LOW:** clamp μ to `[obs − drift · hours_remaining, obs]`
- σ shrinks as `sigma_raw · sqrt(hours_remaining / 24)`, floored at `sigma_floor` (≈0.5).
- `drift` ≈ 3.0 °F/hr default.

Optional NWP **prior blend**: `new_p50 = w·hrrr + (1−w)·p50` (w≈0.5), then rebuild symmetric quantiles `p10 = new50 − 1.28σ`, `p90 = new50 + 1.28σ` if a calibrated σ is known.

## Quantiles → P(YES)

With the half-integer continuity correction (mandatory — settlement is on integers):

```
bracket {floor,cap}:  P = Φ((cap + 0.5 − μ)/σ) − Φ((floor − 0.5 − μ)/σ)
threshold greater(T): P = 1 − Φ((T + 0.5 − μ)/σ)
threshold less(T):    P =     Φ((T − 0.5 − μ)/σ)
```

`Φ(x) = 0.5·(1 + erf(x / √2))` — stdlib only, no scipy needed.

## Settle-space bias correction (CLI ≠ METAR)

The settlement value (NWS CLI integer °F, LST day) is **not** the same as raw ASOS/METAR hourly max/min — CLI applies QC, backup-station fallback, and LST aggregation. Before computing P(YES), shift μ into **CLI space**:

```
mu_cli = mu_metar + bias_city_season       # bias = oracle_extreme − asos_extreme, fit per city + season
```

Fit `bias_max` / `bias_min` as seasonal (circular) curves per city. Skipping this systematically misprices every bracket for cities with a structural CLI/METAR gap.

## Calibrated model performance (reference numbers)

A well-calibrated bracket model is genuinely skillful — but note the *baseline* it beats:

| | Kalshi (2°F, 6 brackets) | Polymarket (1°C, ~11 brackets) |
|---|---|---|
| Top-1 hit rate | ~55% | ~51% |
| Random baseline | 16.7% | 9.1% |
| Lift over random | ~3.3× | ~5.6× |

## The hard truth: forecast skill ≠ trading edge

By the decision hour the **market price already incorporates the same observations** your forecast uses (e.g. the afternoon METAR for a daily high). Measured: same-day model Brier ≈ market Brier, and `corr(model_p − market_p, realized) ≈ 0` or slightly negative — i.e. the forecast is *redundant with*, not *better than*, the price. So:

- A standalone forecast does **not** reliably beat the market at decision time.
- The forecast's real value is as a **tail filter** on the structural longshot-sell (don't sell a longshot your model flags as unusually likely) and possibly **at-open / T-1** (thin, less-informed book) — not as standalone alpha.

The durable edge is market-structure (see `strategy-catalog.md`), with the forecast as a risk overlay.
