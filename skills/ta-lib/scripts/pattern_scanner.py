#!/usr/bin/env python3
"""Scan OHLCV data for candlestick patterns using TA-Lib.

Detects all 61 TA-Lib candlestick patterns on synthetic or provided data.
Falls back to manual detection of doji, hammer, and engulfing patterns
when TA-Lib is not installed.

Usage:
    python scripts/pattern_scanner.py
    python scripts/pattern_scanner.py --demo
    python scripts/pattern_scanner.py --bars 1000

Dependencies:
    uv pip install numpy pandas
    Optional: uv pip install TA-Lib  (requires C library)
"""

import argparse
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── TA-Lib Import (optional) ───────────────────────────────────────
TALIB_AVAILABLE = False
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    pass


# ── Data Classes ───────────────────────────────────────────────────

@dataclass
class PatternDetection:
    """A single pattern detection on a specific bar."""
    bar_index: int
    value: int  # +100 bullish, -100 bearish
    close_price: float


@dataclass
class PatternResult:
    """Results for a single pattern type across all bars."""
    name: str
    display_name: str
    detections: List[PatternDetection] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Total number of detections."""
        return len(self.detections)

    @property
    def bullish_count(self) -> int:
        """Number of bullish detections."""
        return sum(1 for d in self.detections if d.value > 0)

    @property
    def bearish_count(self) -> int:
        """Number of bearish detections."""
        return sum(1 for d in self.detections if d.value < 0)


# ── Synthetic Data with Clear Patterns ─────────────────────────────

def generate_pattern_data(bars: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data that contains clear candlestick patterns.

    Embeds specific pattern structures (doji, hammer, engulfing) at known
    positions so the scanner can demonstrate detection.

    Args:
        bars: Number of bars to generate.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: open, high, low, close, volume.
    """
    rng = np.random.default_rng(seed)

    # Base price movement
    returns = rng.normal(0, 0.015, bars)
    close = 100.0 * np.exp(np.cumsum(returns))

    spread = close * 0.015
    high = close + np.abs(rng.normal(0, 1, bars)) * spread
    low = close - np.abs(rng.normal(0, 1, bars)) * spread
    open_ = close + rng.normal(0, 0.5, bars) * spread

    # Ensure OHLC consistency
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    volume = (100_000 * (1 + 3 * np.abs(returns))).astype(np.float64)

    # ── Embed clear patterns ───────────────────────────────────
    # Doji patterns: open ~= close, with wicks
    doji_bars = [50, 150, 250, 350, 450]
    for i in doji_bars:
        if i < bars:
            mid = close[i]
            open_[i] = mid * 1.0005
            close[i] = mid * 0.9995
            high[i] = mid * 1.015
            low[i] = mid * 0.985

    # Hammer patterns: small body at top, long lower wick
    hammer_bars = [75, 175, 275, 375]
    for i in hammer_bars:
        if i < bars:
            body_top = close[i]
            body_size = body_top * 0.003
            open_[i] = body_top - body_size
            close[i] = body_top
            high[i] = body_top + body_size * 0.5
            low[i] = body_top - body_size * 4  # Long lower wick

    # Bullish engulfing: small bearish bar followed by large bullish bar
    engulfing_bars = [100, 200, 300, 400]
    for i in engulfing_bars:
        if i + 1 < bars:
            mid = close[i]
            # Bar i: small bearish
            open_[i] = mid * 1.002
            close[i] = mid * 0.998
            high[i] = mid * 1.003
            low[i] = mid * 0.997
            # Bar i+1: large bullish engulfing
            open_[i + 1] = mid * 0.996
            close[i + 1] = mid * 1.005
            high[i + 1] = mid * 1.006
            low[i + 1] = mid * 0.995

    # Shooting star: small body at bottom, long upper wick
    shooting_bars = [125, 225, 325]
    for i in shooting_bars:
        if i < bars:
            body_bottom = close[i]
            body_size = body_bottom * 0.003
            open_[i] = body_bottom + body_size
            close[i] = body_bottom
            high[i] = body_bottom + body_size * 4  # Long upper wick
            low[i] = body_bottom - body_size * 0.5

    # Re-enforce OHLC consistency after pattern embedding
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


