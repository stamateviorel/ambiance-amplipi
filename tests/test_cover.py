"""Cover art: tier-1 song-art search (mocked network — REGRESSION test for the space-joined
"Artist Song" term), the tier-3 generated station tile (no network), and tier ordering.
(Tier 2 — logo fetch — still hits the network and is not unit-tested.)"""
import json
import unittest
from unittest import mock

from ambiance.cover import Cover


def _itunes_urlopen(art_bytes=b"\xff\xd8ARTDATA"):
    """A fake urllib.request.urlopen: answers the iTunes search + the artwork download."""
    calls = []

    def fake(url, timeout=0):
        calls.append(url)

        class R:
            def read(self):
                if "itunes.apple.com" in url:
                    return json.dumps({"resultCount": 1,
                                       "results": [{"artworkUrl100": "http://art/100x100bb.jpg"}]
                                       }).encode()
                return art_bytes

        return R()

    return fake, calls


class TestCoverTrack(unittest.TestCase):
    def test_space_joined_term_searches(self):
        # REGRESSION: app.py passes "Artist Song" (space-joined, NO " - " separator) since
        # cfdb599 — the search must fire on it (the old separator gate silently killed tier 1).
        fake, calls = _itunes_urlopen()
        with mock.patch("ambiance.cover.urllib.request.urlopen", fake):
            data = Cover()._track("Coldplay Yellow")
        self.assertEqual(data, b"\xff\xd8ARTDATA")
        self.assertIn("term=Coldplay%20Yellow", calls[0])
        self.assertIn("300x300bb", calls[1])          # upscaled artwork URL

    def test_dash_form_still_normalised(self):
        fake, calls = _itunes_urlopen()
        with mock.patch("ambiance.cover.urllib.request.urlopen", fake):
            data = Cover()._track("Coldplay - Yellow")
        self.assertEqual(data, b"\xff\xd8ARTDATA")
        self.assertIn("term=Coldplay%20Yellow", calls[0])   # separator collapsed to a space

    def test_empty_term_no_search(self):
        fake, calls = _itunes_urlopen()
        with mock.patch("ambiance.cover.urllib.request.urlopen", fake):
            self.assertIsNone(Cover()._track("  "))
        self.assertEqual(calls, [])                    # no network touched

    def test_track_art_beats_tile(self):
        # tier ordering: with real metadata the song art wins over the station tile
        fake, _ = _itunes_urlopen()
        with mock.patch("ambiance.cover.urllib.request.urlopen", fake):
            data = Cover().bytes_for("Coldplay Yellow", None, "VRT Radio 1")
        self.assertEqual(data, b"\xff\xd8ARTDATA")


class TestCoverTile(unittest.TestCase):
    def test_generated_tile_is_jpeg(self):
        data = Cover().bytes_for("", None, "VRT Radio 1")   # no metadata -> tile
        self.assertIsNotNone(data)
        self.assertEqual(data[:2], b"\xff\xd8")   # JPEG magic
        self.assertGreater(len(data), 1000)

    def test_no_station_no_cover(self):
        self.assertIsNone(Cover().bytes_for("", None, None))

    def test_tile_is_deterministic(self):
        a = Cover().bytes_for("", None, "Klara")
        b = Cover().bytes_for("", None, "Klara")
        self.assertEqual(a, b)   # same station -> same tile bytes


if __name__ == "__main__":
    unittest.main()
