"""Spotify Connect source, backed by go-librespot (a static Go binary in its own systemd
unit, `ambiance-spotify.service`).

Audio is NOT routed through this class: go-librespot outputs straight to ALSA `ch0`,
joining the same softvol + dmix as the radio — so the announcement duck, the source
volume and the siren's dominance apply to Spotify automatically. This class only watches
and steers the daemon over its local REST API (pause/resume/next/prev, now-playing
metadata incl. album art URL), and fires `on_playing` when a phone starts playback so the
source arbiter can make the radio yield.

The poll thread caches the state — /api/status readers never hit the daemon directly.
Implements the Sources adapter interface (playing/pause/resume/next/prev/can_resume).
"""
import json
import threading
import time
import urllib.request

_EMPTY = {"running": False, "playing": False, "track": "", "artist": "", "album": "", "cover": ""}


class Spotify:
    def __init__(self, api="http://127.0.0.1:3678", interval=2, on_playing=None):
        self.api = api.rstrip("/")
        self.interval = max(1, int(interval))
        self.on_playing = on_playing or (lambda: None)
        self._state = dict(_EMPTY)
        self._was_playing = False

    # ---- daemon API ----
    def _get_status(self):
        with urllib.request.urlopen(self.api + "/status", timeout=2) as r:
            raw = r.read()
        # go-librespot answers 204/empty until the first phone session -> daemon up, idle
        return json.loads(raw.decode()) if raw.strip() else {}

    def _post(self, path):
        try:
            req = urllib.request.Request(self.api + path, data=b"{}",
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=2).read()
            return True
        except Exception:
            return False

    @staticmethod
    def parse(d):
        """go-librespot GET /status -> our compact state dict (pure, testable)."""
        track = d.get("track") or {}
        artists = [a for a in (track.get("artist_names") or []) if a]
        # `stopped` defaults True so an EMPTY status (no session yet) is idle, not playing
        return {"running": True,
                "playing": not d.get("stopped", True) and not d.get("paused"),
                "track": track.get("name") or "",
                "artist": ", ".join(artists),
                "album": track.get("album_name") or "",
                "cover": track.get("album_cover_url") or ""}

    # ---- poll thread (state cache + start-detection) ----
    def poll_once(self):
        try:
            st = self.parse(self._get_status())
        except Exception:
            st = dict(_EMPTY)          # daemon down/not installed -> inert
        self._state = st
        if st["playing"] and not self._was_playing:
            try:
                self.on_playing()      # phone started playback -> the radio yields
            except Exception:
                pass
        self._was_playing = st["playing"]

    def start(self):
        def run():
            while True:
                self.poll_once()
                time.sleep(self.interval)
        threading.Thread(target=run, name="ambiance-spotify", daemon=True).start()

    # ---- state + Sources adapter interface ----
    def state(self):
        return dict(self._state)

    def playing(self):
        return self._state["playing"]

    def can_resume(self):
        # a resumable session = daemon up AND a track loaded (a dead/absent phone session
        # cannot be resumed -> the caller falls back to the radio)
        return self._state["running"] and bool(self._state["track"])

    def pause(self):
        return self._post("/player/pause")

    def resume(self):
        return self._post("/player/resume")

    def next(self):
        return self._post("/player/next")

    def prev(self):
        return self._post("/player/prev")
