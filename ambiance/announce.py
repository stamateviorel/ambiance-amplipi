"""Public-address announcements on ch0boost.

openHAB's binding (a native audio sink) synthesizes the TTS and POSTs the audio URL to
/api/announce; we duck the radio (Ch0 softvol), aplay it on ch0boost, then restore. Queued
so a burst never overlaps. The siren overrides speech (safety first) — `is_busy` lets the
app skip announcements while the siren is active. No ffmpeg: plain-WAV aplay.

The download is time-bounded (a hung TTS server must never wedge the worker), the duck is
restored only if nobody moved the source volume mid-announce, and an optional per-message
`vol` drives the boost channel for that one announcement (restored afterwards; the siren
re-forces the boost to 100% each loop regardless, so this can never weaken the alarm).
"""
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request

FETCH_TIMEOUT_S = 10


class Announcer:
    def __init__(self, dev="ch0boost", vol_ctl="Ch0", duck_pct=45, dry=False, is_busy=None,
                 boost=None):
        self.dev = dev
        self.vol_ctl = vol_ctl
        self.duck = duck_pct
        self.dry = dry
        self.is_busy = is_busy or (lambda: False)     # e.g. siren active -> drop speech
        self.boost = boost                            # Source for the announce channel (optional vol)
        self.q = queue.Queue(maxsize=20)              # of (url, vol-or-None)
        threading.Thread(target=self._worker, daemon=True).start()

    def _run(self, cmd):
        if self.dry:
            print("DRY:", " ".join(map(str, cmd)))
            return 0
        return subprocess.call(cmd)

    def _radio_pct(self):
        if self.dry:
            return 100
        try:
            out = subprocess.check_output(["amixer", "-c", "0", "sget", self.vol_ctl]).decode()
            m = re.search(r"\[(\d+)%\]", out)
            return int(m.group(1)) if m else 100
        except Exception:
            return 100

    def _set_radio(self, pct):
        self._run(["amixer", "-c", "0", "sset", self.vol_ctl, "%d%%" % pct])

    def _fetch(self, url, path):
        # bounded download — a dead/hung server raises instead of blocking the worker forever
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_S) as r, open(path, "wb") as f:
            shutil.copyfileobj(r, f)

    def say(self, url, vol=None):
        try:
            self.q.put_nowait((url, vol))
            return True
        except queue.Full:
            return False

    def state(self):
        return {"queue": self.q.qsize(), "dev": self.dev, "duck": self.duck, "dry": self.dry}

    def _worker(self):
        while True:
            url, vol = self.q.get()
            if self.is_busy():          # siren owns the audio path
                continue
            saved = self._radio_pct()
            boost_prev = None
            fd, path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                self._fetch(url, path)
                self._set_radio(self.duck)
                if vol is not None and self.boost is not None:
                    boost_prev = self.boost.vol()
                    self.boost.set_vol(vol)
                self._run(["aplay", "-q", "-D", self.dev, path])
            except Exception as e:
                print("announce error: %s" % e)
            finally:
                if boost_prev is not None:
                    self.boost.set_vol(boost_prev)
                # undo the duck ONLY if the source is still at the duck level — if a user/rule
                # changed the volume mid-announce, keep THEIR value instead of stomping it.
                if self.dry or self._radio_pct() == self.duck:
                    self._set_radio(saved)
                try:
                    os.unlink(path)
                except OSError:
                    pass
