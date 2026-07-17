"""Sleep timer: set / cancel / state / fire callback."""
import unittest

from ambiance.sleep import Sleep


class TestSleep(unittest.TestCase):
    def test_set_reports_active_and_remaining(self):
        s = Sleep(on_fire=lambda: None)
        self.assertFalse(s.state()["active"])
        s.set(30)
        st = s.state()
        self.assertTrue(st["active"])
        self.assertTrue(1740 <= st["remaining_s"] <= 1800)
        s.cancel()

    def test_cancel_and_zero(self):
        fired = []
        s = Sleep(on_fire=lambda: fired.append(1))
        s.set(10)
        self.assertTrue(s.state()["active"])
        s.set(0)                                  # 0 cancels
        self.assertFalse(s.state()["active"])
        s.set(10)
        s.cancel()
        self.assertFalse(s.state()["active"])
        self.assertEqual(fired, [])               # cancelling never fires

    def test_fire_calls_back_and_clears(self):
        fired = []
        s = Sleep(on_fire=lambda: fired.append(1))
        s.set(30)
        s._fire()                                 # simulate the timer elapsing
        self.assertEqual(fired, [1])
        self.assertFalse(s.state()["active"])


if __name__ == "__main__":
    unittest.main()
