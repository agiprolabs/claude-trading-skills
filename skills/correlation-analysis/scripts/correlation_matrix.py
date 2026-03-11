#!/usr/bin/env python3
"""Multi-asset correlation matrix analysis with hierarchical clustering.

Fetches historical price data for multiple crypto assets, computes correlation
matrices (Pearson and Spearman), performs hierarchical clustering to identify
asset groups, and reports diversification metrics.

Usage:
    python scripts/correlation_matrix.py --demo
    python scripts/correlation_matrix.py --coins bitcoin,ethereum,solana,cardano

Dependencies:
    uv pip install pandas numpy scipy httpx

Environment Variables:
    None required for demo mode.
"""

import argparse
import sys
import time
from typing import Optional

import httpx
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform


# ── Configuration ───────────────────────────────────────────────────
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DEFAULT_COINS = [
    "bitcoin", "ethereum", "solana", "cardano",
    "avalanche-2", "polkadot", "chainlink", "dogecoin",
]
DAYS = 180
REQUEST_DELAY = 1.5  # CoinGecko free tier rate limit


# ── Data Fetching ───────────────────────────────────────────────────
def fetch_prices(
    coin_id: str,
    days: int = DAYS,
    client: Optional[httpx.Client] = None,
) -> Optional[pd.Series]:
    """Fetch daily closing prices from CoinGecko.

    Args:
        coin_id: CoinGecko coin identifier (e.g., 'bitcoin').
        days: Number of days of history to fetch.
        client: Optional reusable httpx client.

    Returns:
        Series of daily prices indexed by date, or None on failure.
    """
    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval": "daily"}
    try:
        if client:
            resp = client.get(url, params=params, timeout=15)
        else:
            resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        prices = data.get("prices", [])
        if not prices:
            print(f"  Warning: no price data for {coin_id}")
            return None
        series = pd.Series(
            {pd.Timestamp(ts, unit="ms").normalize(): price for ts, price in prices},
            name=coin_id,
        )
        return series
    except httpx.HTTPStatusError as e:
        print(f"  HTTP error fetching {coin_id}: {e.response.status_code}")
        return None
    except Exception as e:
        print(f"  Error fetching {coin_id}: {e}")
        return None


def generate_demo_data(n_assets: int = 8, n_days: int = 180) -> pd.DataFrame:
    """Generate synthetic correlated return data for demo mode.

    Creates assets with realistic crypto correlation structure:
    - A market factor driving all assets
    - Sector factors for subgroups
    - Idiosyncratic noise per asset

    Args:
        n_assets: Number of synthetic assets.
        n_days: Number of days of data.

    Returns:
        DataFrame of daily returns with asset columns.
    """
    rng = np.random.default_rng(42)
    names = ["BTC", "ETH", "SOL", "AVAX", "DOT", "LINK", "DOGE", "SHIB"][:n_assets]

    # Market factor (drives all assets)
    market = rng.normal(0.0005, 0.025, n_days)

    # Sector factors
    l1_factor = rng.normal(0, 0.015, n_days)  # L1 factor
    meme_factor = rng.normal(0, 0.02, n_days)  # Meme factor

    # Asset-specific loadings on factors
    loadings = {
        "BTC":  {"market": 0.85, "l1": 0.10, "meme": 0.00, "idio": 0.015},
        "ETH":  {"market": 0.90, "l1": 0.30, "meme": 0.00, "idio": 0.018},
        "SOL":  {"market": 0.80, "l1": 0.50, "meme": 0.05, "idio": 0.025},
        "AVAX": {"market": 0.75, "l1": 0.45, "meme": 0.00, "idio": 0.022},
        "DOT":  {"market": 0.70, "l1": 0.40, "meme": 0.00, "idio": 0.020},
        "LINK": {"market": 0.65, "l1": 0.20, "meme": 0.00, "idio": 0.020},
        "DOGE": {"market": 0.50, "l1": 0.05, "meme": 0.70, "idio": 0.035},
        "SHIB": {"market": 0.45, "l1": 0.00, "meme": 0.75, "idio": 0.040},
    }

    returns_data: dict[str, np.ndarray] = {}
    for name in names:
        l = loadings[name]
        asset_return = (
            l["market"] * market
            + l["l1"] * l1_factor
            + l["meme"] * meme_factor
            + rng.normal(0, l["idio"], n_days)
        )
        returns_data[name] = asset_return

    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    return pd.DataFrame(returns_data, index=dates)


