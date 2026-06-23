# Brackets & Settlement

How range markets are defined, how a forecast maps to per-bracket probabilities, and the exact rules that decide payouts. Settlement is where most backtest errors live — get this wrong and you manufacture an edge that does not exist.

> 📖 **Settlement-source references (verify the per-market spec before trusting any of this):** Kalshi market rules <https://docs.kalshi.com> (per-market "Rulebook"); NWS Climatological Report (CLI) <https://www.weather.gov/wrh/Climate>; IEM ASOS daily download <https://mesonet.agron.iastate.edu/request/daily.phtml> (100% match to Kalshi); Polymarket resolution via Weather Underground <https://www.wunderground.com> + UMA <https://docs.uma.xyz>. Settlement source, station, and day-window are **per-market contract terms that can change** — read each market's own rules/spec before scoring or trading it.

## Bracket structure (Kalshi temperature)

- A bracket ticker `B<center>` is a **2°F-wide, both-ends-inclusive** window. `B74.5` covers the **two integers {74, 75}°F**.
- A threshold ticker `T<strike>` is a one-sided market — `greater` or `less` — and **you must read `strike_type` from the API**, not infer it from the ticker.
- Brackets in an event are **mutually exclusive and (with two open tails) collectively exhaustive**. Their YES prices sum to the **overround** (fair = 1.0; > 1.0 = aggregate overpricing).

## Forecast → P(YES)

Given a forecast distribution `N(μ, σ)` for the day's extreme, with the **half-integer continuity correction** (mandatory, because settlement is on integers):

```
# bracket B<center>, covering integers {floor, cap}  (e.g. B74.5: floor=74, cap=75)
P(YES) = Φ((cap + 0.5 − μ) / σ) − Φ((floor − 0.5 − μ) / σ)

# threshold, "greater than or equal":
P(YES) = 1 − Φ((T + 0.5 − μ) / σ)

# threshold, "less than or equal":
P(YES) =     Φ((T − 0.5 − μ) / σ)
```

`Φ` is the standard normal CDF. The `± 0.5` shift is **not optional** — dropping it biases every bracket, and using a 1°F window (off-by-one) on the 2°F brackets produced a **phantom +1640% backtest** in one project.

## Settlement rules (what actually pays)

### Kalshi
- **Source:** NWS **CLI** daily climate report, **integer °F**. Mirrored exactly by **IEM ASOS** daily (`max_temp_f`/`min_temp_f`) — a **100% match** to Kalshi payouts in practice.
- **Window:** **Local Standard Time, year-round (no DST shift).**
- **Bracket** settles **YES iff `cli ∈ {floor, cap}`** (the two winning integers). NOT `floor ≤ round(t) < cap`.
- **Threshold:** `greater` YES iff `cli ≥ T + 1`; `less` YES iff `cli ≤ T − 1`.
- **Do not settle on grid actuals / reanalysis** — leaky and inaccurate.

### Polymarket
- **Source:** **Weather Underground** history.
- **Window:** **local clock WITH DST**, midnight-to-midnight.
- Disputes → **UMA** optimistic oracle vote.

### Cross-venue divergence (real money)

| Axis | Kalshi | Polymarket |
|------|--------|-----------|
| Source | NWS CLI / IEM ASOS | Weather Underground |
| Day window | LST (no DST) | local clock (DST) |
| NYC station | **KNYC** (Central Park) | **KLGA** (LaGuardia) |
| Rounding | integer °F, `t ∈ {floor,cap}` | per WU history |

The same metro on the same date can settle to **different values** across venues — both because of the **station** (KNYC vs KLGA) and the **DST window** in spring/fall. Any cross-venue analysis must settle each leg on its own source.

## The cardinal rule

**Settle against the venue's own resolution, never a re-derived truth.** A real example: scoring Kalshi brackets with the wrong rule (`floor ≤ round(high) < cap`, treating them as 1°F half-open) instead of the true `high ∈ {floor, cap}` flipped **~10% of outcomes**, systematically marking winning favorites as losses — which manufactured a fake "+18% favorite-fade edge." Re-settled on Kalshi's authoritative per-bracket `result`, the edge vanished and favorites were correctly priced.

Corollary: the legitimate use of a *derived* source (IEM ASOS, your own station read) is to compute settlement **faster** or fill gaps **using the same source/rule the venue uses** — never a *different* source that merely correlates.

## Overround as a feature

```
overround = Σ_brackets  P_yes(bracket)          # fair = 1.0
```
Persistent overround > 1.0 reflects the favorite–longshot bias concentrated in the cheap tails. It is a microstructure signal, not an arbitrage by itself (per-leg fees + thin books usually defeat naive "sell the whole overpriced set" dutching on Kalshi).
