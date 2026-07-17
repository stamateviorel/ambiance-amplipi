"""Album art for the current now-playing, in three tiers so there is ALWAYS something to show:

  1. track art   — iTunes Search by "Artist - Track" (when the stream broadcasts it);
  2. station logo — the station's configured logo URL (stations.conf optional 3rd field),
                    normalised to a 300px JPEG;
  3. station tile — a generated card (station name on a colour derived from the name; no
                    network, always works) for station-name-only streams.

The Pi has internet; the openHAB host does not — so ambiance fetches/creates + caches the JPEG
and serves it at /api/cover for the binding widget, the web UI and the front screen.
"""
import colorsys
import hashlib
import io
import json
import threading
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont

_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _font(sz):
    try:
        return ImageFont.truetype(_FONT, sz)
    except Exception:
        return ImageFont.load_default()


class Cover:
    def __init__(self):
        self.lock = threading.Lock()
        self._key = None
        self._data = None

    # tier 1 — real track artwork
    def _track(self, title):
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

    # tier 2 — configured station logo, centred on a dark 300px canvas
    def _logo(self, url):
        try:
            raw = urllib.request.urlopen(url, timeout=6).read()
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img.thumbnail((300, 300))
            canvas = Image.new("RGB", (300, 300), (20, 20, 26))
            canvas.paste(img, ((300 - img.width) // 2, (300 - img.height) // 2))
            return self._jpeg(canvas)
        except Exception:
            return None

    # tier 3 — generated station-name tile (no network)
    def _tile(self, name):
        try:
            name = (name or "Radio").strip()
            hue = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % 360
            r, g, b = colorsys.hsv_to_rgb(hue / 360.0, 0.45, 0.42)
            img = Image.new("RGB", (300, 300), (int(r * 255), int(g * 255), int(b * 255)))
            d = ImageDraw.Draw(img)
            d.text((22, 16), "♪", font=_font(44), fill=(255, 255, 255))
            f = _font(30)
            words, lines, cur = name.split(), [], ""
            for w in words:
                t = (cur + " " + w).strip()
                if d.textlength(t, font=f) <= 256:
                    cur = t
                else:
                    lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
            lines = lines[:4]
            y = 150 - len(lines) * 20
            for ln in lines:
                d.text((22, y), ln, font=f, fill=(255, 255, 255))
                y += 40
            return self._jpeg(img)
        except Exception:
            return None

    @staticmethod
    def _jpeg(img):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return buf.getvalue()

    def bytes_for(self, title, logo_url=None, station=None):
        key = (title or "", logo_url or "", station or "")
        with self.lock:
            if self._key == key and self._data is not None:
                return self._data
            self._key = key
            data = self._track(title) if title else None
            if data is None and logo_url:
                data = self._logo(logo_url)
            if data is None and station:
                data = self._tile(station)
            self._data = data
            return self._data
