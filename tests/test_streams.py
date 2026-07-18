"""Sources registry + arbitration (claim pauses the others) and the RadioAdapter mapping."""
import unittest

from ambiance.streams import RadioAdapter, Sources


class _FakeSrc:
    def __init__(self):
        self.paused = 0
        self.resumed = 0
        self._playing = False

    def playing(self):
        return self._playing

    def pause(self):
        self.paused += 1
        self._playing = False

    def resume(self):
        self.resumed += 1
        self._playing = True

    def next(self):
        pass

    def prev(self):
        pass

    def can_resume(self):
        return True


class _FakeRadio:
    def __init__(self):
        self.calls = []
        self.desired_playing = False

    def stop(self):
        self.calls.append("stop")

    def play(self):
        self.calls.append("play")

    def cycle(self, d):
        self.calls.append("cycle%+d" % d)


class TestSources(unittest.TestCase):
    def setUp(self):
        self.radio, self.spotify = _FakeSrc(), _FakeSrc()
        self.s = Sources()
        self.s.register("radio", self.radio)
        self.s.register("spotify", self.spotify)

    def test_first_registered_is_active(self):
        self.assertEqual(self.s.active, "radio")
        self.assertEqual(self.s.available, ["radio", "spotify"])

    def test_claim_pauses_the_others(self):
        self.assertTrue(self.s.claim("spotify"))
        self.assertEqual(self.s.active, "spotify")
        self.assertEqual(self.radio.paused, 1)      # radio yielded
        self.assertEqual(self.spotify.paused, 0)    # the claimer is untouched

    def test_claim_unknown_refused(self):
        self.assertFalse(self.s.claim("airplay"))
        self.assertEqual(self.s.active, "radio")

    def test_pause_all(self):
        self.s.pause_all()
        self.assertEqual((self.radio.paused, self.spotify.paused), (1, 1))

    def test_state_shape(self):
        self.assertEqual(self.s.state(), {"active": "radio", "available": ["radio", "spotify"]})

    def test_pause_exception_does_not_break_claim(self):
        def boom():
            raise RuntimeError("dead daemon")
        self.spotify.pause = boom
        self.assertTrue(self.s.claim("radio"))      # spotify.pause raised, claim still lands
        self.assertEqual(self.s.active, "radio")


class TestRadioAdapter(unittest.TestCase):
    def test_mapping(self):
        r = _FakeRadio()
        a = RadioAdapter(r)
        a.pause()
        a.resume()
        a.next()
        a.prev()
        self.assertEqual(r.calls, ["stop", "play", "cycle+1", "cycle-1"])
        self.assertTrue(a.can_resume())
        self.assertFalse(a.playing())


if __name__ == "__main__":
    unittest.main()
