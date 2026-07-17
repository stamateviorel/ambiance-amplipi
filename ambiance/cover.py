"""Album art for the current now-playing ("Artist - Track" from ICY) via the free/keyless
iTunes Search API. The Pi has internet; the openHAB host does not — so ambiance fetches +
caches the JPEG and serves it at /api/cover, and the openHAB binding pulls it into the
widget's Image item. Best-effort: stations that broadcast only their name yield no cover.
"""
import json
import threading
import urllib.parse
import urllib.request


class Cover:
    def __init__(self):
        self.lock = threading.Lock()
        self._title = None
        self._data = None

    def _fetch(self, title):
        sep = " - " if " - " in title else (" – " if " – " in title else None)
        if not sep:
            return None
        try:
            q = urllib.parse.quote(title.replace(sep, " "))
            u = "https://itunes.apple.com/search?term=%s&entity=song&limit=1" % q
            d = json.loads(urllib.request.urlopen(u, timeout=6).read())
            if d.get("resultCount"):
                art = d["results"][0]["artworkUrl100"].replace("100x100bb", "300x300bb")
                return urllib.request.urlopen(art, timeout=6).read()
        except Exception:
            pass
        return None

    def bytes_for(self, title):
        with self.lock:
            if self._title == title and self._data is not None:
                return self._data
            self._title = title
            self._data = self._fetch(title) if title else None
            return self._data
