#!/usr/bin/env python3
"""Volatility forecasting using EWMA and GARCH(1,1) models.

Fits an EWMA model and a GARCH(1,1) model via maximum likelihood estimation,
then produces multi-horizon volatility forecasts and a volatility term
structure comparison.

Usage:
    python scripts/vol_forecast.py              # demo mode
    python scripts/vol_forecast.py --live       # live data via Birdeye

Dependencies:
    uv pip install pandas numpy scipy httpx

Environment Variables:
    BIRDEYE_API_KEY: Birdeye API key (required only with --live)
    TOKEN_MINT: Solana token mint address (optional, defaults to SOL)
"""

import argparse
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize


# ── Configuration ───────────────────────────────────────────────────
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")
DEFAULT_MINT = os.getenv(
    "TOKEN_MINT",
    "So11111111111111111111111111111111111111112",
)
ANNUALIZATION_FACTOR = 365
EWMA_LAMBDA = 0.94
FORECAST_HORIZONS = [1, 7, 14, 30, 60, 90]


# ── Data Loading ────────────────────────────────────────────────────
def generate_demo_returns(n_days: int = 500, seed: int = 42) -> pd.Series:
    """Generate synthetic log returns with GARCH-like volatility clustering.

    Creates returns from a known GARCH(1,1) process so we can verify
    that our estimation recovers the true parameters.

    True parameters: omega=0.000005, alpha=0.10, beta=0.85

    Args:
        n_days: Number of daily returns.
        seed: Random seed.

    Returns:
        Series of daily log returns.
    """
    rng = np.random.default_rng(seed)

    # True GARCH parameters
    omega = 0.000005
    alpha = 0.10
    beta = 0.85

    returns = np.zeros(n_days)
    sigma2 = np.zeros(n_days)
    sigma2[0] = omega / (1 - alpha - beta)  # unconditional variance

    for t in range(1, n_days):
        sigma2[t] = omega + alpha * returns[t - 1] ** 2 + beta * sigma2[t - 1]
        returns[t] = rng.normal(0, np.sqrt(sigma2[t]))

    dates = pd.date_range("2024-03-01", periods=n_days, freq="D")
    return pd.Series(returns, index=dates, name="log_return")


def fetch_live_returns(mint: str, days: int = 500) -> pd.Series:
    """Fetch daily returns from Birdeye.

    Args:
        mint: Solana token mint address.
        days: Number of days.

    Returns:
        Series of daily log returns.
    """
    if not BIRDEYE_API_KEY:
        print("Error: Set BIRDEYE_API_KEY for live data.")
        sys.exit(1)

    try:
        import httpx
    except ImportError:
        print("Error: httpx required. Install with: uv pip install httpx")
        sys.exit(1)

    import time

    time_to = int(time.time())
    time_from = time_to - days * 86400

    url = "https://public-api.birdeye.so/defi/ohlcv"
    params = {"address": mint, "type": "1D", "time_from": time_from, "time_to": time_to}
    headers = {"X-API-KEY": BIRDEYE_API_KEY}

    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        print(f"API error: {e.response.status_code}")
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        sys.exit(1)

    items = data.get("data", {}).get("items", [])
    if not items:
        print("No data returned.")
        sys.exit(1)

    closes = []
    dates = []
    for item in sorted(items, key=lambda x: x["unixTime"]):
        closes.append(float(item["c"]))
        dates.append(pd.Timestamp(item["unixTime"], unit="s"))

    prices = pd.Series(closes, index=dates)
    log_ret = np.log(prices / prices.shift(1)).dropna()
    log_ret.name = "log_return"
    return log_ret


# ── EWMA Model ──────────────────────────────────────────────────────
class EWMAModel:
    """Exponentially Weighted Moving Average volatility model.

    Attributes:
        lam: Decay factor (0 < lam < 1).
        variance: Fitted variance series.
        current_var: Most recent variance estimate.
    """

    def __init__(self, lam: float = EWMA_LAMBDA) -> None:
        self.lam = lam
        self.variance: Optional[np.ndarray] = None
        self.current_var: float = 0.0

    def fit(self, returns: pd.Series) -> None:
        """Fit EWMA to return series.

        Args:
            returns: Series of log returns.
        """
        r = returns.values
        n = len(r)
        var = np.zeros(n)

        # Initialize with sample variance of first 20 obs
        init_n = min(20, n)
        var[0] = np.var(r[:init_n])

        for t in range(1, n):
            var[t] = self.lam * var[t - 1] + (1 - self.lam) * r[t - 1] ** 2

        self.variance = var
        self.current_var = var[-1]

    def forecast(self, horizons: list[int]) -> dict[int, float]:
        """Forecast annualized volatility at multiple horizons.

        EWMA forecast is flat — the current estimate is the forecast for
        all horizons.

        Args:
            horizons: List of forecast horizons in days.

        Returns:
            Dict mapping horizon to annualized vol forecast.
        """
        forecasts = {}
        for h in horizons:
            # EWMA forecast is constant (no mean reversion)
            daily_vol = np.sqrt(self.current_var)
            ann_vol = daily_vol * np.sqrt(ANNUALIZATION_FACTOR)
            forecasts[h] = ann_vol
        return forecasts

    @property
    def half_life(self) -> float:
        """Half-life of the EWMA in periods."""
        return -np.log(2) / np.log(self.lam)


