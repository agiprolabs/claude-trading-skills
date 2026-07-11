import importlib.util
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "layered-regime-momentum"
    / "scripts"
    / "layer2_bias.py"
)


def load_layer2_bias():
    spec = importlib.util.spec_from_file_location("layer2_bias", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Layer2BiasTests(unittest.TestCase):
    def test_pctrank_of_a_new_high_is_100(self):
        module = load_layer2_bias()
        series = pd.Series(list(range(1, 21)))  # strictly increasing

        ranks = module.pctrank(series, lookback=10)

        # The last value is the highest seen in its trailing window -> rank 100.
        self.assertAlmostEqual(ranks.iloc[-1], 100.0)

    def test_pctrank_of_a_new_low_is_low(self):
        module = load_layer2_bias()
        series = pd.Series(list(range(20, 0, -1)))  # strictly decreasing

        ranks = module.pctrank(series, lookback=10)

        self.assertLess(ranks.iloc[-1], 20.0)

    def test_directional_tf_score_mirrors_for_sell(self):
        """BULL uses ROC/RSI as-is; SELL must mirror both (100 - x), while
        ADX/Volume (non-directional) stay identical either way."""
        module = load_layer2_bias()
        bias = pd.DataFrame({
            "roc_pctrank": [80.0],
            "rsi14": [70.0],
            "adx_pctrank": [60.0],
            "vol_pctrank": [40.0],
        })

        bull_score = module.directional_tf_score(bias, pd.Series(["BULL"]))
        sell_score = module.directional_tf_score(bias, pd.Series(["SELL"]))
        none_score = module.directional_tf_score(bias, pd.Series([None]))

        self.assertAlmostEqual(bull_score.iloc[0], (80 + 70 + 60 + 40) / 4)
        self.assertAlmostEqual(sell_score.iloc[0], ((100 - 80) + (100 - 70) + 60 + 40) / 4)
        self.assertTrue(np.isnan(none_score.iloc[0]))

    def test_threshold_is_stricter_for_early_states(self):
        module = load_layer2_bias()
        result = pd.DataFrame({
            "layer1_regime": ["BULL", "EARLY_BULL", "SELL", "EARLY_SELL", "NEUTRAL"],
        })

        thresholds = np.select(
            [result["layer1_regime"].isin(module.CONFIRMED_STATES),
             result["layer1_regime"].isin(module.EARLY_STATES)],
            [module.CONFIRMED_THRESHOLD, module.EARLY_THRESHOLD],
            default=np.nan,
        )

        self.assertEqual(thresholds[0], module.CONFIRMED_THRESHOLD)
        self.assertEqual(thresholds[1], module.EARLY_THRESHOLD)
        self.assertEqual(thresholds[2], module.CONFIRMED_THRESHOLD)
        self.assertEqual(thresholds[3], module.EARLY_THRESHOLD)
        self.assertTrue(np.isnan(thresholds[4]))
        self.assertGreater(module.EARLY_THRESHOLD, module.CONFIRMED_THRESHOLD)

    def test_neutral_layer1_never_passes_regardless_of_score(self):
        module = load_layer2_bias()

        def resample(df, bucket_ms):
            d = df.copy()
            d["grp"] = d["timestamp"] // bucket_ms
            return d.groupby("grp").agg(
                timestamp=("timestamp", "first"), open=("open", "first"),
                high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"),
            ).reset_index(drop=True)

        # Perfectly flat price -> HMA slope stays flat -> Layer 1 NEUTRAL throughout.
        n = 500
        step = 15 * 60 * 1000
        flat = pd.DataFrame({
            "timestamp": [i * step for i in range(n)],
            "open": [100.0] * n, "high": [100.0] * n, "low": [100.0] * n,
            "close": [100.0] * n, "volume": [1000.0] * n,
        })
        df_30m = resample(flat, 30 * 60 * 1000)
        df_1h = resample(flat, 60 * 60 * 1000)

        result = module.layer2_bias(df_1h, df_30m, flat)

        self.assertTrue((result["layer1_regime"] == "NEUTRAL").all())
        self.assertFalse(result["layer2_pass"].any())

    def test_strong_sustained_uptrend_passes_confirmed_threshold(self):
        module = load_layer2_bias()

        def resample(df, bucket_ms):
            d = df.copy()
            d["grp"] = d["timestamp"] // bucket_ms
            return d.groupby("grp").agg(
                timestamp=("timestamp", "first"), open=("open", "first"),
                high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"),
            ).reset_index(drop=True)

        n = 500
        step = 15 * 60 * 1000
        # Genuinely *accelerating* uptrend (per-bar return rate itself rises
        # over time) with rising volume. A constant per-bar % return would
        # give a flat ROC/ADX that ranks ~50th-percentile against its own
        # recent history (percentile-rank measures "more extreme than
        # recently," not absolute level) -- acceleration is what pushes ROC
        # and ADX to new highs within the rolling window.
        prices = [100.0]
        for i in range(1, n):
            ret = 0.0005 + i * 0.00001  # per-bar return rate increases over time
            prices.append(prices[-1] * (1 + ret))
        volumes = [1000.0 * (1 + i / n) for i in range(n)]
        df_15m = pd.DataFrame({
            "timestamp": [i * step for i in range(n)],
            "open": prices, "high": prices, "low": prices, "close": prices,
            "volume": volumes,
        })
        df_30m = resample(df_15m, 30 * 60 * 1000)
        df_1h = resample(df_15m, 60 * 60 * 1000)

        result = module.layer2_bias(df_1h, df_30m, df_15m)
        tail = result.tail(20)

        self.assertTrue((tail["layer1_regime"] == "BULL").all())
        self.assertTrue(tail["layer2_pass"].all())


if __name__ == "__main__":
    unittest.main()
