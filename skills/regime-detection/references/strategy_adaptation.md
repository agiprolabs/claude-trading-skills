# Regime Detection — Strategy Adaptation Reference

How to adapt trading strategies, position sizing, and risk parameters based on the detected market regime.

## Regime-Strategy Matrix

| Regime | Best Strategies | Worst Strategies | Notes |
|---|---|---|---|
| **Low vol + trend up** | Trend following, breakout, momentum | Mean reversion, short selling | Cleanest edge. Full position size. Tight trailing stops. |
| **Low vol + trend down** | Trend following (short), hedging | Buying dips, grid trading | Less common in crypto. Often precedes capitulation. |
| **High vol + trend up** | Momentum with wide stops, scale-in | Tight stop trend following | Stops get hunted. Use half size, 2x normal stop width. |
| **High vol + trend down** | Short momentum, hedging, cash | Buying dips, mean reversion | Most dangerous. Drawdowns accelerate. Preserve capital. |
| **Low vol + range** | Mean reversion, grid, market making | Trend following, breakout | Bollinger band bounce, RSI mean reversion. High win rate. |
| **High vol + range** | Volatility strategies, wide grids | Tight stops, trend following | Danger zone. Whipsaws destroy both trend and MR strategies. |
| **Transitional** | Reduce size, wait for clarity | Any full-size strategy | Regime shifts cause the biggest losses. Wait for confirmation. |

## Position Sizing by Regime

### Volatility-Adjusted Sizing

Base position size on the inverse of current volatility:

```python
def regime_adjusted_size(
    base_size: float,
    vol_percentile: float,
    adx: float
) -> float:
    """Adjust position size based on regime.

    Args:
        base_size: Normal position size (e.g., 1.0 = 100%).
        vol_percentile: Current ATR percentile (0-1).
        adx: Current ADX value.

    Returns:
        Adjusted position size.
    """
    # Volatility adjustment: scale inversely with vol
    if vol_percentile > 0.80:
        vol_mult = 0.25  # Very high vol: quarter size
    elif vol_percentile > 0.60:
        vol_mult = 0.50  # High vol: half size
    elif vol_percentile < 0.20:
        vol_mult = 1.25  # Very low vol: can go slightly over
    else:
        vol_mult = 1.0   # Normal vol: full size

    # Trend clarity adjustment
    if adx > 30:
        trend_mult = 1.25  # Strong trend: increase size
    elif adx < 15:
        trend_mult = 0.50  # No trend: reduce size
    else:
        trend_mult = 1.0

    return base_size * vol_mult * trend_mult
```

### Sizing Rules of Thumb

| Regime | Size Multiplier | Rationale |
|---|---|---|
| Low vol + strong trend | 1.25–1.50x | Best risk/reward, exploit it |
| Normal vol + trend | 1.0x | Standard sizing |
| High vol + trend | 0.50x | Same direction conviction, more noise |
| Low vol + range | 0.75x | Lower expected return per trade |
| High vol + range | 0.25x | Danger zone, minimal exposure |
| Any transition | 0.25–0.50x | Wait for regime to establish |

## Stop Loss Adaptation

### ATR-Based Stop Scaling

```python
def regime_stop_distance(
    atr: float,
    vol_percentile: float,
    regime: str
) -> float:
    """Compute stop distance adapted to current regime.

    Returns distance in price units.
    """
    if regime == "trending":
        # Wider stops to avoid getting shaken out
        if vol_percentile > 0.70:
            return atr * 3.0  # High vol trend: 3x ATR
        else:
            return atr * 2.0  # Low vol trend: 2x ATR
    else:
        # Range: tighter stops, expect mean reversion
        if vol_percentile > 0.70:
            return atr * 2.5  # High vol range: wide but capped
        else:
            return atr * 1.5  # Low vol range: tight
```

### Stop Adaptation Summary

