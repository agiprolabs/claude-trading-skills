---
name: kalshi-weather-markets
description: Daily temperature high/low bracket and threshold contracts on Kalshi — contract structure, forecast→P(YES) map, settlement rules, cross-venue divergences, and weather-specific pitfalls
---

# Kalshi Weather Markets — Daily Temperature High/Low

Kalshi lists daily high and low temperature options for ~20 US cities as binary contracts that settle YES ($1.00) or NO ($0.00). This skill covers the market structure, the forecast-to-probability map, exact settlement mechanics, and hard-won pitfalls. It builds on the exchange layer — for Kalshi API mechanics (host, auth, orders, order book, candlesticks) see the `kalshi-api` skill; for strategy, sizing, and backtesting see `prediction-market-strategy`.

## Contract Types

### Brackets — `B<center>`

A bracket ticker `B<center>` is a **2°F-wide, both-ends-inclusive** window.

- `B74.5` covers the **two integers {74, 75}°F**.
- YES iff the settled temperature is exactly 74 **or** 75.
- Brackets in one event are mutually exclusive and (with two open tail markets) collectively exhaustive.
- Their YES prices sum to the **overround** (fair = 1.0; > 1.0 = aggregate overpricing).

### Thresholds — `T<strike>`

A threshold ticker `T<strike>` is a one-sided binary.

- `greater` → YES iff `cli >= strike + 1`
- `less` → YES iff `cli <= strike - 1`
- **Critical:** `strike_type` (`"greater"` / `"less"`) is **not inferable from the ticker**. Read it from the API `strike_type` field every time.

### Ticker Format

```
KXHIGH<CITY>-<YYMONDD>-B<center>     # bracket high
KXLOW<CITY>-<YYMONDD>-T<strike>      # threshold low
```

**The date is encoded in the ticker, not derivable from `close_time`.**  
`KXHIGHNY-26JUN21` settles 2026-06-21 LST. `close_time` is next-day UTC (~00:59 ET). Joining on `close_time` off-by-ones every label — use the ticker date.

---

## Forecast → P(YES)

Given a forecast distribution `N(μ, σ)` for the day's extreme, apply the **half-integer continuity correction** (mandatory — settlement is on integers, not a continuous scale):

```
# Bracket B<center>, covering integers {floor, cap}
P(YES) = Φ((cap + 0.5 − μ) / σ) − Φ((floor − 0.5 − μ) / σ)

# Threshold "greater":
P(YES) = 1 − Φ((T + 0.5 − μ) / σ)

# Threshold "less":
P(YES) =     Φ((T − 0.5 − μ) / σ)

Φ(x) = 0.5 · (1 + erf(x / √2))   # stdlib only, no scipy needed
```

The `±0.5` shift is **not optional**. Dropping it biases every bracket. Treating 2°F brackets as 1°F half-open windows produced a **+1640% phantom backtest** in one project.

See `scripts/weather_brackets.py` for runnable implementations of all four functions.

---

## Deriving (μ, σ) from Ensemble Quantiles

```
sigma_raw = max((p90 − p10) / 2.56, 0.5) · sigma_scale · sigma_mult
mu        = p50                          # or nowcast-blended (see forecasting.md)
sigma     = max(sigma_raw, 0.1)          # hard floor against degeneracy
```

The **2.56 divisor** is the 10th–90th percentile span of a standard normal (2 × 1.28σ).

---

## CLI-Space Bias Correction

The settlement value (NWS CLI integer °F, LST day) is **not** the same as raw ASOS/METAR hourly max/min — CLI applies QC, backup-station fallback, and LST aggregation. Shift μ before computing P(YES):

```
mu_cli = mu_metar + bias_city_season     # bias = oracle_extreme − asos_extreme, fit per city + season
```

Fit `bias_max` / `bias_min` as seasonal (circular) curves per city. Skipping this systematically misprices every bracket for cities with a structural CLI/METAR gap.

---

## Settlement Rules

### Kalshi

- **Source:** NWS Climatological Report (CLI) — the official daily climate summary issued by each WFO.
- **Fallback:** IEM ASOS daily download matches CLI 100% and is available programmatically.
- **Window:** **LST (Local Standard Time), no DST adjustment.** The day runs midnight-to-midnight LST year-round.
- **Value:** Integer °F maximum (HIGH) or minimum (LOW) temperature for that LST day.
- **Bracket:** YES iff `cli ∈ {floor, cap}` (both ends inclusive).
- **Threshold greater:** YES iff `cli >= strike + 1`.
- **Threshold less:** YES iff `cli <= strike - 1`.

### Settlement-Source References

> **Read each market's own rulebook before scoring or trading.** Settlement source, station, and day-window are per-market contract terms that can change.

