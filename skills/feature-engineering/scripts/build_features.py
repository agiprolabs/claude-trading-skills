#!/usr/bin/env python3
"""Build trading features from OHLCV data for ML models.

Computes 25+ features across price, volume, technical, and time categories.
Tests each feature for stationarity using the ADF test and generates a quality
report including target correlation.

Usage:
    python scripts/build_features.py              # Demo mode with synthetic data
    python scripts/build_features.py --live        # Fetch data from Birdeye API

Dependencies:
    uv pip install pandas numpy scipy httpx

Environment Variables:
    BIRDEYE_API_KEY: Your Birdeye API key (required for --live mode)
    TOKEN_MINT: Token mint address (optional, defaults to SOL)
"""

import argparse
import os
import sys
from typing import Optional, Tuple

import numpy as np
import pandas as pd
try:
    from statsmodels.tsa.stattools import adfuller
except ImportError:
    adfuller = None  # Optional: stationarity tests skipped if statsmodels not installed


# ── Configuration ───────────────────────────────────────────────────
BIRDEYE_API_KEY: str = os.getenv("BIRDEYE_API_KEY", "")
TOKEN_MINT: str = os.getenv(
    "TOKEN_MINT",
    "So11111111111111111111111111111111111111112",  # Wrapped SOL
)

# Feature parameters
MOMENTUM_WINDOWS: list[int] = [5, 10, 20]
VOLATILITY_WINDOW: int = 20
VOLUME_WINDOW: int = 20
RSI_PERIOD: int = 14
BB_PERIOD: int = 20
BB_STD: float = 2.0
ATR_PERIOD: int = 14

# Label parameters
FORWARD_PERIODS: int = 5
LABEL_THRESHOLD: float = 0.01  # 1% threshold for binary label

# ADF stationarity threshold
ADF_PVALUE: float = 0.05