| Regime | Stop Width (ATR multiples) | Stop Type |
|---|---|---|
| Low vol trend | 2.0x ATR | Trailing stop |
| High vol trend | 3.0x ATR | Trailing stop, wider |
| Low vol range | 1.5x ATR | Fixed stop at range edge |
| High vol range | 2.5x ATR | Fixed stop, or time-based exit |

## Indicator Parameter Adaptation

Adjust indicator lookback periods based on regime speed:

| Parameter | Low Vol / Slow | High Vol / Fast |
|---|---|---|
| EMA fast period | 20 | 8–12 |
| EMA slow period | 50 | 20–30 |
| RSI period | 14 | 7–10 |
| ADX period | 14 | 7–10 |
| ATR period | 14 | 7–10 |
| Bollinger period | 20 | 10–14 |
| Hurst window | 100–200 | 50–100 |

Rationale: High-volatility regimes have faster information incorporation. Longer-period indicators lag too much and generate late signals.

## Regime Transition Signals

Early warning that a regime is about to change:

### Volatility Regime Transitions

- **Low → High vol**: Bollinger Band width expanding rapidly (BB width crosses above 75th percentile from below). ATR increasing 2+ consecutive bars.
- **High → Low vol**: BB squeeze forming. ATR decreasing. Volume declining.

### Trend Regime Transitions

- **Range → Trend**: ADX crossing above 20 from below. Price breaking out of Bollinger Bands. Volume spike (>2x average).
- **Trend → Range**: ADX declining from above 30. DI+ and DI- converging. Hurst dropping toward 0.5.

### Transition Playbook

1. **Detect potential transition** (2+ signals aligning)
2. **Reduce position size to 50%** until new regime confirms
3. **Wait 3–5 bars** for regime to establish (avoid whipsaws)
4. **Switch strategy** only after regime persists for 5+ bars
5. **Never fully switch** on a single bar signal

## PumpFun Micro-Regime Playbook

For new token launches on Solana, regimes compress into minutes/hours.

### Phase Detection

```python
def detect_pump_phase(
    close: pd.Series, volume: pd.Series,
    bars_since_launch: int
) -> str:
    """Identify current micro-regime phase for a new token."""
    recent_return = (close.iloc[-1] / close.iloc[-10] - 1) if len(close) > 10 else 0
    vol_ratio = volume.iloc[-5:].mean() / volume.mean() if len(volume) > 20 else 1

    if bars_since_launch < 20:
        if recent_return > 0.5:  # Up 50%+ in first bars
            return "launch_pump"
        return "launch_uncertain"
    elif bars_since_launch < 60:
        if recent_return < -0.3 and vol_ratio > 1.5:
            return "first_dump"
        elif abs(recent_return) < 0.1 and vol_ratio < 0.5:
            return "consolidation"
        else:
            return "volatile_transition"
    else:
        if recent_return > 0.3 and vol_ratio > 1.0:
            return "second_wave"
        elif recent_return < -0.2:
            return "fading"
        else:
            return "consolidation"
```

### Micro-Regime Actions

| Phase | Action | Position Size | Stop |
|---|---|---|---|
| Launch pump | Don't chase | 0% | — |
| First dump | Watch, don't catch knife | 0% | — |
| Consolidation | Assess holders, volume | Scout (10%) | Below range low |
| Second wave | Enter if volume confirms | 25–50% | Below consolidation low |
| Fading | Avoid | 0% | — |

## Risk Regime Override

Regardless of regime classification, apply these hard overrides:

1. **Drawdown override**: If portfolio down > 5% today, reduce all sizes to 25% regardless of regime
2. **Correlation spike**: If BTC drops > 5% in 1 hour, all altcoin regimes reset to "danger" — everything correlates in crashes
3. **Volume death**: If volume drops below 20th percentile of its own history, treat any trend signal as unreliable
4. **Spread blowout**: If bid-ask spread exceeds 2%, the regime is "illiquid" — reduce size and widen stops regardless