# ── Correlation Analysis ────────────────────────────────────────────
def compute_correlation_matrices(
    returns: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute Pearson and Spearman correlation matrices.

    Args:
        returns: DataFrame of asset returns.

    Returns:
        Tuple of (pearson_corr, spearman_corr) DataFrames.
    """
    pearson = returns.corr(method="pearson")
    spearman = returns.corr(method="spearman")
    return pearson, spearman


def find_extreme_pairs(
    corr_matrix: pd.DataFrame, n: int = 5
) -> tuple[list[tuple[str, str, float]], list[tuple[str, str, float]]]:
    """Find the most and least correlated pairs.

    Args:
        corr_matrix: Correlation matrix DataFrame.
        n: Number of pairs to return.

    Returns:
        Tuple of (strongest_pairs, weakest_pairs), each a list of
        (asset_a, asset_b, correlation) tuples.
    """
    pairs: list[tuple[str, str, float]] = []
    cols = corr_matrix.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pairs.append((cols[i], cols[j], corr_matrix.iloc[i, j]))

    pairs_sorted = sorted(pairs, key=lambda x: x[2], reverse=True)
    strongest = pairs_sorted[:n]
    weakest = pairs_sorted[-n:]
    return strongest, weakest


# ── Hierarchical Clustering ────────────────────────────────────────
def cluster_assets(
    corr_matrix: pd.DataFrame, max_clusters: int = 5
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Perform hierarchical clustering on assets based on correlation.

    Args:
        corr_matrix: Correlation matrix DataFrame.
        max_clusters: Maximum number of clusters.

    Returns:
        Tuple of (linkage_matrix, distance_matrix, cluster_labels).
    """
    # Convert correlation to distance
    dist_matrix = np.sqrt(2.0 * (1.0 - corr_matrix.values))
    np.fill_diagonal(dist_matrix, 0.0)

    # Ensure symmetry (numerical precision)
    dist_matrix = (dist_matrix + dist_matrix.T) / 2.0

    condensed = squareform(dist_matrix)
    linkage_matrix = linkage(condensed, method="ward")

    # Determine optimal number of clusters (up to max_clusters)
    labels = fcluster(linkage_matrix, t=max_clusters, criterion="maxclust")
    return linkage_matrix, dist_matrix, labels.tolist()


def print_dendrogram_text(
    linkage_matrix: np.ndarray, labels: list[str]
) -> None:
    """Print a text-based representation of the clustering hierarchy.

    Args:
        linkage_matrix: Linkage matrix from scipy.
        labels: Asset names.
    """
    n = len(labels)
    clusters: dict[int, str] = {i: labels[i] for i in range(n)}

    print("\n  Clustering Hierarchy (Ward linkage):")
    print("  " + "-" * 55)
    for i, row in enumerate(linkage_matrix):
        left, right, dist, count = int(row[0]), int(row[1]), row[2], int(row[3])
        left_label = clusters.get(left, f"C{left}")
        right_label = clusters.get(right, f"C{right}")
        merged_label = f"({left_label} + {right_label})"
        clusters[n + i] = merged_label
        print(f"  d={dist:.3f}: {left_label}  <->  {right_label}")
    print()


# ── Diversification Metrics ────────────────────────────────────────
def diversification_metrics(corr_matrix: pd.DataFrame) -> dict[str, float]:
    """Compute portfolio diversification metrics from correlation matrix.

    Args:
        corr_matrix: Correlation matrix DataFrame.

    Returns:
        Dictionary with diversification metrics.
    """
    n = corr_matrix.shape[0]
    corr_values = corr_matrix.values

    # Average pairwise correlation (off-diagonal)
    mask = ~np.eye(n, dtype=bool)
    avg_corr = corr_values[mask].mean()

    # Effective N from average correlation
    if avg_corr < 1.0:
        effective_n_simple = 1.0 / (1.0 / n + (1.0 - 1.0 / n) * avg_corr)
    else:
        effective_n_simple = 1.0

    # Effective N from eigenvalue entropy
    eigenvalues = np.linalg.eigvalsh(corr_values)
    eigenvalues = eigenvalues[eigenvalues > 1e-10]
    proportions = eigenvalues / eigenvalues.sum()
    entropy = -np.sum(proportions * np.log(proportions))
    effective_n_eigen = np.exp(entropy)

    # First eigenvalue dominance (market factor strength)
    eigenvalues_sorted = np.sort(eigenvalues)[::-1]
    first_eigen_pct = eigenvalues_sorted[0] / eigenvalues_sorted.sum() * 100

    return {
        "n_assets": n,
        "avg_pairwise_corr": avg_corr,
        "effective_n_simple": effective_n_simple,
        "effective_n_eigenvalue": effective_n_eigen,
        "first_eigenvalue_pct": first_eigen_pct,
        "max_corr": corr_values[mask].max(),
        "min_corr": corr_values[mask].min(),
    }


# ── Eigenvalue Analysis ────────────────────────────────────────────
def eigenvalue_analysis(corr_matrix: pd.DataFrame) -> None:
    """Print eigenvalue decomposition of correlation matrix.

    Args:
        corr_matrix: Correlation matrix DataFrame.
    """
    eigenvalues, eigenvectors = np.linalg.eigh(corr_matrix.values)
    idx = eigenvalues.argsort()[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    total = eigenvalues.sum()
    cumulative = 0.0

    print("\n  Eigenvalue Decomposition:")
    print("  " + "-" * 55)
    print(f"  {'Factor':<10} {'Eigenvalue':>10} {'% Var':>8} {'Cum %':>8}")
    print("  " + "-" * 55)
    for i, ev in enumerate(eigenvalues):
        pct = ev / total * 100
        cumulative += pct
        label = "Market" if i == 0 else f"Factor {i}"
        print(f"  {label:<10} {ev:>10.3f} {pct:>7.1f}% {cumulative:>7.1f}%")
    print()


# ── Display Functions ───────────────────────────────────────────────
def print_correlation_heatmap(corr_matrix: pd.DataFrame, title: str) -> None:
    """Print a text-based correlation heatmap.

    Args:
        corr_matrix: Correlation matrix DataFrame.
        title: Title for the heatmap.
    """
    labels = corr_matrix.columns.tolist()
    max_label = max(len(l) for l in labels)

    print(f"\n  {title}")
    print("  " + "-" * (max_label + 2 + len(labels) * 7))

    # Header
    header = " " * (max_label + 2)
    for label in labels:
        header += f"{label:>7}"
    print(f"  {header}")

    # Rows
    for i, row_label in enumerate(labels):
        row_str = f"  {row_label:>{max_label}}  "
        for j in range(len(labels)):
            val = corr_matrix.iloc[i, j]
            if i == j:
                row_str += "   1.00"
            elif val >= 0.8:
                row_str += f"  {val:5.2f}"  # Strong positive
            elif val >= 0.5:
                row_str += f"  {val:5.2f}"
            elif val <= -0.3:
                row_str += f" {val:5.2f}"
            else:
                row_str += f"  {val:5.2f}"
        print(row_str)
    print()

    # Legend
    print("  Interpretation: >0.8 strong | 0.5-0.8 moderate | <0.5 weak")


def print_cluster_report(
    labels: list[str], clusters: list[int]
) -> None:
    """Print cluster membership report.

    Args:
        labels: Asset names.
        clusters: Cluster assignment for each asset.
    """
    print("\n  Asset Clusters:")
    print("  " + "-" * 40)
    cluster_map: dict[int, list[str]] = {}
    for asset, cluster in zip(labels, clusters):
        cluster_map.setdefault(cluster, []).append(asset)

    for cluster_id in sorted(cluster_map.keys()):
        members = cluster_map[cluster_id]
        print(f"  Cluster {cluster_id}: {', '.join(members)}")
    print()


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run multi-asset correlation analysis."""
    parser = argparse.ArgumentParser(
        description="Multi-asset correlation matrix analysis"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Use synthetic demo data instead of fetching from API"
    )
    parser.add_argument(
        "--coins", type=str, default=None,
        help="Comma-separated CoinGecko coin IDs (e.g., bitcoin,ethereum,solana)"
    )
    parser.add_argument(
        "--days", type=int, default=DAYS,
        help=f"Days of history (default: {DAYS})"
    )
    args = parser.parse_args()

    print("=" * 65)
    print("  MULTI-ASSET CORRELATION ANALYSIS")
    print("=" * 65)

    if args.demo:
        print("\n  Mode: DEMO (synthetic data)")
        returns = generate_demo_data()
        asset_names = returns.columns.tolist()
    else:
        coins = args.coins.split(",") if args.coins else DEFAULT_COINS
        print(f"\n  Fetching {args.days}d prices for: {', '.join(coins)}")
        print("  (CoinGecko free tier — may be slow due to rate limits)")

        price_data: dict[str, pd.Series] = {}
        with httpx.Client() as client:
            for coin in coins:
                print(f"  Fetching {coin}...", end=" ", flush=True)
                series = fetch_prices(coin, days=args.days, client=client)
                if series is not None:
                    price_data[coin] = series
                    print("OK")
                else:
                    print("FAILED")
                time.sleep(REQUEST_DELAY)

        if len(price_data) < 3:
            print("\n  Error: need at least 3 assets. Try --demo mode.")
            sys.exit(1)

        prices = pd.DataFrame(price_data).dropna()
        returns = prices.pct_change().dropna()
        # Shorten names for display
        name_map = {c: c.upper()[:6] for c in returns.columns}
        returns = returns.rename(columns=name_map)
        asset_names = returns.columns.tolist()

    print(f"\n  Assets: {len(asset_names)}")
    print(f"  Observations: {len(returns)}")
    print(f"  Date range: {returns.index[0].strftime('%Y-%m-%d')} to "
          f"{returns.index[-1].strftime('%Y-%m-%d')}")

    # Compute correlation matrices
    pearson_corr, spearman_corr = compute_correlation_matrices(returns)

    # Display heatmaps
    print_correlation_heatmap(pearson_corr, "Pearson Correlation Matrix")
    print_correlation_heatmap(spearman_corr, "Spearman Rank Correlation Matrix")

    # Strongest and weakest pairs
    strongest, weakest = find_extreme_pairs(pearson_corr)
    print("\n  Strongest Correlated Pairs (Pearson):")
    print("  " + "-" * 40)
    for a, b, corr in strongest:
        print(f"  {a:>6} / {b:<6}  r = {corr:+.3f}")

    print("\n  Weakest Correlated Pairs (Pearson):")
    print("  " + "-" * 40)
    for a, b, corr in weakest:
        print(f"  {a:>6} / {b:<6}  r = {corr:+.3f}")

    # Eigenvalue analysis
    eigenvalue_analysis(pearson_corr)

    # Hierarchical clustering
    linkage_mat, dist_mat, clusters = cluster_assets(pearson_corr)
    print_dendrogram_text(linkage_mat, asset_names)
    print_cluster_report(asset_names, clusters)

    # Diversification metrics
    metrics = diversification_metrics(pearson_corr)
    print("\n  Diversification Metrics:")
    print("  " + "-" * 50)
    print(f"  Number of assets:             {metrics['n_assets']}")
    print(f"  Avg pairwise correlation:     {metrics['avg_pairwise_corr']:.3f}")
    print(f"  Effective N (simple):         {metrics['effective_n_simple']:.1f}")
    print(f"  Effective N (eigenvalue):     {metrics['effective_n_eigenvalue']:.1f}")
    print(f"  Market factor dominance:      {metrics['first_eigenvalue_pct']:.1f}%")
    print(f"  Max pairwise correlation:     {metrics['max_corr']:.3f}")
    print(f"  Min pairwise correlation:     {metrics['min_corr']:.3f}")

    # Assessment
    print("\n  Assessment:")
    print("  " + "-" * 50)
    avg = metrics["avg_pairwise_corr"]
    if avg > 0.7:
        print("  WARNING: High average correlation — portfolio is poorly diversified.")
        print("  Consider adding uncorrelated assets (stablecoins, different sectors).")
    elif avg > 0.4:
        print("  Moderate diversification. Some correlated clusters present.")
        print("  Consider reducing within-cluster allocations.")
    else:
        print("  Good diversification. Assets provide independent return streams.")

    mkt = metrics["first_eigenvalue_pct"]
    if mkt > 70:
        print(f"  Market factor explains {mkt:.0f}% of variance — all assets move together.")
    elif mkt > 50:
        print(f"  Market factor explains {mkt:.0f}% — significant common driver.")

    print("\n  Note: This is analysis output, not financial advice.")
    print("=" * 65)


if __name__ == "__main__":
    main()
