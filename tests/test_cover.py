"""Cover: the tier-3 generated station tile (no network) + no-station -> None.
(Tiers 1/2 hit the network and are not unit-tested.)"""
import unittest

from ambiance.cover import Cover


class TestCoverTile(unittest.TestCase):
    def test_generated_tile_is_jpeg(self):
        data = Cover().bytes_for("VRT Radio 1", None, "VRT Radio 1")
        self.assertIsNotNone(data)
        self.assertEqual(data[:2], b"\xff\xd8")   # JPEG magic
        self.assertGreater(len(data), 1000)

    def test_no_station_no_cover(self):
        self.assertIsNone(Cover().bytes_for("", None, None))

    def test_tile_is_deterministic(self):
        a = Cover().bytes_for("Klara", None, "Klara")
        b = Cover().bytes_for("Klara", None, "Klara")
        self.assertEqual(a, b)   # same station -> same tile bytes


if __name__ == "__main__":
    unittest.main()
