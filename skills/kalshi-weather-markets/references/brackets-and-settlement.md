# Brackets & Settlement

How range markets are defined, how a forecast maps to per-bracket probabilities, and the exact rules that decide payouts. Settlement is where most backtest errors live — get this wrong and you manufacture an edge that does not exist.

> **Settlement-source references (verify the per-market spec before trusting any of this):**
> - Kalshi market rules: <https://docs.kalshi.com> (per-market "Rulebook")
> - NWS Climatological Report (CLI): <https://www.weather.gov/wrh/Climate>
> - IEM ASOS daily download: <https://mesonet.agron.iastate.edu/request/daily.phtml> (100% match to Kalshi)
> - Polymarket resolution via Weather Underground: <https://www.wunderground.com> + UMA: <https://docs.uma.xyz>
>
> Settlement source, station, and day-window are **per-market contract terms that can change** — read each market's own rules/spec before scoring or trading it.

---

## Bracket Structure (Kalshi Temperature)

- A bracket ticker `B<center>` is a **2°F-wide, both-ends-inclusive** window. `B74.5` covers the **two integers {74, 75}°F**.
- A threshold ticker `T<strike>` is a one-sided market — `greater` or `less` — and **you must read `strike_type` from the API**, not infer it from the ticker.
- Brackets in an event are **mutually exclusive and (with two open tails) collectively exhaustive**. Their YES prices sum to the **overround** (fair = 1.0; > 1.0 = aggregate overpricing).

### Ticker Format

```
KXHIGH<CITY>-<YYMONDD>-B<center>     # e.g. KXHIGHNY-26JUN21-B74.5
KXHIGH<CITY>-<YYMONDD>-T<strike>     # e.g. KXHIGHNY-26JUN21-T80
KXLOW<CITY>-<YYMONDD>-B<center>
KXLOW<CITY>-<YYMONDD>-T<strike>
```

**The date is encoded in the ticker.** `close_time` is next-day UTC (~00:59 ET) — joining on it off-by-ones every label. Always parse the ticker date for settlement-date joins.

---

## Forecast → P(YES)

Given a forecast distribution `N(μ, σ)` for the day's extreme, with the **half-integer continuity correction** (mandatory — settlement is on integers):

```
# Bracket B<center>, covering integers {floor, cap}  (e.g. B74.5: floor=74, cap=75)
P(YES) = Φ((cap + 0.5 − μ) / σ) − Φ((floor − 0.5 − μ) / σ)

# Threshold "greater than or equal":
P(YES) = 1 − Φ((T + 0.5 − μ) / σ)

# Threshold "less than or equal":
P(YES) =     Φ((T − 0.5 − μ) / σ)
```

`Φ` is the standard normal CDF. The `± 0.5` shift is **not optional** — dropping it biases every bracket, and using a 1°F window (off-by-one) on the 2°F brackets produced a **phantom +1640% backtest** in one project.

See `scripts/weather_brackets.py` for a runnable implementation.

---

## Settlement Rules

### Kalshi

- **Source:** NWS Climatological Report (CLI) — the official daily climate summary issued by each WFO.
- **Backup / programmatic access:** IEM ASOS daily download matches CLI 100%.
- **Window:** **LST (Local Standard Time), no DST.** The day runs midnight-to-midnight LST year-round.
- **Value:** Integer °F maximum (HIGH) or minimum (LOW) for that LST day.
- **Bracket YES:** `cli ∈ {floor, cap}` — both ends inclusive.
- **Threshold `greater` YES:** `cli >= strike + 1`
- **Threshold `less` YES:** `cli <= strike - 1`

### Polymarket

- **Source:** Weather Underground history.
- **Window:** Local clock **with DST**, midnight-to-midnight.
- Disputes resolved via **UMA** optimistic oracle vote.

### Cross-Venue Divergence (Real Money)

| Axis | Kalshi | Polymarket |
|------|--------|------------|
| Source | NWS CLI / IEM ASOS | Weather Underground |
| Day window | LST (no DST) | Local clock (DST) |
| NYC station | **KNYC** (Central Park) | **KLGA** (LaGuardia) |
| Rounding | Integer °F, `t ∈ {floor, cap}` | Per WU history |

The same metro on the same date can settle to **different values** across venues — both because of the **station** (KNYC vs KLGA) and the **DST window** in spring/fall. Any cross-venue analysis must settle each leg on its own source.

---

## Overround as a Feature

```python
overround = sum(p_yes_bracket_i for all brackets in event)
```

- Fair market: `overround == 1.0`
- Typical Kalshi: `1.05–1.15` (house edge + favorite–longshot inflation)
- `overround >> 1.1`: suspect data or a genuinely mispriced event

The favorite–longshot bias inflates tail brackets above fair value — those overpriced tails are the primary maker-side opportunity.

---

## The Cardinal Rule

> Score every settlement against the **venue's own resolution source** — not against any derived or correlated truth. Using grid-actuals, NWP model output, or WU to score Kalshi contracts will flip ~10% of outcomes and manufacture phantom edge.