# ── TA-Lib Pattern Scanner ─────────────────────────────────────────

# Display names for TA-Lib candlestick functions
PATTERN_DISPLAY_NAMES: Dict[str, str] = {
    "CDL2CROWS": "Two Crows",
    "CDL3BLACKCROWS": "Three Black Crows",
    "CDL3INSIDE": "Three Inside Up/Down",
    "CDL3LINESTRIKE": "Three-Line Strike",
    "CDL3OUTSIDE": "Three Outside Up/Down",
    "CDL3STARSINSOUTH": "Three Stars in the South",
    "CDL3WHITESOLDIERS": "Three White Soldiers",
    "CDLABANDONEDBABY": "Abandoned Baby",
    "CDLADVANCEBLOCK": "Advance Block",
    "CDLBELTHOLD": "Belt Hold",
    "CDLBREAKAWAY": "Breakaway",
    "CDLCLOSINGMARUBOZU": "Closing Marubozu",
    "CDLCONCEALBABYSWALL": "Concealing Baby Swallow",
    "CDLCOUNTERATTACK": "Counterattack",
    "CDLDARKCLOUDCOVER": "Dark Cloud Cover",
    "CDLDOJI": "Doji",
    "CDLDOJISTAR": "Doji Star",
    "CDLDRAGONFLYDOJI": "Dragonfly Doji",
    "CDLENGULFING": "Engulfing",
    "CDLEVENINGDOJISTAR": "Evening Doji Star",
    "CDLEVENINGSTAR": "Evening Star",
    "CDLGAPSIDESIDEWHITE": "Gap Side-by-Side White",
    "CDLGRAVESTONEDOJI": "Gravestone Doji",
    "CDLHAMMER": "Hammer",
    "CDLHANGINGMAN": "Hanging Man",
    "CDLHARAMI": "Harami",
    "CDLHARAMICROSS": "Harami Cross",
    "CDLHIGHWAVE": "High Wave",
    "CDLHIKKAKE": "Hikkake",
    "CDLHIKKAKEMOD": "Modified Hikkake",
    "CDLHOMINGPIGEON": "Homing Pigeon",
    "CDLIDENTICAL3CROWS": "Identical Three Crows",
    "CDLINNECK": "In-Neck",
    "CDLINVERTEDHAMMER": "Inverted Hammer",
    "CDLKICKING": "Kicking",
    "CDLKICKINGBYLENGTH": "Kicking by Length",
    "CDLLADDERBOTTOM": "Ladder Bottom",
    "CDLLONGLEGGEDDOJI": "Long-Legged Doji",
    "CDLLONGLINE": "Long Line",
    "CDLMARUBOZU": "Marubozu",
    "CDLMATCHINGLOW": "Matching Low",
    "CDLMATHOLD": "Mat Hold",
    "CDLMORNINGDOJISTAR": "Morning Doji Star",
    "CDLMORNINGSTAR": "Morning Star",
    "CDLONNECK": "On-Neck",
    "CDLPIERCING": "Piercing",
    "CDLRICKSHAWMAN": "Rickshaw Man",
    "CDLRISEFALL3METHODS": "Rising/Falling Three Methods",
    "CDLSEPARATINGLINES": "Separating Lines",
    "CDLSHOOTINGSTAR": "Shooting Star",
    "CDLSHORTLINE": "Short Line",
    "CDLSPINNINGTOP": "Spinning Top",
    "CDLSTALLEDPATTERN": "Stalled Pattern",
    "CDLSTICKSANDWICH": "Stick Sandwich",
    "CDLTAKURI": "Takuri",
    "CDLTASUKIGAP": "Tasuki Gap",
    "CDLTHRUSTING": "Thrusting",
    "CDLTRISTAR": "Tri-Star",
    "CDLUNIQUE3RIVER": "Unique Three River",
    "CDLXSIDEGAP3METHODS": "Side Gap Three Methods",
}