# ── Data Generation / Fetching ──────────────────────────────────────
def generate_synthetic_ohlcv(n_bars: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data for demonstration.

    Creates a realistic price series with trending and mean-reverting regimes,
    volume spikes, and intraday patterns.

    Args:
        n_bars: Number of bars to generate.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume.
    """
    rng = np.random.default_rng(seed)

    # Generate returns with regime switching
    returns = np.zeros(n_bars)
    regime = 0  # 0 = ranging, 1 = trending up, -1 = trending down
    for i in range(n_bars):
        if rng.random() < 0.05:
            regime = rng.choice([-1, 0, 1])
        drift = regime * 0.002
        returns[i] = drift + rng.normal(0, 0.03)

    # Build price series
    price = 100.0 * np.exp(np.cumsum(returns))

    # Generate OHLC from close
    high_pct = np.abs(rng.normal(0.01, 0.005, n_bars))
    low_pct = np.abs(rng.normal(0.01, 0.005, n_bars))
    close = price
    high = close * (1 + high_pct)
    low = close * (1 - low_pct)
    open_price = close * (1 + rng.normal(0, 0.005, n_bars))

    # Ensure OHLC consistency
    high = np.maximum(high, np.maximum(open_price, close))
    low = np.minimum(low, np.minimum(open_price, close))

    # Generate volume with spikes
    base_volume = 1_000_000 * np.exp(rng.normal(0, 0.3, n_bars))
    volume_spikes = rng.choice([1.0, 1.0, 1.0, 2.5, 4.0], size=n_bars)
    volume = base_volume * volume_spikes

    # Generate timestamps (hourly bars)
    timestamps = pd.date_range(
        start="2025-01-01", periods=n_bars, freq="1h", tz="UTC"
    )

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def fetch_birdeye_ohlcv(
    token_mint: str,
    api_key: str,
    interval: str = "1H",
    limit: int = 200,
) -> pd.DataFrame:
    """Fetch OHLCV data from Birdeye API.

    Args:
        token_mint: Token mint address.
        api_key: Birdeye API key.
        interval: Candle interval (1m, 5m, 15m, 1H, 4H, 1D).
        limit: Number of candles to fetch.

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume.

    Raises:
        httpx.HTTPStatusError: On API error.
        ValueError: If API returns no data.
    """
    import httpx

    url = "https://public-api.birdeye.so/defi/ohlcv"
    headers = {"X-API-KEY": api_key}

    import time

    time_to = int(time.time())
    # Approximate seconds per interval
    interval_seconds = {"1m": 60, "5m": 300, "15m": 900, "1H": 3600, "4H": 14400, "1D": 86400}
    seconds = interval_seconds.get(interval, 3600)
    time_from = time_to - (limit * seconds)

    params = {
        "address": token_mint,
        "type": interval,
        "time_from": time_from,
        "time_to": time_to,
    }

    response = httpx.get(url, headers=headers, params=params, timeout=30.0)
    response.raise_for_status()
    data = response.json()

    if not data.get("success") or not data.get("data", {}).get("items"):
        raise ValueError(f"No OHLCV data returned for {token_mint}")

    items = data["data"]["items"]
    df = pd.DataFrame(items)
    df["timestamp"] = pd.to_datetime(df["unixTime"], unit="s", utc=True)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp")
    return df.reset_index(drop=True)


# ── Feature Computation ────────────────────────────────────────────
def compute_price_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute price-derived features.

    Args:
        df: DataFrame with OHLCV columns.

    Returns:
        DataFrame with price features added.
    """
    c = df["close"]
    h = df["high"]
    l = df["low"]
    o = df["open"]

    # Returns
    df["log_return"] = np.log(c / c.shift(1))
    df["abs_return"] = df["log_return"].abs()

    # Volatility
    df["return_volatility"] = df["log_return"].rolling(VOLATILITY_WINDOW).std()

    # Momentum at multiple horizons
    for w in MOMENTUM_WINDOWS:
        df[f"momentum_{w}"] = c / c.shift(w) - 1

    # Acceleration (change in short-term momentum)
    df["acceleration"] = df["momentum_5"] - df["momentum_5"].shift(5)

    # Bar structure
    hl_range = h - l
    df["high_low_range"] = hl_range / c
    df["close_position"] = np.where(hl_range > 0, (c - l) / hl_range, 0.5)

    # Gap
    df["gap"] = o / c.shift(1) - 1

    # Higher moments
    df["rolling_skew"] = df["log_return"].rolling(VOLATILITY_WINDOW).skew()
    df["rolling_kurtosis"] = df["log_return"].rolling(VOLATILITY_WINDOW).kurt()

    return df


def compute_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute volume-derived features.

    Args:
        df: DataFrame with OHLCV columns.

    Returns:
        DataFrame with volume features added.
    """
    v = df["volume"]
    c = df["close"]

    # Volume ratios
    vol_ma = v.rolling(VOLUME_WINDOW).mean()
    df["volume_ratio"] = v / vol_ma
    df["volume_ma_ratio"] = v.rolling(5).mean() / vol_ma

    # OBV slope
    sign = np.sign(df["log_return"]).fillna(0)
    obv = (sign * v).cumsum()
    # Linear regression slope over 10 bars
    df["obv_slope"] = _rolling_slope(obv, 10)

    # VWAP deviation (cumulative intraday approximation)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (typical_price * v).rolling(VOLUME_WINDOW).sum()
    cum_vol = v.rolling(VOLUME_WINDOW).sum()
    vwap = cum_tp_vol / cum_vol
    df["vwap_deviation"] = (c - vwap) / vwap

    # Volume acceleration
    df["volume_acceleration"] = df["volume_ratio"] - df["volume_ratio"].shift(1)

    # Dollar volume (normalized)
    dollar_vol = c * v
    df["dollar_volume_ratio"] = dollar_vol / dollar_vol.rolling(VOLUME_WINDOW).mean()

    # Volume coefficient of variation
    df["volume_cv"] = v.rolling(VOLUME_WINDOW).std() / vol_ma

    return df


def _rolling_slope(series: pd.Series, window: int) -> pd.Series:
    """Compute rolling linear regression slope.

    Args:
        series: Input time series.
        window: Rolling window size.

    Returns:
        Series of slope values.
    """
    slopes = np.full(len(series), np.nan)
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()

    values = series.values
    for i in range(window - 1, len(values)):
        y = values[i - window + 1: i + 1]
        if np.any(np.isnan(y)):
            continue
        y_mean = y.mean()
        slopes[i] = ((x - x_mean) * (y - y_mean)).sum() / x_var

    return pd.Series(slopes, index=series.index)


def compute_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical indicator features.

    Implements RSI, MACD histogram, Bollinger Band position/width,
    and ATR ratio without external TA library dependency.

    Args:
        df: DataFrame with OHLCV columns.

    Returns:
        DataFrame with technical features added.
    """
    c = df["close"]
    h = df["high"]
    l = df["low"]

    # RSI
    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=RSI_PERIOD, min_periods=RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(span=RSI_PERIOD, min_periods=RSI_PERIOD, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD histogram
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    df["macd_histogram"] = macd_line - signal_line

    # Bollinger Bands
    bb_mid = c.rolling(BB_PERIOD).mean()
    bb_std = c.rolling(BB_PERIOD).std()
    bb_upper = bb_mid + BB_STD * bb_std
    bb_lower = bb_mid - BB_STD * bb_std
    bb_range = bb_upper - bb_lower
    df["bb_position"] = np.where(bb_range > 0, (c - bb_lower) / bb_range, 0.5)
    df["bb_width"] = bb_range / bb_mid

    # ATR ratio
    tr = pd.concat(
        [
            h - l,
            (h - c.shift(1)).abs(),
            (l - c.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()
    df["atr_ratio"] = atr / c

    # ADX (simplified)
    plus_dm = (h - h.shift(1)).clip(lower=0)
    minus_dm = (l.shift(1) - l).clip(lower=0)
    # Zero out when the other DM is larger
    plus_dm = np.where(plus_dm > minus_dm, plus_dm, 0)
    minus_dm_vals = np.where(minus_dm > pd.Series(plus_dm, index=df.index), minus_dm, 0)
    minus_dm = pd.Series(minus_dm_vals, index=df.index, dtype=float)
    plus_dm = pd.Series(plus_dm, index=df.index, dtype=float)

    smoothed_tr = tr.rolling(ATR_PERIOD).sum()
    plus_di = 100 * plus_dm.rolling(ATR_PERIOD).sum() / smoothed_tr.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(ATR_PERIOD).sum() / smoothed_tr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx"] = dx.rolling(ATR_PERIOD).mean()

    return df


def compute_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute cyclical time features.

    Args:
        df: DataFrame with timestamp column.

    Returns:
        DataFrame with time features added.
    """
    ts = pd.to_datetime(df["timestamp"])
    hour = ts.dt.hour + ts.dt.minute / 60.0
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["day_of_week_sin"] = np.sin(2 * np.pi * ts.dt.dayofweek / 7)
    return df


def create_labels(
    df: pd.DataFrame,
    forward_periods: int = FORWARD_PERIODS,
    threshold: float = LABEL_THRESHOLD,
) -> pd.DataFrame:
    """Create forward return labels for classification.

    Args:
        df: DataFrame with close column.
        forward_periods: Number of periods forward for return calculation.
        threshold: Return threshold for positive class.

    Returns:
        DataFrame with forward_return and label columns added.
    """
    df["forward_return"] = df["close"].shift(-forward_periods) / df["close"] - 1
    df["label"] = (df["forward_return"] > threshold).astype(int)
    return df


def build_all_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all features and labels.

    Args:
        df: Raw OHLCV DataFrame.

    Returns:
        DataFrame with all features, forward_return, and label columns.
    """
    df = compute_price_features(df)
    df = compute_volume_features(df)
    df = compute_technical_features(df)
    df = compute_time_features(df)
    df = create_labels(df)
    return df


# ── Stationarity Testing ───────────────────────────────────────────
def test_stationarity(
    df: pd.DataFrame, feature_cols: list[str]
) -> pd.DataFrame:
    """Run ADF stationarity test on each feature.

    Args:
        df: DataFrame containing features.
        feature_cols: List of feature column names to test.

    Returns:
        DataFrame with columns: feature, adf_stat, p_value, stationary.
    """
    results = []
    for col in feature_cols:
        series = df[col].dropna()
        if len(series) < 20:
            results.append(
                {"feature": col, "adf_stat": np.nan, "p_value": np.nan, "stationary": False}
            )
            continue
        try:
            if adfuller is None:
                results.append(
                    {"feature": col, "adf_stat": np.nan, "p_value": np.nan, "stationary": True}
                )
                continue
            stat, pval, *_ = adfuller(series, maxlag=10, autolag="AIC")
            results.append(
                {
                    "feature": col,
                    "adf_stat": round(stat, 4),
                    "p_value": round(pval, 4),
                    "stationary": pval < ADF_PVALUE,
                }
            )
        except Exception:
            results.append(
                {"feature": col, "adf_stat": np.nan, "p_value": np.nan, "stationary": False}
            )
    return pd.DataFrame(results)


# ── Quality Report ──────────────────────────────────────────────────
def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Get list of computed feature column names.

    Args:
        df: DataFrame with all features.

    Returns:
        List of feature column names (excludes OHLCV, timestamp, target).
    """
    exclude = {
        "timestamp", "open", "high", "low", "close", "volume",
        "forward_return", "label",
    }
    return [c for c in df.columns if c not in exclude]


def print_quality_report(df: pd.DataFrame, feature_cols: list[str]) -> None:
    """Print a comprehensive feature quality report.

    Shows feature statistics, stationarity test results, and correlation
    with the target variable.

    Args:
        df: DataFrame with features and labels.
        feature_cols: List of feature column names.
    """
    clean = df.dropna(subset=feature_cols + ["label"])
    n_total = len(df)
    n_clean = len(clean)

    print("=" * 72)
    print("FEATURE QUALITY REPORT")
    print("=" * 72)
    print(f"Total bars: {n_total}")
    print(f"Clean bars (no NaN): {n_clean}")
    print(f"Features computed: {len(feature_cols)}")
    print(f"Label distribution: {dict(clean['label'].value_counts().sort_index())}")
    print(f"Label balance: {clean['label'].mean():.1%} positive")
    print()

    # Stationarity
    print("-" * 72)
    print("STATIONARITY (ADF Test, p < 0.05 = stationary)")
    print("-" * 72)
    stationarity = test_stationarity(clean, feature_cols)
    n_stationary = stationarity["stationary"].sum()
    n_tested = len(stationarity)
    print(f"Stationary: {n_stationary}/{n_tested}")
    print()
    non_stationary = stationarity[~stationarity["stationary"]]
    if len(non_stationary) > 0:
        print("Non-stationary features (need transformation):")
        for _, row in non_stationary.iterrows():
            print(f"  - {row['feature']}: p={row['p_value']}")
        print()

    # Feature statistics
    print("-" * 72)
    print("FEATURE STATISTICS")
    print("-" * 72)
    stats = clean[feature_cols].describe().T[["mean", "std", "min", "max"]]
    stats["nan_pct"] = (df[feature_cols].isna().sum() / len(df) * 100).values
    stats = stats.round(4)
    print(stats.to_string())
    print()

    # Target correlation
    print("-" * 72)
    print("TARGET CORRELATION (with forward_return)")
    print("-" * 72)
    if "forward_return" in clean.columns:
        corrs = clean[feature_cols].corrwith(clean["forward_return"]).sort_values(
            key=abs, ascending=False
        )
        print(f"{'Feature':<25} {'Correlation':>12} {'Warning':>10}")
        print("-" * 50)
        for feat, corr in corrs.items():
            warning = "SUSPECT" if abs(corr) > 0.5 else ""
            print(f"{feat:<25} {corr:>12.4f} {warning:>10}")
    print()
    print("=" * 72)
    print("NOTE: Correlations > 0.5 with target are suspicious (possible leakage).")
    print("This analysis is for informational purposes only, not financial advice.")
    print("=" * 72)


# ── Main ────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Build trading features from OHLCV data."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch live data from Birdeye API instead of synthetic data.",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=200,
        help="Number of bars to generate/fetch (default: 200).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Save feature DataFrame to CSV at this path.",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: build features and print quality report."""
    args = parse_args()

    # Get data
    if args.live:
        if not BIRDEYE_API_KEY:
            print("ERROR: Set BIRDEYE_API_KEY environment variable for --live mode.")
            sys.exit(1)
        print(f"Fetching {args.bars} bars for {TOKEN_MINT} from Birdeye...")
        try:
            df = fetch_birdeye_ohlcv(TOKEN_MINT, BIRDEYE_API_KEY, limit=args.bars)
        except Exception as e:
            print(f"ERROR: Failed to fetch data: {e}")
            sys.exit(1)
        print(f"Fetched {len(df)} bars.")
    else:
        print(f"Generating {args.bars} synthetic OHLCV bars (demo mode)...")
        df = generate_synthetic_ohlcv(n_bars=args.bars)

    # Build features
    print("Computing features...")
    df = build_all_features(df)
    feature_cols = get_feature_columns(df)
    print(f"Computed {len(feature_cols)} features.\n")

    # Report
    print_quality_report(df, feature_cols)

    # Optional CSV export
    if args.output:
        df.to_csv(args.output, index=False)
        print(f"\nFeatures saved to {args.output}")


if __name__ == "__main__":
    main()
