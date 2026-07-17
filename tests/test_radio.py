"""Radio: station CRUD (atomic file), ICY now-playing parse, desired_playing + health.
The mpc subprocess is stubbed so no mpd is needed."""
import os
import tempfile
import unittest

from ambiance.radio import Radio


class FakeRadio(Radio):
    """Radio with _mpc stubbed to a canned string (no mpd)."""
    mpc_out = ""

    def _mpc(self, *args):
        return self.mpc_out


def _stations_file(contents="VRT|http://a\nKlara|http://b\n"):
    fd, path = tempfile.mkstemp(suffix=".conf")
    with os.fdopen(fd, "w") as f:
        f.write(contents)
    return path


class TestStationsCrud(unittest.TestCase):
    def setUp(self):
        self.path = _stations_file()
        self.r = FakeRadio(self.path)

    def tearDown(self):
        for p in (self.path, self.path + ".bak"):
            if os.path.exists(p):
                os.remove(p)

    def test_load(self):
        self.assertEqual([s["name"] for s in self.r.stations], ["VRT", "Klara"])

    def test_add_and_persist(self):
        ok, err = self.r.add_station("Nostalgie", "http://c")
        self.assertTrue(ok)
        self.assertIsNone(err)
        # persisted atomically -> a fresh load sees it
        self.assertIn("Nostalgie", [s["name"] for s in FakeRadio(self.path).stations])

    def test_add_duplicate_rejected(self):
        ok, _ = self.r.add_station("VRT", "http://x")
        self.assertFalse(ok)

    def test_add_missing_fields_rejected(self):
        self.assertFalse(self.r.add_station("", "http://x")[0])
        self.assertFalse(self.r.add_station("Name", "")[0])

    def test_update(self):
        ok, _ = self.r.update_station("Klara", "Klara Continuo", "http://b2")
        self.assertTrue(ok)
        self.assertEqual(self.r.stations[1], {"name": "Klara Continuo", "url": "http://b2"})

    def test_delete(self):
        ok, _ = self.r.delete_station("VRT")
        self.assertTrue(ok)
        self.assertEqual([s["name"] for s in self.r.stations], ["Klara"])

    def test_set_default_moves_first(self):
        ok, _ = self.r.set_default("Klara")
        self.assertTrue(ok)
        self.assertEqual(self.r.stations[0]["name"], "Klara")

    def test_clean_strips_pipe_and_newline(self):
        ok, _ = self.r.add_station("A|B\nC", "http://d")
        self.assertTrue(ok)
        self.assertNotIn("|", self.r.stations[-1]["name"])
        self.assertNotIn("\n", self.r.stations[-1]["name"])


class TestNowPlaying(unittest.TestCase):
    def _radio(self, title):
        path = _stations_file()
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        r = FakeRadio(path)
        r.mpc_out = title
        return r

    def test_artist_track_split(self):
        np = self._radio("Coldplay - Yellow").now_playing()
        self.assertEqual(np["artist"], "Coldplay")
        self.assertEqual(np["track"], "Yellow")

    def test_station_only(self):
        np = self._radio("VRT Radio 1").now_playing()
        self.assertEqual(np["artist"], "")
        self.assertEqual(np["track"], "VRT Radio 1")


class TestPlayStateHealth(unittest.TestCase):
    def _radio(self, mpc_out):
        path = _stations_file()
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        r = FakeRadio(path)
        r.mpc_out = mpc_out
        return r

    def test_desired_playing_tracks_play_stop(self):
        r = self._radio("[playing] ...")
        self.assertFalse(r.desired_playing)
        r.play()
        self.assertTrue(r.desired_playing)
        r.stop()
        self.assertFalse(r.desired_playing)

    def test_health_ok_when_playing(self):
        r = self._radio("volume: n/a\n[playing] #1/1")
        r.desired_playing = True
        ok, detail = r.health()
        self.assertTrue(ok)
        self.assertIsNone(detail)

    def test_health_not_ok_when_unreachable(self):
        r = self._radio("")            # _mpc returns "" -> mpd unreachable
        ok, detail = r.health()
        self.assertFalse(ok)

    def test_health_detects_dropped_stream(self):
        r = self._radio("[paused] #1/1")  # meant to play but not playing
        r.desired_playing = True
        ok, detail = r.health()
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
