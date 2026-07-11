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
    / "layer1_regime.py"
)


def load_layer1_regime():
    spec = importlib.util.spec_from_file_location("layer1_regime", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Layer1RegimeTests(unittest.TestCase):
    def test_warmup_bars_are_neutral(self):
        module = load_layer1_regime()
        short_df = pd.DataFrame({
            "timestamp": [i * 1000 for i in range(10)],
            "close": [100.0 + i for i in range(10)],
        })

        result = module.compute_tf_regime(short_df, hma_period=20)

        self.assertTrue((result["regime"] == "NEUTRAL").all())

    def test_htf_regime_is_not_visible_before_it_closes(self):
        """A 30m bar closing halfway through an in-progress 1h bar must see
        the PREVIOUS (already-closed) 1h bar's regime, never the current one.
        Regression test for an off-by-one where comparing open-time
        timestamps directly let a still-forming HTF bar leak into the LTF
        join one bar early."""
        module = load_layer1_regime()
        n_1h = 40
        step_1h = 3_600_000
        prices = list(np.linspace(100, 150, 20)) + list(np.linspace(150, 90, 20))
        df_1h = pd.DataFrame({
            "timestamp": [i * step_1h for i in range(n_1h)],
            "close": prices,
        })
        r1h = module.compute_tf_regime(df_1h)

        # One 30m bar at the start of each hour (closes halfway through that
        # hour) and one at the half-hour mark (closes exactly when the hour does).
        rows = []
        for i, ts in enumerate(df_1h["timestamp"]):
            rows.append((ts, 0.0))
            rows.append((ts + 1_800_000, 0.0))
        df_30m = pd.DataFrame(rows, columns=["timestamp", "close"])

        aligned = module.align_htf_to_ltf(df_30m["timestamp"], r1h, "regime_1h")

        for i in range(2, n_1h):
            start_of_hour_ts = df_1h["timestamp"].iloc[i]
            idx = df_30m.index[df_30m["timestamp"] == start_of_hour_ts][0]
            with self.subTest(hour=i, half="first"):
                self.assertEqual(aligned.iloc[idx], r1h["regime"].iloc[i - 1])

            half_hour_ts = start_of_hour_ts + 1_800_000
            idx2 = df_30m.index[df_30m["timestamp"] == half_hour_ts][0]
            with self.subTest(hour=i, half="second"):
                self.assertEqual(aligned.iloc[idx2], r1h["regime"].iloc[i])

    def test_classify_layer1_covers_all_nine_combinations(self):
        """Direct table test of the 5-state classification over the full
        3x3 (regime_30m, regime_1h) grid. 30m is the leading timeframe: an
        EARLY_* state fires whenever 30m has a direction and 1h hasn't
        confirmed it yet -- whether 1h is merely undecided (NEUTRAL) or
        actively opposite -- matching the confirmed design (outright
        conflict counts as "early", not NEUTRAL)."""
        module = load_layer1_regime()
        regime_30m = pd.Series(["UP", "UP", "UP", "DOWN", "DOWN", "DOWN", "NEUTRAL", "NEUTRAL", "NEUTRAL"])
        regime_1h = pd.Series(["UP", "DOWN", "NEUTRAL", "DOWN", "UP", "NEUTRAL", "UP", "DOWN", "NEUTRAL"])
        expected = ["BULL", "EARLY_BULL", "EARLY_BULL", "SELL", "EARLY_SELL", "EARLY_SELL", "NEUTRAL", "NEUTRAL", "NEUTRAL"]

        result = module.classify_layer1(regime_30m, regime_1h)

        self.assertEqual(list(result["layer1_regime"]), expected)
        self.assertEqual(
            list(result["layer1_confirmed"]),
            [s in ("BULL", "SELL") for s in expected],
        )
        self.assertEqual(
            list(result["layer1_directional"]),
            [s != "NEUTRAL" for s in expected],
        )

    def test_layer1_regime_end_to_end_steady_uptrend(self):
        module = load_layer1_regime()

        # End-to-end: construct 1h/30m data whose regimes are known to align
        # on the tail and verify layer1_regime reports full BULL there.
        n_30m = 200
        step_30m = 1_800_000
        prices_30m = list(np.linspace(100, 200, n_30m))  # steady uptrend
        df_30m = pd.DataFrame({
            "timestamp": [i * step_30m for i in range(n_30m)],
            "open": prices_30m, "high": prices_30m, "low": prices_30m,
            "close": prices_30m, "volume": [1.0] * n_30m,
        })
        df = df_30m.copy()
        df["grp"] = df["timestamp"] // 3_600_000
        df_1h = df.groupby("grp").agg(
            timestamp=("timestamp", "first"), open=("open", "first"),
            high=("high", "max"), low=("low", "min"),
            close=("close", "last"), volume=("volume", "sum"),
        ).reset_index(drop=True)

        result = module.layer1_regime(df_1h, df_30m)
        tail = result.tail(20)
        self.assertTrue((tail["layer1_regime"] == "BULL").all())
        self.assertTrue(tail["layer1_confirmed"].all())
        self.assertTrue(tail["layer1_directional"].all())


if __name__ == "__main__":
    unittest.main()
