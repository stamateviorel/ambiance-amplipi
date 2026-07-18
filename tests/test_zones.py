"""Zones logic (Mock hardware — no I2C)."""
import unittest

from ambiance.hardware.zones import Zones, pct_to_db, db_to_pct

# AmpliPi hardware is 6 zones per board, and the preamp layer asserts multiples of 6.
ZONES = [{"id": i, "name": n, "default_pct": p} for i, (n, p) in enumerate(
    [("Office", 70), ("Wc up", 40), ("Main", 80), ("Kitchen", 50), ("Wc down", 45), ("Showroom", 39)])]


class TestZones(unittest.TestCase):
    def setUp(self):
        self.z = Zones(ZONES, hw="mock")

    def test_defaults(self):
        snap = self.z.snapshot()
        self.assertEqual(len(snap), 6)
        self.assertEqual(snap[0]["name"], "Office")
        self.assertEqual(snap[0]["vol"], 70)
        self.assertTrue(all(s["power"] for s in snap))
        self.assertFalse(any(s["mute"] for s in snap))

    def test_pct_db_roundtrip(self):
        for pct in (0, 25, 50, 75, 100):
            self.assertAlmostEqual(db_to_pct(pct_to_db(pct)), pct, delta=2)

    def test_vol_clamped(self):
        self.z.set_vol(0, 150)
        self.assertEqual(self.z.snapshot()[0]["vol"], 100)
        self.z.set_vol(0, -10)
        self.assertEqual(self.z.snapshot()[0]["vol"], 0)

    def test_effective_silence(self):
        # effective silence = mute OR not power
        self.z.set_mute(0, True)
        self.assertTrue(self.z._eff()[0])
        self.z.set_mute(0, False)
        self.assertFalse(self.z._eff()[0])
        self.z.set_power(0, False)
        self.assertTrue(self.z._eff()[0])

    def test_master_mute(self):
        self.z.set_master_mute(True)
        self.assertTrue(self.z.master_mute())
        self.z.set_master_mute(False)
        self.assertFalse(self.z.master_mute())

    def test_zone_volumes_stay_independent(self):
        # the master (source) volume no longer flattens zones — each keeps its own level
        self.z.set_vol(0, 20)
        self.z.set_vol(1, 80)
        snap = {s["id"]: s["vol"] for s in self.z.snapshot()}
        self.assertEqual(snap[0], 20)
        self.assertEqual(snap[1], 80)

    def test_siren_snapshot_restore(self):
        self.z.set_vol(0, 30)
        self.z.set_mute(1, True)
        self.z.set_power(2, False)
        before = self.z.snapshot()

        self.z.siren(True)
        self.assertTrue(self.z.siren_active)
        during = self.z.snapshot()
        self.assertFalse(any(s["mute"] for s in during))   # all unmuted
        self.assertTrue(all(s["power"] for s in during))    # all powered

        self.z.siren(False)
        self.assertFalse(self.z.siren_active)
        self.assertEqual(self.z.snapshot(), before)         # restored exactly


if __name__ == "__main__":
    unittest.main()
