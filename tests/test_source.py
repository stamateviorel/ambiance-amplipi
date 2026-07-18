"""Source (Ch0) volume — the radio source level, independent of per-zone volumes."""
import unittest

from ambiance.source import Source


class TestSource(unittest.TestCase):
    def test_dry_defaults_full(self):
        self.assertEqual(Source(dry=True).vol(), 100)

    def test_set_and_get(self):
        s = Source(dry=True)
        s.set_vol(70)
        self.assertEqual(s.vol(), 70)

    def test_clamps(self):
        s = Source(dry=True)
        s.set_vol(150)
        self.assertEqual(s.vol(), 100)
        s.set_vol(-10)
        self.assertEqual(s.vol(), 0)


if __name__ == "__main__":
    unittest.main()
