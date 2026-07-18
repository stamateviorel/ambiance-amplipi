"""Zones logic (Mock hardware — no I2C)."""
import unittest

from ambiance.hardware.zones import Zones, pct_to_db, db_to_pct, MAX_DB

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

    def test_out_of_range_ids_ignored(self):
        # zid=-1 must NOT wrap to the last zone (Python negative indexing); zid>=n must not crash
        self.z.set_vol(-1, 5)
        self.z.set_vol(9, 5)
        self.z.set_mute(-1, True)
        self.z.set_power(9, False)
        snap = self.z.snapshot()
        self.assertEqual(snap[5]["vol"], 39)               # untouched by the -1 write
        self.assertFalse(any(s["mute"] for s in snap))
        self.assertTrue(all(s["power"] for s in snap))

    def test_rename(self):
        self.assertTrue(self.z.rename(0, "Studeerkamer"))
        self.assertEqual(self.z.snapshot()[0]["name"], "Studeerkamer")
        self.assertFalse(self.z.rename(9, "x"))
        self.assertFalse(self.z.rename(-1, "x"))

    def test_master_mute_reports_false_during_siren(self):
        self.z.set_master_mute(True)
        self.z.siren(True)
        self.assertFalse(self.z.master_mute())             # actual output is unmuted
        self.z.siren(False)
        self.assertTrue(self.z.master_mute())              # logical state restored

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


class _Rec:
    """Records what actually reaches the preamp — proves the siren lock."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.vol_calls = 0
        self.mute_calls = 0
        self.last_vol = {}
        self.last_mutes = None

    def update_zone_sources(self, s, a):
        pass

    def update_zone_vol(self, z, db):
        self.vol_calls += 1
        self.last_vol[z] = db

    def update_zone_mutes(self, s, a):
        self.mute_calls += 1
        self.last_mutes = list(a)


class TestPartialZoneCount(unittest.TestCase):
    """A zones.conf with fewer than 6 zones must work — the preamp layer asserts whole
    boards (multiples of 6); zones beyond the configured count are padded MUTED."""

    FOUR = [{"id": i, "name": "Zone %d" % (i + 1), "default_pct": 50} for i in range(4)]

    def test_four_zone_config_initialises(self):
        z = Zones(self.FOUR, hw="mock")        # Mock() itself asserts the padded shapes
        self.assertEqual(len(z.snapshot()), 4)

    def test_padding_is_muted(self):
        z = Zones(self.FOUR, hw="mock")
        z.rt = _Rec()
        z.set_mute(0, True)
        self.assertEqual(len(z.rt.last_mutes), 6)
        self.assertEqual(z.rt.last_mutes[4:], [True, True])    # absent zones stay silent

    def test_padding_stays_muted_during_siren(self):
        z = Zones(self.FOUR, hw="mock")
        z.rt = _Rec()
        z.siren(True)
        self.assertEqual(z.rt.last_mutes[:4], [False] * 4)     # real zones blast
        self.assertEqual(z.rt.last_mutes[4:], [True, True])    # absent outputs never open


class TestSirenLock(unittest.TestCase):
    def setUp(self):
        self.z = Zones(ZONES, hw="mock")
        self.z.rt = _Rec()                     # swap in the recorder after init

    def test_no_command_can_quiet_the_siren(self):
        self.z.siren(True)
        self.z.rt.reset()
        self.z.set_vol(0, 0)                   # every way to "quiet it" mid-alarm
        self.z.set_mute(1, True)
        self.z.set_power(2, False)
        self.z.set_master_mute(True)
        self.assertEqual(self.z.vol[0], 0)     # remembered for later restore...
        self.assertTrue(self.z.muted[1])
        self.assertFalse(self.z.power[2])
        self.assertEqual(self.z.rt.vol_calls, 0)   # ...but nothing reached the preamp
        self.assertEqual(self.z.rt.mute_calls, 0)

    def test_siren_drives_every_zone_full(self):
        self.z.rt.reset()
        self.z.siren(True)
        self.assertEqual(set(self.z.rt.last_vol.values()), {MAX_DB})   # all MAX
        self.assertEqual(self.z.rt.last_mutes, [False] * 6)            # all audible

    def test_reassert_redrives_full(self):
        self.z.siren(True)
        self.z.set_power(3, False)
        self.z.rt.reset()
        self.z.reassert_siren()
        self.assertEqual(set(self.z.rt.last_vol.values()), {MAX_DB})
        self.assertEqual(self.z.rt.last_mutes, [False] * 6)

    def test_release_applies_commands_made_during_siren(self):
        self.z.siren(True)
        self.z.set_power(3, False)             # commanded off mid-alarm
        self.z.rt.reset()
        self.z.siren(False)
        self.assertFalse(self.z.siren_active)
        self.assertTrue(self.z.rt.last_mutes[3])    # zone 3 silenced on release
        self.assertFalse(self.z.rt.last_mutes[0])   # zone 0 audible


if __name__ == "__main__":
    unittest.main()
