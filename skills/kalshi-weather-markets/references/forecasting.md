# Forecasting for Weather Brackets

How to go from a multi-model forecast ensemble to a calibrated `N(μ, σ)` distribution, and from that distribution to per-bracket P(YES) values. Also: why calibrated forecasts do not automatically translate into trading edge.

---

## Ensemble Quantiles → (μ, σ)

Take the forecast as quantiles (p10, p50, p90) from a multi-model ensemble, then:

```
sigma_raw = max((p90 − p10) / 2.56, 0.5) · sigma_scale · sigma_mult
mu        = p50                                   # or nowcast-blended (below)
sigma     = max(sigma_raw, 0.1)                   # hard floor
```

The **2.56 divisor** spans the 10th–90th percentile range of a standard normal (= 2 × 1.28σ). The σ floors prevent overconfident degenerate distributions.

---

## Nowcast Blending (`t0_blend`) — Same-Day Path

Once an intraday observation is available, pull μ toward reality and shrink σ:

- **HIGH:** clamp μ to `[obs, obs + drift · hours_remaining]`
- **LOW:** clamp μ to `[obs − drift · hours_remaining, obs]`
- σ shrinks as `sigma_raw · sqrt(hours_remaining / 24)`, floored at `sigma_floor` (≈ 0.5)
- `drift` ≈ 3.0°F/hr default

Optional NWP **prior blend**: `new_p50 = w · hrrr + (1−w) · p50` (w ≈ 0.5), then rebuild symmetric quantiles `p10 = new50 − 1.28σ`, `p90 = new50 + 1.28σ` if a calibrated σ is known.

---

## Quantiles → P(YES)

With the half-integer continuity correction (mandatory — settlement is on integers):

```
bracket {floor, cap}:  P = Φ((cap + 0.5 − μ)/σ) − Φ((floor − 0.5 − μ)/σ)
threshold greater(T):  P = 1 − Φ((T + 0.5 − μ)/σ)
threshold less(T):     P =     Φ((T − 0.5 − μ)/σ)
```

`Φ(x) = 0.5 · (1 + erf(x / √2))` — stdlib only, no scipy needed.

See `scripts/weather_brackets.py` for the full implementation.

---

## Settle-Space Bias Correction (CLI ≠ METAR)

The settlement value (NWS CLI integer °F, LST day) is **not** the same as raw ASOS/METAR hourly max/min — CLI applies QC, backup-station fallback, and LST aggregation. Before computing P(YES), shift μ into **CLI space**:

```
mu_cli = mu_metar + bias_city_season       # bias = oracle_extreme − asos_extreme, fit per city + season
```

Fit `bias_max` / `bias_min` as seasonal (circular) curves per city. Skipping this systematically misprices every bracket for cities with a structural CLI/METAR gap.

---

## Calibrated Model Performance (Reference Numbers)

v1.5 baseline (2026-06-17), leak-free OOS across 22 highs + 22 lows:

| Metric | Typical range |
|--------|---------------|
| Per-city OOS Brier score | 0.07 – 0.14 (0.25 = climatology baseline) |
| Per-city accuracy (bracket classification) | 65 – 85% |

These numbers are from `data/weather/oos_holdout_skill.csv` in the tempscale repo. Validated with a temporal holdout (train ≤ cutoff, test on held-out future) to ensure no leakage.

**Never report shuffled-CV Brier as OOS skill.** Shuffle-split on temperature time series leaks future observations into training and inflates skill by 0.02–0.05 Brier.

---

## The Hard Truth: Forecast Skill ≠ Trading Edge

A calibrated model that beats climatology by 0.05 Brier does not guarantee positive EV at market prices. The market prices already incorporate public NWP forecasts (GFS, ECMWF, NBM). Empirical findings:

- At Kalshi opening, market-implied probabilities track NWP ensembles within ~2–3% for most brackets.
- The practical edge is not directional: it is **maker-side fading of overpriced longshot brackets** (favorite–longshot bias). Tail brackets (< 10% YES probability) are systematically overpriced by 2–5 percentage points by retail participants.
- Beating the market by enough to overcome the taker fee (≈ 7% peak at p=0.5, ≈ 0 at the wings) requires either private data or structural market microstructure exploitation.

Use per-city OOS Brier as a **sizing input** (better-calibrated cities get larger positions) rather than as a profit guarantee.

---

## Leakage Rules for Temporal Validation

1. Train on data ≤ cutoff date; test on held-out future.
2. Intraday lookahead: use 11:00 LST (high) or 02:00 LST (low) as the feature-cutoff — no observations from later in the settlement day.
3. UTC vs local-day: aggregate features over the **LST day** the venue settles on, not the UTC day. UTC aggregation cost ~14 percentage points of accuracy in one study.
4. Walk-forward PnL from synthetic backtests (infinite liquidity) is a forecast-skill diagnostic only — not a profit forecast.
