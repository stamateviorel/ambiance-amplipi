"""Config zone parsing + the HealthMonitor sweep (with a fake controller)."""
import os
import tempfile
import unittest

from ambiance import health as health_mod
from ambiance.config import _load_zones
from ambiance.hardware import preamp


class TestConfigZones(unittest.TestCase):
    def _write(self, contents):
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, "w") as f:
            f.write(contents)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_parse(self):
        z = _load_zones(self._write("# header\n0|Office|70\n1|Kitchen|50\n\n2|Main|80\n"))
        self.assertEqual(len(z), 3)
        self.assertEqual(z[0], {"id": 0, "name": "Office", "default_pct": 70})
        self.assertEqual(z[2]["name"], "Main")

    def test_default_pct_fallback(self):
        z = _load_zones(self._write("0|Office|\n"))
        self.assertEqual(z[0]["default_pct"], 50)

    def test_missing_file(self):
        self.assertEqual(_load_zones("/no/such/file"), [])


class _FakeRadio:
    def __init__(self, healthy):
        self.desired_playing = True
        self._healthy = healthy
        self.recovered = False

    def health(self):
        return (True, None) if self._healthy else (False, "streamfout")

    def recover(self):
        self.recovered = True
        self._healthy = True   # self-heal succeeds
        return True


class _FakeCtl:
    def __init__(self, radio):
        self.radio = radio


class TestHealthMonitor(unittest.TestCase):
    def setUp(self):
        # no real 2s sleep, and a clean preamp health surface
        self._sleep = health_mod.time.sleep
        health_mod.time.sleep = lambda *a, **k: None
        preamp._HEALTH["alert_ts"] = 0.0
        preamp._HEALTH["alert_msg"] = None

    def tearDown(self):
        health_mod.time.sleep = self._sleep

    def test_healthy(self):
        st = health_mod.HealthMonitor(_FakeCtl(_FakeRadio(healthy=True)))._sweep()
        self.assertTrue(st["ok"])
        self.assertEqual(st["mpd"], "ok")
        self.assertEqual(st["preamp"], "ok")
        self.assertEqual(st["issues"], [])

    def test_self_heals_dropped_stream(self):
        r = _FakeRadio(healthy=False)
        st = health_mod.HealthMonitor(_FakeCtl(r))._sweep()
        self.assertTrue(r.recovered)     # recover() was attempted
        self.assertTrue(st["ok"])        # and it healed

    def test_preamp_alert_surfaces(self):
        preamp._add_alert("I2C recovery failed")
        st = health_mod.HealthMonitor(_FakeCtl(_FakeRadio(healthy=True)))._sweep()
        self.assertFalse(st["ok"])
        self.assertEqual(st["preamp"], "wedged")
        self.assertTrue(any("ersterker" in i or "I2C" in i for i in st["issues"]))


if __name__ == "__main__":
    unittest.main()