# ── GARCH(1,1) Model ───────────────────────────────────────────────
class GARCHModel:
    """GARCH(1,1) model fitted via maximum likelihood.

    σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}

    Attributes:
        omega: Intercept.
        alpha: ARCH coefficient (shock reaction).
        beta: GARCH coefficient (persistence).
        variance: Fitted conditional variance series.
        current_var: Most recent conditional variance.
        log_likelihood: Maximized log-likelihood value.
    """

    def __init__(self) -> None:
        self.omega: float = 0.0
        self.alpha: float = 0.0
        self.beta: float = 0.0
        self.variance: Optional[np.ndarray] = None
        self.current_var: float = 0.0
        self.log_likelihood: float = 0.0

    def _compute_variance(
        self, returns: np.ndarray, omega: float, alpha: float, beta: float
    ) -> np.ndarray:
        """Compute conditional variance series given parameters.

        Args:
            returns: Array of log returns.
            omega: Intercept parameter.
            alpha: ARCH parameter.
            beta: GARCH parameter.

        Returns:
            Array of conditional variances.
        """
        n = len(returns)
        var = np.zeros(n)

        # Initialize at unconditional variance
        persistence = alpha + beta
        if persistence < 1.0 and persistence > 0:
            var[0] = omega / (1 - persistence)
        else:
            var[0] = np.var(returns)

        for t in range(1, n):
            var[t] = omega + alpha * returns[t - 1] ** 2 + beta * var[t - 1]
            var[t] = max(var[t], 1e-12)  # numerical floor

        return var

    def _neg_log_likelihood(self, params: np.ndarray, returns: np.ndarray) -> float:
        """Negative Gaussian log-likelihood for GARCH(1,1).

        Args:
            params: Array [omega, alpha, beta].
            returns: Array of log returns.

        Returns:
            Negative log-likelihood (to minimize).
        """
        omega, alpha, beta = params

        # Parameter validity
        if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1.0:
            return 1e10

        var = self._compute_variance(returns, omega, alpha, beta)

        # Gaussian log-likelihood: -0.5 * Σ [ln(σ²) + r²/σ²]
        ll = -0.5 * np.sum(np.log(var) + returns**2 / var)

        if np.isnan(ll) or np.isinf(ll):
            return 1e10

        return -ll  # negative for minimization

    def fit(self, returns: pd.Series) -> bool:
        """Fit GARCH(1,1) via maximum likelihood.

        Args:
            returns: Series of log returns.

        Returns:
            True if optimization converged, False otherwise.
        """
        r = returns.values
        sample_var = np.var(r)

        # Initial guess: typical crypto parameters
        x0 = np.array([
            sample_var * 0.04,  # omega
            0.08,               # alpha
            0.88,               # beta
        ])

        # Bounds
        bounds = [
            (1e-10, sample_var * 10),  # omega
            (1e-4, 0.5),               # alpha
            (0.3, 0.999),              # beta
        ]

        # Constraint: alpha + beta < 1
        constraints = {
            "type": "ineq",
            "fun": lambda p: 0.9999 - p[1] - p[2],
        }

        try:
            result = minimize(
                self._neg_log_likelihood,
                x0,
                args=(r,),
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": 500, "ftol": 1e-10},
            )
        except Exception as e:
            print(f"  GARCH optimization failed: {e}")
            return False

        if not result.success:
            print(f"  GARCH warning: optimizer did not converge ({result.message})")

        self.omega, self.alpha, self.beta = result.x
        self.log_likelihood = -result.fun
        self.variance = self._compute_variance(r, self.omega, self.alpha, self.beta)
        self.current_var = self.variance[-1]

        return True

    @property
    def persistence(self) -> float:
        """Total persistence α + β."""
        return self.alpha + self.beta

    @property
    def long_run_variance(self) -> float:
        """Unconditional (long-run) variance ω / (1 - α - β)."""
        denom = 1 - self.persistence
        if denom <= 0:
            return self.current_var
        return self.omega / denom

    @property
    def long_run_vol_annual(self) -> float:
        """Annualized long-run volatility."""
        return np.sqrt(self.long_run_variance) * np.sqrt(ANNUALIZATION_FACTOR)

    @property
    def half_life(self) -> float:
        """Half-life of vol shocks in days."""
        if self.persistence <= 0 or self.persistence >= 1:
            return float("inf")
        return -np.log(2) / np.log(self.persistence)

    def forecast(self, horizons: list[int]) -> dict[int, float]:
        """Multi-horizon annualized volatility forecast.

        Uses the GARCH term structure formula:
        σ²_{t+h} = V_L + (α+β)^h × (σ²_t - V_L)

        Args:
            horizons: List of forecast horizons in days.

        Returns:
            Dict mapping horizon to annualized vol forecast.
        """
        vl = self.long_run_variance
        persistence = self.persistence
        forecasts = {}

        for h in horizons:
            if persistence >= 1.0:
                forecast_var = self.current_var
            else:
                forecast_var = vl + (persistence ** h) * (self.current_var - vl)
            forecast_var = max(forecast_var, 1e-12)
            ann_vol = np.sqrt(forecast_var) * np.sqrt(ANNUALIZATION_FACTOR)
            forecasts[h] = ann_vol

        return forecasts


