import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "layered-regime-momentum"
    / "scripts"
    / "layer4_risk.py"
)


def load_layer4_risk():
    spec = importlib.util.spec_from_file_location("layer4_risk", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclasses' internal type resolution looks the module up in
    # sys.modules by name -- it must be registered there before exec_module
    # runs, or @dataclass raises AttributeError on a None module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PositionLimitTests(unittest.TestCase):
    def test_max_two_positions_across_portfolio(self):
        module = load_layer4_risk()
        risk = module.Layer4RiskManager(balance=10_000.0, max_positions=2)
        risk.open("BTC", "LONG", 100.0, 0, atr_value=2.0)
        risk.open("ETH", "LONG", 50.0, 0, atr_value=1.0)

        can, why = risk.can_open("SOL")

        self.assertFalse(can)
        self.assertIn("max positions", why)

    def test_no_second_position_on_same_symbol(self):
        module = load_layer4_risk()
        risk = module.Layer4RiskManager(balance=10_000.0, max_positions=5)
        risk.open("BTC", "LONG", 100.0, 0, atr_value=2.0)

        can, why = risk.can_open("BTC")

        self.assertFalse(can)
        self.assertIn("BTC", why)

    def test_margin_is_five_percent_of_current_balance(self):
        module = load_layer4_risk()
        risk = module.Layer4RiskManager(balance=20_000.0, margin_fraction=0.05)

        pos = risk.open("BTC", "LONG", 100.0, 0, atr_value=2.0)

        self.assertAlmostEqual(pos.margin, 1_000.0)
        self.assertAlmostEqual(pos.remaining_margin, 1_000.0)


class SplitTakeProfitTests(unittest.TestCase):
    def test_long_sl_hit_before_tp1_closes_full_position_at_a_loss(self):
        module = load_layer4_risk()
        risk = module.Layer4RiskManager(balance=10_000.0)
        # entry 100, atr 2 -> risk_distance = 2*1.5 = 3 -> sl=97, tp1=101.5, tp2=103.6
        risk.open("BTC", "LONG", 100.0, entry_ts=0, atr_value=2.0)

        risk.check_exit("BTC", high=100.5, low=96.5, ts=1)  # dips through SL

        self.assertEqual(len(risk.fills), 1)
        fill = risk.fills[0]
        self.assertEqual(fill.reason, "SL")
        self.assertAlmostEqual(fill.exit_price, 97.0)
        self.assertAlmostEqual(fill.portion_margin, 500.0)  # full margin (5% of 10,000)
        self.assertLess(fill.pnl, 0)
        self.assertNotIn("BTC", risk.positions)  # fully closed

    def test_long_tp1_closes_half_then_tp2_closes_the_rest(self):
        module = load_layer4_risk()
        risk = module.Layer4RiskManager(balance=10_000.0)
        pos = risk.open("BTC", "LONG", 100.0, entry_ts=0, atr_value=2.0)
        self.assertAlmostEqual(pos.tp1, 101.5)
        self.assertAlmostEqual(pos.tp2, 103.6)
        self.assertAlmostEqual(pos.sl, 97.0)

        # Bar 1: price runs up through TP1 only.
        risk.check_exit("BTC", high=101.6, low=100.2, ts=1)
        self.assertEqual(len(risk.fills), 1)
        self.assertEqual(risk.fills[0].reason, "TP1")
        self.assertAlmostEqual(risk.fills[0].portion_margin, 250.0)  # 50% of 500
        self.assertIn("BTC", risk.positions)  # runner still open
        self.assertTrue(risk.positions["BTC"].tp1_hit)
        self.assertAlmostEqual(risk.positions["BTC"].sl, 100.3)  # moved to BE + 0.1*risk_distance(3)

        # Bar 2: price continues up to TP2.
        risk.check_exit("BTC", high=103.7, low=102.0, ts=2)
        self.assertEqual(len(risk.fills), 2)
        self.assertEqual(risk.fills[1].reason, "TP2")
        self.assertAlmostEqual(risk.fills[1].exit_price, 103.6)
        self.assertAlmostEqual(risk.fills[1].portion_margin, 250.0)
        self.assertNotIn("BTC", risk.positions)  # fully closed

        # Whole-trade sanity: TP1 leg (+1.5% on $250) + TP2 leg (+3.6% on $250).
        expected_pnl = 250.0 * 0.015 + 250.0 * 0.036
        self.assertAlmostEqual(risk.fills[0].pnl + risk.fills[1].pnl, expected_pnl, places=4)

    def test_long_tp1_then_reverses_to_be_stop_still_nets_a_gain(self):
        """The whole point of moving the stop to BE+0.1R after TP1: even if
        the runner gives back everything down to the new stop, the trade as
        a whole still nets a small gain, not just a wash -- TP1's realized
        gain plus the +0.1R locked in on the runner both stand."""
        module = load_layer4_risk()
        risk = module.Layer4RiskManager(balance=10_000.0)
        # entry 100, atr 2 -> risk_distance = 3 -> post-TP1 stop = 100 + 0.1*3 = 100.3
        risk.open("BTC", "LONG", 100.0, entry_ts=0, atr_value=2.0)

        risk.check_exit("BTC", high=101.6, low=100.2, ts=1)  # TP1 hit
        self.assertAlmostEqual(risk.positions["BTC"].sl, 100.3)
        risk.check_exit("BTC", high=100.5, low=99.5, ts=2)   # reverses back down through the new stop

        self.assertEqual(len(risk.fills), 2)
        self.assertEqual(risk.fills[1].reason, "BE_STOP")
        self.assertAlmostEqual(risk.fills[1].exit_price, 100.3)
        self.assertGreater(risk.fills[1].pnl, 0.0, "BE+0.1R must be a small win, not a wash")
        total_pnl = risk.fills[0].pnl + risk.fills[1].pnl
        self.assertGreater(total_pnl, 0.0, "TP1's gain must stand even if the runner gives back everything")

    def test_short_mirrors_long(self):
        module = load_layer4_risk()
        risk = module.Layer4RiskManager(balance=10_000.0)
        pos = risk.open("BTC", "SHORT", 100.0, entry_ts=0, atr_value=2.0)
        self.assertAlmostEqual(pos.sl, 103.0)
        self.assertAlmostEqual(pos.tp1, 98.5)
        self.assertAlmostEqual(pos.tp2, 96.4)

        risk.check_exit("BTC", high=98.8, low=98.2, ts=1)  # TP1
        self.assertEqual(risk.fills[0].reason, "TP1")
        self.assertGreater(risk.fills[0].pnl, 0)
        # entry 100, risk_distance 3 -> post-TP1 stop = 100 - 0.1*3 = 99.7
        self.assertAlmostEqual(risk.positions["BTC"].sl, 99.7)

        risk.check_exit("BTC", high=97.0, low=96.3, ts=2)  # TP2
        self.assertEqual(risk.fills[1].reason, "TP2")
        self.assertGreater(risk.fills[1].pnl, 0)
        self.assertNotIn("BTC", risk.positions)

    def test_same_bar_conservative_ordering_sl_wins_over_tp1(self):
        """If a single bar's range spans both the SL and TP1 levels, the
        conservative assumption (matching tf30m-hma-ema-momentum's engine)
        is that the stop was touched first."""
        module = load_layer4_risk()
        risk = module.Layer4RiskManager(balance=10_000.0)
        risk.open("BTC", "LONG", 100.0, entry_ts=0, atr_value=2.0)  # sl=97, tp1=101.5

        risk.check_exit("BTC", high=102.0, low=96.0, ts=1)  # spans both

        self.assertEqual(len(risk.fills), 1)
        self.assertEqual(risk.fills[0].reason, "SL")


if __name__ == "__main__":
    unittest.main()