| Resource | URL |
|----------|-----|
| Kalshi market rules / Rulebook | <https://docs.kalshi.com> (per-market "Rulebook") |
| NWS Climatological Report (CLI) | <https://www.weather.gov/wrh/Climate> |
| IEM ASOS daily download | <https://mesonet.agron.iastate.edu/request/daily.phtml> |
| Polymarket resolution (WU) | <https://www.wunderground.com> |
| Polymarket disputes (UMA) | <https://docs.uma.xyz> |

---

## Cross-Venue Divergence

The same metro on the same date can settle to **different values** across venues — both because of the **station** and the **DST window** in spring/fall.

| Axis | Kalshi | Polymarket |
|------|--------|------------|
| Source | NWS CLI / IEM ASOS | Weather Underground |
| Day window | LST (no DST) | Local clock (with DST) |
| NYC station | **KNYC** (Central Park) | **KLGA** (LaGuardia) |
| Rounding | Integer °F, `t ∈ {floor, cap}` | Per WU history |

Any cross-venue analysis must settle each leg on its own source.

---

## Nowcast Blending (Same-Day Path)

Once an intraday observation is available, pull μ toward reality and shrink σ:

- **HIGH:** clamp μ to `[obs, obs + drift · hours_remaining]`
- **LOW:** clamp μ to `[obs − drift · hours_remaining, obs]`
- σ shrinks as `sigma_raw · sqrt(hours_remaining / 24)`, floored at `sigma_floor` (≈ 0.5)
- `drift` ≈ 3.0°F/hr default

Optional NWP prior blend: `new_p50 = w · hrrr + (1−w) · p50` (w ≈ 0.5), then rebuild symmetric quantiles using a calibrated σ.

---

## Calibrated Model Performance (Reference Numbers)

Per-city OOS Brier scores across 22 highs + 22 lows (v1.5, 2026-06-17 baseline):

| Metric | Range |
|--------|-------|
| Per-city OOS Brier | 0.07 – 0.14 (lower = better; 0.25 = climatology) |
| Per-city accuracy | 65–85% (bracket classification) |

**Forecast skill ≠ trading edge.** A calibrated model that beats climatology by 0.05 Brier does not guarantee positive EV at market prices — the market already incorporates NWP. The practical edge is maker-side fading of mispriced longshot brackets (favorite–longshot bias), not raw directional forecasting.

---

## Weather Pitfalls

1. **Wrong settlement source.** Scoring against a derived truth that correlates with but differs from the venue's resolution flips ~10% of outcomes. Settle on the venue's own `result`.

2. **Bracket off-by-one (phantom +1640%).** Treating 2°F inclusive brackets `{floor, cap}` as 1°F half-open `[floor, cap)` manufactures a large phantom backtest edge. The bracket is **both-ends-inclusive**.

3. **strike_type not inferable from ticker.** `T74` on a low market might be `greater` or `less`. Always read `strike_type` from the API. Never guess.

4. **Date-in-ticker, not `close_time`.** Use the date embedded in the ticker string for settlement-date joins, not `close_time` (which is next-day UTC).

5. **LST ≠ local clock.** Kalshi settles on LST (no DST). In spring/fall, the LST window shifts relative to local time. Cross-referencing WU (which uses local clock) against CLI on DST-transition days will produce mismatches.

6. **CLI ≠ METAR.** Raw ASOS hourly max/min is not the settlement value. CLI applies QC, backup-station fallback, and LST aggregation. Fit per-city seasonal bias corrections before computing P(YES).

7. **UTC vs local-day feature aggregation.** Aggregating forecast features over UTC days instead of LST days misaligns labels — cost ~14 percentage points of accuracy in one study.

8. **Clock-mismatch look-ahead.** Filling at an 18:00Z book snapshot while features are cut at 14:00 LST trades non-Eastern cities on future information. Use each city's own local decision time.

9. **Phantom penny asks.** 1¢ ask levels are frequently spoofed; assuming you fill them over-credits PnL ~23×. Count only depth that persists across snapshots and is corroborated by trade prints.

10. **Overround as a diagnostic.** Sum the YES prices across an event's full bracket set. `overround > 1.0` is normal (house edge); `overround >> 1.1` signals a mispriced event (or data error).

---

## Files

### References

- `references/brackets-and-settlement.md` — Bracket/threshold structure, P(YES) formulas, settlement rules, cross-venue divergence table, overround
- `references/forecasting.md` — Ensemble quantiles → (μ, σ), nowcast blending, CLI-space bias correction, model skill numbers, forecast ≠ edge

### Scripts

- `scripts/weather_brackets.py` — Gaussian bracket/threshold P(YES), settlement resolution, and quantile→(μ,σ) functions (pure stdlib, runs offline)