# ── Reporting ───────────────────────────────────────────────────────
def print_model_params(ewma: EWMAModel, garch: GARCHModel) -> None:
    """Print fitted model parameters.

    Args:
        ewma: Fitted EWMA model.
        garch: Fitted GARCH model.
    """
    print(f"\n{'=' * 55}")
    print("  MODEL PARAMETERS")
    print(f"{'=' * 55}")

    print("\n  EWMA:")
    print(f"    Lambda:          {ewma.lam:.4f}")
    print(f"    Half-life:       {ewma.half_life:.1f} days")
    print(f"    Current vol:     {np.sqrt(ewma.current_var) * np.sqrt(ANNUALIZATION_FACTOR) * 100:.1f}% ann.")

    print("\n  GARCH(1,1):")
    print(f"    omega:           {garch.omega:.8f}")
    print(f"    alpha:           {garch.alpha:.4f}")
    print(f"    beta:            {garch.beta:.4f}")
    print(f"    Persistence:     {garch.persistence:.4f}")
    print(f"    Half-life:       {garch.half_life:.1f} days")
    print(f"    Long-run vol:    {garch.long_run_vol_annual * 100:.1f}% ann.")
    print(f"    Current vol:     {np.sqrt(garch.current_var) * np.sqrt(ANNUALIZATION_FACTOR) * 100:.1f}% ann.")
    print(f"    Log-likelihood:  {garch.log_likelihood:.2f}")


def print_forecast_comparison(
    ewma_fc: dict[int, float], garch_fc: dict[int, float]
) -> None:
    """Print side-by-side forecast comparison.

    Args:
        ewma_fc: EWMA forecasts by horizon.
        garch_fc: GARCH forecasts by horizon.
    """
    print(f"\n{'=' * 55}")
    print("  VOLATILITY FORECASTS (Annualized)")
    print(f"{'=' * 55}")
    print(f"  {'Horizon':>10}  {'EWMA':>10}  {'GARCH':>10}  {'Diff':>10}")
    print(f"  {'-' * 42}")

    for h in sorted(ewma_fc.keys()):
        e = ewma_fc[h] * 100
        g = garch_fc[h] * 100
        d = g - e
        print(f"  {h:>8}d  {e:>9.1f}%  {g:>9.1f}%  {d:>+9.1f}%")


def print_term_structure(garch: GARCHModel) -> None:
    """Print GARCH volatility term structure.

    Shows how forecast vol converges to long-run vol.

    Args:
        garch: Fitted GARCH model.
    """
    print(f"\n{'=' * 55}")
    print("  GARCH TERM STRUCTURE")
    print(f"{'=' * 55}")

    lr_vol = garch.long_run_vol_annual * 100
    curr_vol = np.sqrt(garch.current_var) * np.sqrt(ANNUALIZATION_FACTOR) * 100

    horizons = [1, 5, 10, 20, 30, 60, 90, 120, 180, 365]
    fc = garch.forecast(horizons)

    print(f"\n  Current vol:  {curr_vol:.1f}%")
    print(f"  Long-run vol: {lr_vol:.1f}%")
    print(f"  Persistence:  {garch.persistence:.4f}")
    print()
    print(f"  {'Horizon':>10}  {'Forecast':>10}  {'% to LR':>10}")
    print(f"  {'-' * 32}")

    for h in horizons:
        f_vol = fc[h] * 100
        if abs(curr_vol - lr_vol) > 0.01:
            pct_to_lr = (f_vol - curr_vol) / (lr_vol - curr_vol) * 100
        else:
            pct_to_lr = 100.0
        print(f"  {h:>8}d  {f_vol:>9.1f}%  {pct_to_lr:>9.1f}%")

    print(f"\n  Interpretation: forecast converges {pct_to_lr:.0f}% toward long-run")
    print(f"  vol ({lr_vol:.1f}%) by day {horizons[-1]}.")


