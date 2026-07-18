"""Spotify (go-librespot client): status parsing, start-event detection, control POSTs.
All mocked — no daemon, no network."""
import unittest
from unittest import mock

from ambiance.spotify import Spotify

PLAYING = {"stopped": False, "paused": False,
           "track": {"name": "Yellow", "artist_names": ["Coldplay"],
                     "album_name": "Parachutes", "album_cover_url": "http://art/x.jpg"}}
PAUSED = {"stopped": False, "paused": True, "track": {"name": "Yellow", "artist_names": ["Coldplay"]}}
STOPPED = {"stopped": True, "paused": False}


class TestParse(unittest.TestCase):
    def test_playing(self):
        st = Spotify.parse(PLAYING)
        self.assertTrue(st["running"])
        self.assertTrue(st["playing"])
        self.assertEqual(st["track"], "Yellow")
        self.assertEqual(st["artist"], "Coldplay")
        self.assertEqual(st["album"], "Parachutes")
        self.assertEqual(st["cover"], "http://art/x.jpg")

    def test_paused_and_stopped_not_playing(self):
        self.assertFalse(Spotify.parse(PAUSED)["playing"])
        self.assertFalse(Spotify.parse(STOPPED)["playing"])

    def test_missing_track_safe(self):
        st = Spotify.parse(STOPPED)
        self.assertEqual((st["track"], st["artist"], st["album"], st["cover"]), ("", "", "", ""))

    def test_empty_status_is_running_but_idle(self):
        # go-librespot answers 204/{} until the first phone session connects
        st = Spotify.parse({})
        self.assertTrue(st["running"])
        self.assertFalse(st["playing"])   # an empty payload must NEVER read as playing
        self.assertEqual(st["track"], "")


class TestPollTransitions(unittest.TestCase):
    def test_on_playing_fires_once_per_start(self):
        hits = []
        sp = Spotify(on_playing=lambda: hits.append(1))
        answers = [PLAYING, PLAYING, PAUSED, PLAYING]
        sp._get_status = lambda: answers.pop(0)
        sp.poll_once()                       # -> playing: fires
        sp.poll_once()                       # still playing: no re-fire
        sp.poll_once()                       # paused
        sp.poll_once()                       # playing again: fires
        self.assertEqual(len(hits), 2)

    def test_daemon_down_is_inert(self):
        hits = []
        sp = Spotify(on_playing=lambda: hits.append(1))

        def boom():
            raise OSError("connection refused")
        sp._get_status = boom
        sp.poll_once()
        st = sp.state()
        self.assertFalse(st["running"])
        self.assertFalse(sp.playing())
        self.assertFalse(sp.can_resume())
        self.assertEqual(hits, [])


class TestControls(unittest.TestCase):
    def test_posts_hit_player_endpoints(self):
        calls = []

        def fake_urlopen(req, timeout=0):
            calls.append(req.get_full_url())

            class R:
                def read(self):
                    return b"{}"
            return R()

        sp = Spotify(api="http://127.0.0.1:3678")
        with mock.patch("ambiance.spotify.urllib.request.urlopen", fake_urlopen):
            self.assertTrue(sp.pause())
            self.assertTrue(sp.resume())
            self.assertTrue(sp.next())
            self.assertTrue(sp.prev())
        self.assertEqual(calls, ["http://127.0.0.1:3678/player/pause",
                                 "http://127.0.0.1:3678/player/resume",
                                 "http://127.0.0.1:3678/player/next",
                                 "http://127.0.0.1:3678/player/prev"])

    def test_post_failure_returns_false(self):
        sp = Spotify(api="http://127.0.0.1:1")   # nothing listens
        self.assertFalse(sp.pause())


if __name__ == "__main__":
    unittest.main()
