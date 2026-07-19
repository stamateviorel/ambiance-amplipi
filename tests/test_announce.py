"""Announcer: queue -> fetch -> duck -> aplay -> restore, the siren busy-drop, the
per-announcement boost volume, and the duck-restore guard. All dry / local file:// — no
audio, no network."""
import os
import tempfile
import time
import unittest

from ambiance.announce import Announcer


def _wait(predicate, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class _RecBoost:
    """Records boost set_vol calls; reports a fixed current level."""

    def __init__(self, level=100):
        self.level = level
        self.sets = []

    def vol(self):
        return self.level

    def set_vol(self, pct):
        self.sets.append(pct)


class TestAnnouncer(unittest.TestCase):
    def setUp(self):
        fd, self.wav = tempfile.mkstemp(suffix=".wav")
        os.write(fd, b"RIFF0000WAVEfmt ")
        os.close(fd)
        self.url = "file://" + self.wav

    def tearDown(self):
        try:
            os.unlink(self.wav)
        except OSError:
            pass

    def _recorded(self, a):
        ran = []
        a._run = lambda cmd: ran.append(list(cmd)) or 0
        return ran

    def test_says_and_restores_duck(self):
        a = Announcer(dry=True)
        ran = self._recorded(a)
        self.assertTrue(a.say(self.url))
        self.assertTrue(_wait(lambda: any(c[0] == "aplay" for c in ran)))
        self.assertTrue(_wait(lambda: len([c for c in ran if c[0] == "amixer"]) >= 2))
        amixer = [c for c in ran if c[0] == "amixer"]
        self.assertIn("45%", amixer[0])                    # ducked...
        self.assertIn("100%", amixer[-1])                  # ...and restored (dry current = 100)

    def test_busy_drops_speech(self):
        a = Announcer(dry=True, is_busy=lambda: True)      # siren active
        ran = self._recorded(a)
        self.assertTrue(a.say(self.url))
        self.assertTrue(_wait(lambda: a.q.qsize() == 0))
        time.sleep(0.1)
        self.assertEqual(ran, [])                          # nothing played, nothing ducked

    def test_vol_drives_and_restores_boost(self):
        boost = _RecBoost(level=100)
        a = Announcer(dry=True, boost=boost)
        self._recorded(a)
        self.assertTrue(a.say(self.url, vol=30))
        self.assertTrue(_wait(lambda: boost.sets == [30, 100]))   # set for the message, restored after

    def test_no_vol_leaves_boost_alone(self):
        boost = _RecBoost()
        a = Announcer(dry=True, boost=boost)
        self._recorded(a)
        self.assertTrue(a.say(self.url))
        self.assertTrue(_wait(lambda: a.q.qsize() == 0))
        time.sleep(0.1)
        self.assertEqual(boost.sets, [])

    def test_default_vol_applies_when_message_omits_vol(self):
        boost = _RecBoost(level=100)
        a = Announcer(dry=True, boost=boost, default_vol=70)
        self._recorded(a)
        self.assertTrue(a.say(self.url))                          # no per-message vol
        self.assertTrue(_wait(lambda: boost.sets == [70, 100]))   # default applied, then restored

    def test_message_vol_overrides_default(self):
        boost = _RecBoost(level=100)
        a = Announcer(dry=True, boost=boost, default_vol=70)
        self._recorded(a)
        self.assertTrue(a.say(self.url, vol=25))                  # per-message wins over the default
        self.assertTrue(_wait(lambda: boost.sets == [25, 100]))

    def test_set_default_vol_clamps_and_clears(self):
        a = Announcer(dry=True)
        self.assertEqual(a.set_default_vol(150), 100)             # clamp high
        self.assertEqual(a.set_default_vol(-5), 0)                # clamp low
        self.assertIsNone(a.set_default_vol(None))               # None clears the override

    def test_flush_drops_pending_and_is_idempotent(self):
        import queue as q_
        a = Announcer(dry=True)
        held = q_.Queue(maxsize=20)                               # worker stays blocked on the OLD
        for u in ("a", "b", "c"):                                 # queue -> these 3 stay put
            held.put_nowait((u, None))
        a.q = held
        self.assertEqual(a.flush(), 3)                            # all pending dropped
        self.assertEqual(a.q.qsize(), 0)
        self.assertEqual(a.flush(), 0)                            # nothing left -> 0

    def test_stats_reports_depth_and_vol(self):
        import queue as q_
        a = Announcer(dry=True, default_vol=60)
        held = q_.Queue(maxsize=20)
        held.put_nowait((self.url, None))
        a.q = held                                               # worker blocked on the OLD queue
        st = a.stats()
        self.assertEqual(st["queued"], 1)
        self.assertFalse(st["playing"])                          # nothing on air
        self.assertEqual(st["vol"], 60)

    def test_fetch_failure_does_not_kill_worker(self):
        a = Announcer(dry=True)
        ran = self._recorded(a)
        self.assertTrue(a.say("file:///nonexistent-announce-input.wav"))   # fetch raises
        self.assertTrue(a.say(self.url))                                   # ...worker survives
        self.assertTrue(_wait(lambda: any(c[0] == "aplay" for c in ran)))

    def test_queue_full_rejected(self):
        import queue as q_
        a = Announcer(dry=True)
        full = q_.Queue(maxsize=1)
        full.put_nowait(("x", None))
        a.q = full        # the worker stays blocked on the OLD queue -> deterministic
        self.assertFalse(a.say(self.url))                  # a full queue reports failure


if __name__ == "__main__":
    unittest.main()
