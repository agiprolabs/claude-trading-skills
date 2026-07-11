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
    / "layer3_entry.py"
)


def load_layer3_entry():
    spec = importlib.util.spec_from_file_location("layer3_entry", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def resample(df: pd.DataFrame, bucket_ms: int) -> pd.DataFrame:
    d = df.copy()
    d["grp"] = d["timestamp"] // bucket_ms
    return d.groupby("grp").agg(
        timestamp=("timestamp", "first"), open=("open", "first"),
        high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"),
    ).reset_index(drop=True)


class Layer3EntryTests(unittest.TestCase):
    def test_swing_high_is_not_confirmed_before_enough_future_bars_exist(self):
        """A fractal swing high at index k requires `lookback` bars AFTER k
        to rule out a higher one. It must not appear as `last_swing_high`
        any earlier than bar k + lookback -- that would mean the system
        "knew" about a peak before enough time had passed to confirm it."""
        module = load_layer3_entry()
        lookback = 3
        # A single, unambiguous spike at index 10, flat elsewhere.
        n = 30
        high = [100.0] * n
        high[10] = 110.0
        df = pd.DataFrame({
            "timestamp": [i * 1000 for i in range(n)],
            "open": high, "high": high, "low": [h - 1 for h in high], "close": high,
            "volume": [1.0] * n,
        })

        structure = module.compute_structure_breaks(df, lookback)

        for i in range(10 + lookback):
            with self.subTest(bar=i):
                self.assertTrue(
                    pd.isna(structure["last_swing_high"].iloc[i]) or structure["last_swing_high"].iloc[i] != 110.0,
                    f"bar {i} already sees the swing high, but it can't be confirmed until bar {10+lookback}",
                )
        for i in range(10 + lookback, n):
            with self.subTest(bar=i):
                self.assertEqual(structure["last_swing_high"].iloc[i], 110.0)

    def test_break_of_structure_is_one_shot(self):
        """Once a break fires, the same level must not refire on later bars
        that also happen to close above it -- a fresh swing high is required
        before the next long trigger."""
        module = load_layer3_entry()
        lookback = 2
        n = 20
        high = [100.0] * n
        high[5] = 105.0  # single swing high
        close = [100.0] * n
        # Break above 105 at bar 12, and stay above it for several more bars.
        for i in range(12, n):
            close[i] = 106.0
            high[i] = 106.0
        df = pd.DataFrame({
            "timestamp": [i * 1000 for i in range(n)],
            "open": close, "high": high, "low": [c - 1 for c in close], "close": close,
            "volume": [1.0] * n,
        })

        structure = module.compute_structure_breaks(df, lookback)

        self.assertEqual(structure["bos_up"].sum(), 1, "break should fire exactly once, not on every bar above it")
        self.assertTrue(structure["bos_up"].iloc[12])

    def test_long_only_fires_when_bull_and_layer2_passes(self):
        module = load_layer3_entry()
        df_1h, df_30m, df_15m = module.make_demo_data(n_15m=3000, seed=5)

        result = module.layer3_entry(df_1h, df_30m, df_15m)

        longs = result[result["layer3_entry"] == "LONG"]
        shorts = result[result["layer3_entry"] == "SHORT"]
        self.assertGreater(len(longs), 0)
        self.assertGreater(len(shorts), 0)
        self.assertTrue((longs["layer2_direction"] == "BULL").all())
        self.assertTrue(longs["layer2_pass"].all())
        self.assertTrue((shorts["layer2_direction"] == "SELL").all())
        self.assertTrue(shorts["layer2_pass"].all())
        # Structurally impossible: never LONG in a permitted SELL regime or vice versa.
        self.assertFalse((result[result["layer3_entry"] == "LONG"]["layer2_direction"] == "SELL").any())
        self.assertFalse((result[result["layer3_entry"] == "SHORT"]["layer2_direction"] == "BULL").any())

    def test_no_entry_when_layer2_fails_even_with_a_break(self):
        """A structure break with the right direction but layer2_pass False
        (bias too weak, or an EARLY_* state below the stricter threshold)
        must not produce an entry."""
        module = load_layer3_entry()
        df_1h, df_30m, df_15m = module.make_demo_data(n_15m=3000, seed=5)

        result = module.layer3_entry(df_1h, df_30m, df_15m)

        would_have_been_long = result[(result["bos_up"]) & (result["layer2_direction"] == "BULL")
                                       & (~result["layer2_pass"])]
        # These bars had a bullish break during a bull-direction read, but
        # bias didn't clear the threshold -- must not be marked as an entry.
        if len(would_have_been_long) > 0:
            self.assertTrue((would_have_been_long["layer3_entry"].isna()).all())


if __name__ == "__main__":
    unittest.main()
