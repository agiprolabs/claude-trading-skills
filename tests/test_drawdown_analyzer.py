import importlib.util
import unittest
from pathlib import Path

import numpy as np


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "risk-management"
    / "scripts"
    / "drawdown_analyzer.py"
)


def load_drawdown_analyzer():
    spec = importlib.util.spec_from_file_location("drawdown_analyzer", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DrawdownAnalyzerTests(unittest.TestCase):
    def test_current_drawdown_start_uses_latest_matching_peak(self):
        module = load_drawdown_analyzer()
        equity = np.array([100.0, 120.0, 110.0, 120.0, 115.0])

        summary = module.analyze_drawdowns(equity)

        self.assertAlmostEqual(summary.current_drawdown, (120.0 - 115.0) / 120.0)
        self.assertEqual(summary.current_drawdown_start, 3)

    def test_current_drawdown_start_is_none_at_new_high(self):
        module = load_drawdown_analyzer()
        equity = np.array([100.0, 110.0, 120.0])

        summary = module.analyze_drawdowns(equity)

        self.assertEqual(summary.current_drawdown, 0.0)
        self.assertIsNone(summary.current_drawdown_start)


if __name__ == "__main__":
    unittest.main()
