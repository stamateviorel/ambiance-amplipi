"""System stats shape + power actions are no-ops in dry mode (fail-safe)."""
import unittest

from ambiance.system import System


class TestSystem(unittest.TestCase):
    def test_stats_shape(self):
        s = System(dry=True).stats()
        for k in ("hostname", "uptime_s", "cpu_pct", "mem", "disk", "temp_c", "services"):
            self.assertIn(k, s)
        self.assertIn("pct", s["mem"])
        self.assertIsInstance(s["services"], list)

    def test_power_noop_in_dry(self):
        s = System(dry=True)
        self.assertFalse(s.reboot())      # dry -> never actually reboots
        self.assertFalse(s.shutdown())


if __name__ == "__main__":
    unittest.main()