def print_diagnostics(returns: pd.Series, garch: GARCHModel) -> None:
    """Print model fit diagnostics.

    Args:
        returns: Original return series.
        garch: Fitted GARCH model.
    """
    print(f"\n{'=' * 55}")
    print("  DIAGNOSTICS")
    print(f"{'=' * 55}")

    r = returns.values
    std_resid = r / np.sqrt(garch.variance)

    print(f"\n  Return series:")
    print(f"    N observations:  {len(r)}")
    print(f"    Mean return:     {np.mean(r) * 100:.4f}% daily")
    print(f"    Std dev:         {np.std(r) * 100:.3f}% daily")
    print(f"    Skewness:        {pd.Series(r).skew():.3f}")
    print(f"    Kurtosis:        {pd.Series(r).kurtosis():.3f} (excess)")

    print(f"\n  Standardized residuals (r/σ):")
    print(f"    Mean:            {np.mean(std_resid):.4f} (should be ~0)")
    print(f"    Std dev:         {np.std(std_resid):.4f} (should be ~1)")
    print(f"    Skewness:        {pd.Series(std_resid).skew():.3f}")
    print(f"    Kurtosis:        {pd.Series(std_resid).kurtosis():.3f} (excess, >0 = fat tails)")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run EWMA and GARCH volatility forecasting."""
    parser = argparse.ArgumentParser(description="Volatility forecasting with EWMA and GARCH")
    parser.add_argument("--live", action="store_true", help="Use live Birdeye data")
    parser.add_argument("--mint", type=str, default=DEFAULT_MINT, help="Token mint")
    parser.add_argument("--days", type=int, default=500, help="Days of history")
    parser.add_argument("--lambda_", type=float, default=EWMA_LAMBDA, help="EWMA lambda")
    args = parser.parse_args()

    # Load data
    if args.live:
        print(f"Fetching {args.days} days of returns for {args.mint[:8]}...")
        returns = fetch_live_returns(args.mint, args.days)
        print(f"Loaded {len(returns)} daily returns.")
    else:
        print("Running in DEMO mode with synthetic GARCH(1,1) data.")
        print("True parameters: omega=0.000005, alpha=0.10, beta=0.85")
        print("Use --live flag with BIRDEYE_API_KEY for real data.\n")
        returns = generate_demo_returns(args.days)
        print(f"Generated {len(returns)} daily returns.")

    if len(returns) < 50:
        print(f"Error: Need at least 50 returns, got {len(returns)}.")
        sys.exit(1)

    # Fit EWMA
    ewma = EWMAModel(lam=args.lambda_)
    ewma.fit(returns)

    # Fit GARCH
    garch = GARCHModel()
    garch_ok = garch.fit(returns)

    if not garch_ok:
        print("Warning: GARCH fitting had issues. Results may be unreliable.")

    # Reports
    print_model_params(ewma, garch)

    ewma_fc = ewma.forecast(FORECAST_HORIZONS)
    garch_fc = garch.forecast(FORECAST_HORIZONS)
    print_forecast_comparison(ewma_fc, garch_fc)

    print_term_structure(garch)
    print_diagnostics(returns, garch)

    # Summary
    print(f"\n{'=' * 55}")
    print("  SUMMARY")
    print(f"{'=' * 55}")
    ewma_1d = ewma_fc[1] * 100
    garch_1d = garch_fc[1] * 100
    garch_30d = garch_fc[30] * 100
    lr = garch.long_run_vol_annual * 100

    print(f"\n  1-day forecast:   EWMA={ewma_1d:.1f}%, GARCH={garch_1d:.1f}%")
    print(f"  30-day forecast:  GARCH={garch_30d:.1f}%")
    print(f"  Long-run vol:     {lr:.1f}%")

    if garch_1d > lr * 1.2:
        print("  Status: Current vol ABOVE long-run — expect compression.")
    elif garch_1d < lr * 0.8:
        print("  Status: Current vol BELOW long-run — expect expansion.")
    else:
        print("  Status: Current vol near long-run level.")

    print()


if __name__ == "__main__":
    main()
