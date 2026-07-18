"""Internet radio via mpd, controlled with the `mpc` subprocess (python-mpd2 is not
installed on the Pi). Stations are a declarative list with atomic CRUD (temp+rename, one
.bak — never a half-written file); the FIRST entry is the default/boot station. Now-playing
comes from the stream's ICY StreamTitle ("Artist - Track" when the station broadcasts it).
"""
import os
import shutil
import subprocess
import tempfile
import threading


class Radio:
    def __init__(self, stations_file, mpd_host="127.0.0.1", mpd_port=6600):
        self.file = stations_file
        self.mpc_base = ["mpc", "-h", mpd_host, "-p", str(mpd_port)]
        self.lock = threading.Lock()
        self.stations = self._load()
        # Intended play-state: the health monitor self-heals only a DROPPED stream we meant
        # to be playing — never an intentional stop (e.g. music-follows-you going away).
        self.desired_playing = False
        # Name of the station we last put on. Authoritative for "what's playing" because
        # mpd expands .pls/.m3u stations to an inner CDN URL that no longer matches the
        # configured station URL — so reverse-matching the URL alone is unreliable.
        self.current_name = None

    # ---- mpc ----
    def _mpc(self, *args):
        try:
            return subprocess.check_output(self.mpc_base + list(args),
                                           stderr=subprocess.DEVNULL, timeout=8).decode()
        except Exception:
            return ""

    # ---- stations file (atomic write, one .bak) ----
    def _load(self):
        out = []
        try:
            with open(self.file) as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("|")
                    if len(parts) >= 2 and parts[1].strip():
                        st = {"name": parts[0].strip(), "url": parts[1].strip()}
                        if len(parts) >= 3 and parts[2].strip():   # optional logo URL
                            st["logo"] = parts[2].strip()
                        out.append(st)
        except Exception:
            pass
        return out

    def _save(self):
        header = ("# ambiance-amplipi station list (edited via the web UI / the API).\n"
                  "# Format:  Display Name | Stream URL | Logo URL(optional)  — FIRST entry = default (boot).\n\n")
        body = "".join("%s|%s%s\n" % (s["name"], s["url"], ("|" + s["logo"]) if s.get("logo") else "")
                       for s in self.stations)
        d = os.path.dirname(self.file) or "."
        try:
            fd, tmp = tempfile.mkstemp(dir=d, prefix=".stations-", suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                f.write(header + body)
            if os.path.exists(self.file):
                try:
                    shutil.copy2(self.file, self.file + ".bak")
                except OSError:
                    pass
            os.replace(tmp, self.file)
            try:
                os.chmod(self.file, 0o644)
            except OSError:
                pass
        except Exception:
            pass

    @staticmethod
    def _clean(s):
        return str(s or "").replace("|", " ").replace("\n", " ").replace("\r", " ").strip()

    # CRUD -> (ok, error)
    def add_station(self, name, url, logo=None):
        name, url, logo = self._clean(name), self._clean(url), self._clean(logo)
        if not name or not url:
            return False, "naam en URL vereist"
        with self.lock:
            if any(s["name"] == name for s in self.stations):
                return False, "naam bestaat al"
            st = {"name": name, "url": url}
            if logo:
                st["logo"] = logo
            self.stations.append(st)
            self._save()
        return True, None

    def update_station(self, orig, name, url, logo=None):
        orig, name, url, logo = self._clean(orig), self._clean(name), self._clean(url), self._clean(logo)
        if not name or not url:
            return False, "naam en URL vereist"
        with self.lock:
            i = next((k for k, s in enumerate(self.stations) if s["name"] == orig), -1)
            if i < 0:
                return False, "zender niet gevonden"
            if name != orig and any(s["name"] == name for s in self.stations):
                return False, "naam bestaat al"
            st = {"name": name, "url": url}
            if logo:
                st["logo"] = logo
            self.stations[i] = st
            self._save()
        return True, None

    def delete_station(self, name):
        name = self._clean(name)
        with self.lock:
            i = next((k for k, s in enumerate(self.stations) if s["name"] == name), -1)
            if i < 0:
                return False, "zender niet gevonden"
            del self.stations[i]
            self._save()
        return True, None

    def set_default(self, name):
        name = self._clean(name)
        with self.lock:
            i = next((k for k, s in enumerate(self.stations) if s["name"] == name), -1)
            if i < 0:
                return False, "zender niet gevonden"
            self.stations.insert(0, self.stations.pop(i))
            self._save()
        return True, None

    # ---- playback ----
    def _current(self):
        """The station dict currently on: the name we last played (survives .pls/.m3u
        URL expansion), else a reverse URL match for a name we don't have stored yet."""
        if self.current_name:
            s = next((s for s in self.stations if s["name"] == self.current_name), None)
            if s:
                return s
        url = self._mpc("-f", "%file%", "current").strip()
        return next((s for s in self.stations if s["url"] == url), None)

    def current_station(self):
        s = self._current()
        return s["name"] if s else None

    def current_station_logo(self):
        s = self._current()
        return s.get("logo") if s else None

    def now_playing(self):
        raw = self._mpc("-f", "%title%", "current").strip()   # ICY StreamTitle
        if not raw:
            # No ICY metadata (talk/news stream, or between tracks): fall back to the
            # station name so the now-playing is never blank. Matches the pre-migration
            # behaviour where the UI always showed at least which station is on.
            raw = self.current_station() or ""
        artist, track = "", raw
        for sep in (" - ", " – "):
            if sep in raw:
                artist, track = raw.split(sep, 1)
                break
        artist, track = artist.strip(), track.strip()
        # `track` is the primary line; `title` (the full StreamTitle) the secondary one.
        # With no "Artist - Song" split they are identical, so blank the secondary — the
        # widget shows both cards, and screen/web already show `station` + `title`.
        title = "" if track == raw else raw
        return {"title": title, "artist": artist, "track": track}

    def is_playing(self):
        return "[playing]" in self._mpc("status")

    def play_station(self, name):
        for s in self.stations:
            if s["name"] == name:
                self._mpc("clear")
                self._mpc("add", s["url"])
                self._mpc("play")
                self.desired_playing = True
                self.current_name = name
                return True
        return False

    def play(self):
        self.desired_playing = True
        self._mpc("play")

    def stop(self):
        self.desired_playing = False
        self._mpc("stop")

    def health(self):
        """(ok, detail): mpd reachable + no stream error. An intentional stop is healthy;
        only an unreachable mpd or a dropped/errored stream we meant to play is not."""
        st = self._mpc("status")
        if not st:
            return False, "mpd niet bereikbaar"
        if "ERROR" in st.upper():
            return False, "streamfout"
        if self.desired_playing and "[playing]" not in st:
            return False, "radio gestopt (drop)"
        return True, None

    def recover(self):
        """Re-establish a dropped/errored stream: clear the error + replay the current
        (or first) station. Returns True if a replay was issued."""
        cur = self.current_station()
        if cur and self.play_station(cur):
            return True
        if self.stations:
            return self.play_station(self.stations[0]["name"])
        return False

    def cycle(self, delta):
        names = [s["name"] for s in self.stations]
        if not names:
            return
        cur = self.current_station()
        i = names.index(cur) if cur in names else 0
        self.play_station(names[(i + delta) % len(names)])

    def ensure_default(self):
        # boot-to-radio: empty playlist (cold start) -> play the first station
        if not self._mpc("playlist").strip() and self.stations:
            self.play_station(self.stations[0]["name"])

    def state(self):
        playing = self.is_playing()
        # Blank the now-playing when stopped so the UI shows a name only while on air.
        np = self.now_playing() if playing else {"title": "", "artist": "", "track": ""}
        return {"playing": playing, "station": self.current_station(),
                "title": np["title"], "artist": np["artist"], "track": np["track"],
                "stations": [s["name"] for s in self.stations]}