def scan_talib_patterns(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> List[PatternResult]:
    """Scan for all 61 TA-Lib candlestick patterns.

    Args:
        open_: Open price array (float64).
        high: High price array (float64).
        low: Low price array (float64).
        close: Close price array (float64).

    Returns:
        List of PatternResult for patterns with at least one detection.
    """
    candle_funcs = talib.get_function_groups()["Pattern Recognition"]
    results: List[PatternResult] = []

    for func_name in candle_funcs:
        func = getattr(talib, func_name)
        output = func(open_, high, low, close)
        hits = np.nonzero(output)[0]

        if len(hits) > 0:
            display = PATTERN_DISPLAY_NAMES.get(func_name, func_name)
            pr = PatternResult(name=func_name, display_name=display)
            for idx in hits:
                pr.detections.append(PatternDetection(
                    bar_index=int(idx),
                    value=int(output[idx]),
                    close_price=float(close[idx]),
                ))
            results.append(pr)

    # Sort by detection count descending
    results.sort(key=lambda r: r.count, reverse=True)
    return results


# ── Manual Pattern Detection (Fallback) ────────────────────────────

def detect_doji(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    body_threshold: float = 0.001,
) -> np.ndarray:
    """Detect doji patterns: open ~= close with visible wicks.

    A doji has a very small body relative to its total range,
    indicating indecision.

    Args:
        open_: Open prices.
        high: High prices.
        low: Low prices.
        close: Close prices.
        body_threshold: Max body/range ratio to qualify as doji.

    Returns:
        Array with +100 where doji detected, 0 otherwise.
    """
    n = len(close)
    result = np.zeros(n, dtype=np.int32)
    for i in range(n):
        total_range = high[i] - low[i]
        if total_range == 0:
            continue
        body = abs(close[i] - open_[i])
        body_ratio = body / total_range
        if body_ratio <= body_threshold and total_range > close[i] * 0.005:
            result[i] = 100
    return result


def detect_hammer(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    lower_wick_ratio: float = 2.0,
) -> np.ndarray:
    """Detect hammer patterns: small body at top, long lower shadow.

    A hammer has a lower wick at least N times the body size, with
    minimal upper wick.

    Args:
        open_: Open prices.
        high: High prices.
        low: Low prices.
        close: Close prices.
        lower_wick_ratio: Min ratio of lower wick to body.

    Returns:
        Array with +100 where bullish hammer detected, 0 otherwise.
    """
    n = len(close)
    result = np.zeros(n, dtype=np.int32)
    for i in range(n):
        body = abs(close[i] - open_[i])
        if body == 0:
            continue
        body_top = max(open_[i], close[i])
        body_bottom = min(open_[i], close[i])
        lower_wick = body_bottom - low[i]
        upper_wick = high[i] - body_top

        # Hammer: long lower wick, short upper wick, small body
        if (lower_wick >= lower_wick_ratio * body
                and upper_wick <= body * 0.5):
            result[i] = 100
    return result


def detect_shooting_star(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    upper_wick_ratio: float = 2.0,
) -> np.ndarray:
    """Detect shooting star patterns: small body at bottom, long upper shadow.

    Args:
        open_: Open prices.
        high: High prices.
        low: Low prices.
        close: Close prices.
        upper_wick_ratio: Min ratio of upper wick to body.

    Returns:
        Array with -100 where shooting star detected, 0 otherwise.
    """
    n = len(close)
    result = np.zeros(n, dtype=np.int32)
    for i in range(n):
        body = abs(close[i] - open_[i])
        if body == 0:
            continue
        body_top = max(open_[i], close[i])
        body_bottom = min(open_[i], close[i])
        upper_wick = high[i] - body_top
        lower_wick = body_bottom - low[i]

        if (upper_wick >= upper_wick_ratio * body
                and lower_wick <= body * 0.5):
            result[i] = -100
    return result


def detect_engulfing(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> np.ndarray:
    """Detect bullish and bearish engulfing patterns.

    Bullish engulfing: bearish bar followed by bullish bar whose body
    completely engulfs the prior bar's body.
    Bearish engulfing: bullish bar followed by bearish bar that engulfs.

    Args:
        open_: Open prices.
        high: High prices.
        low: Low prices.
        close: Close prices.

    Returns:
        Array with +100 (bullish) or -100 (bearish) engulfing, 0 otherwise.
    """
    n = len(close)
    result = np.zeros(n, dtype=np.int32)
    for i in range(1, n):
        prev_body_top = max(open_[i - 1], close[i - 1])
        prev_body_bot = min(open_[i - 1], close[i - 1])
        curr_body_top = max(open_[i], close[i])
        curr_body_bot = min(open_[i], close[i])

        prev_bearish = close[i - 1] < open_[i - 1]
        prev_bullish = close[i - 1] > open_[i - 1]
        curr_bearish = close[i] < open_[i]
        curr_bullish = close[i] > open_[i]

        # Bullish engulfing: prev bearish, current bullish, engulfs
        if (prev_bearish and curr_bullish
                and curr_body_bot <= prev_body_bot
                and curr_body_top >= prev_body_top
                and (curr_body_top - curr_body_bot) > (prev_body_top - prev_body_bot)):
            result[i] = 100

        # Bearish engulfing: prev bullish, current bearish, engulfs
        elif (prev_bullish and curr_bearish
              and curr_body_bot <= prev_body_bot
              and curr_body_top >= prev_body_top
              and (curr_body_top - curr_body_bot) > (prev_body_top - prev_body_bot)):
            result[i] = -100

    return result


def scan_manual_patterns(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> List[PatternResult]:
    """Scan using manual fallback pattern detection.

    Detects doji, hammer, shooting star, and engulfing patterns
    without TA-Lib.

    Args:
        open_: Open prices.
        high: High prices.
        low: Low prices.
        close: Close prices.

    Returns:
        List of PatternResult for detected patterns.
    """
    manual_scanners = [
        ("CDLDOJI", "Doji (manual)", detect_doji),
        ("CDLHAMMER", "Hammer (manual)", detect_hammer),
        ("CDLSHOOTINGSTAR", "Shooting Star (manual)", detect_shooting_star),
        ("CDLENGULFING", "Engulfing (manual)", detect_engulfing),
    ]

    results: List[PatternResult] = []
    for name, display, func in manual_scanners:
        output = func(open_, high, low, close)
        hits = np.nonzero(output)[0]
        if len(hits) > 0:
            pr = PatternResult(name=name, display_name=display)
            for idx in hits:
                pr.detections.append(PatternDetection(
                    bar_index=int(idx),
                    value=int(output[idx]),
                    close_price=float(close[idx]),
                ))
            results.append(pr)

    results.sort(key=lambda r: r.count, reverse=True)
    return results


# ── Display Functions ──────────────────────────────────────────────

def print_pattern_summary(results: List[PatternResult], bars: int) -> None:
    """Print a summary table of all detected patterns.

    Args:
        results: List of PatternResult objects.
        bars: Total number of bars scanned.
    """
    total_detections = sum(r.count for r in results)
    print(f"\n{'='*70}")
    print(f"Pattern Scan Summary — {bars} bars, "
          f"{len(results)} pattern types, {total_detections} total detections")
    print(f"{'='*70}")

    if not results:
        print("No patterns detected.")
        return

    print(f"{'Pattern':<35} {'Total':>6} {'Bull':>6} {'Bear':>6}")
    print(f"{'-'*35} {'-'*6} {'-'*6} {'-'*6}")

    for r in results:
        print(f"{r.display_name:<35} {r.count:>6} "
              f"{r.bullish_count:>6} {r.bearish_count:>6}")

    print(f"{'-'*35} {'-'*6} {'-'*6} {'-'*6}")
    total_bull = sum(r.bullish_count for r in results)
    total_bear = sum(r.bearish_count for r in results)
    print(f"{'TOTAL':<35} {total_detections:>6} {total_bull:>6} {total_bear:>6}")


def print_recent_detections(
    results: List[PatternResult],
    n_recent: int = 10,
) -> None:
    """Print the N most recent pattern detections across all patterns.

    Args:
        results: List of PatternResult objects.
        n_recent: Number of recent detections to show.
    """
    # Flatten all detections with pattern name
    all_detections: List[Tuple[str, PatternDetection]] = []
    for r in results:
        for d in r.detections:
            all_detections.append((r.display_name, d))

    # Sort by bar index descending
    all_detections.sort(key=lambda x: x[1].bar_index, reverse=True)
    recent = all_detections[:n_recent]

    print(f"\n{'='*70}")
    print(f"Most Recent {min(n_recent, len(recent))} Detections")
    print(f"{'='*70}")

    if not recent:
        print("No detections to display.")
        return

    print(f"{'Bar':>6} {'Pattern':<35} {'Signal':>8} {'Price':>12}")
    print(f"{'-'*6} {'-'*35} {'-'*8} {'-'*12}")

    for name, det in recent:
        signal = "BULL" if det.value > 0 else "BEAR"
        color_signal = f"+{det.value}" if det.value > 0 else str(det.value)
        print(f"{det.bar_index:>6} {name:<35} {color_signal:>8} "
              f"{det.close_price:>12.4f}")


def print_pattern_distribution(results: List[PatternResult], bars: int) -> None:
    """Print where patterns cluster in the data.

    Args:
        results: List of PatternResult objects.
        bars: Total number of bars.
    """
    if not results:
        return

    # Divide into quartiles
    q_size = bars // 4
    quartile_counts = [0, 0, 0, 0]

    for r in results:
        for d in r.detections:
            q = min(d.bar_index // q_size, 3)
            quartile_counts[q] += 1

    total = sum(quartile_counts)
    if total == 0:
        return

    print(f"\n--- Pattern Distribution by Quarter ---")
    labels = ["Q1 (oldest)", "Q2", "Q3", "Q4 (newest)"]
    for i, label in enumerate(labels):
        pct = quartile_counts[i] / total * 100 if total > 0 else 0
        bar = "#" * int(pct / 2)
        print(f"  {label:<15} {quartile_counts[i]:>4} ({pct:>5.1f}%) {bar}")


# ── Main ───────────────────────────────────────────────────────────

def main() -> None:
    """Entry point: generate data, scan patterns, display results."""
    parser = argparse.ArgumentParser(
        description="Scan OHLCV data for candlestick patterns."
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run demo with synthetic data containing embedded patterns."
    )
    parser.add_argument(
        "--bars", type=int, default=500,
        help="Number of OHLCV bars to generate (default: 500)."
    )
    parser.add_argument(
        "--recent", type=int, default=15,
        help="Number of recent detections to display (default: 15)."
    )
    args = parser.parse_args()

    bars = args.bars
    print(f"TA-Lib available: {TALIB_AVAILABLE}")
    print(f"Generating {bars} bars of synthetic OHLCV data with embedded patterns...")

    df = generate_pattern_data(bars=bars)
    open_ = df["open"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    close = df["close"].values.astype(np.float64)

    print(f"Price range: {close.min():.2f} - {close.max():.2f}")

    if TALIB_AVAILABLE:
        print(f"\nScanning all 61 TA-Lib candlestick patterns...")
        results = scan_talib_patterns(open_, high, low, close)
    else:
        print(f"\nTA-Lib not installed. Using manual fallback for 4 patterns.")
        print("Install TA-Lib for all 61 patterns:")
        print("  brew install ta-lib && uv pip install TA-Lib")
        results = scan_manual_patterns(open_, high, low, close)

    print_pattern_summary(results, bars)
    print_recent_detections(results, n_recent=args.recent)
    print_pattern_distribution(results, bars)

    # If both available, compare
    if TALIB_AVAILABLE:
        print(f"\n--- Manual Fallback Comparison ---")
        manual_results = scan_manual_patterns(open_, high, low, close)
        for mr in manual_results:
            # Find corresponding TA-Lib result
            talib_match = next((r for r in results if r.name == mr.name), None)
            talib_count = talib_match.count if talib_match else 0
            print(f"  {mr.display_name:<35} manual={mr.count:>4}, "
                  f"talib={talib_count:>4}")

    print("\nNote: This is synthetic data for demonstration purposes only.")
    print("Not financial advice. Use with real market data for actual analysis.")


if __name__ == "__main__":
    main()
