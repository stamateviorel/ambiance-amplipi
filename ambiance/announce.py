"""Public-address announcements on ch0boost.

openHAB's binding (a native audio sink) synthesizes the TTS and POSTs the audio URL to
/api/announce; we duck the radio (Ch0 Volume softvol), aplay it on ch0boost, then restore.
Queued so a burst never overlaps. The siren overrides speech (safety first) — `is_busy`
lets the app skip announcements while the siren is active. No ffmpeg: plain-WAV aplay.
"""
import os
import queue
import re
import subprocess
import tempfile
import threading
import urllib.request


class Announcer:
    def __init__(self, dev="ch0boost", vol_ctl="Ch0 Volume", duck_pct=45, dry=False, is_busy=None):
        self.dev = dev
        self.vol_ctl = vol_ctl
        self.duck = duck_pct
        self.dry = dry
        self.is_busy = is_busy or (lambda: False)     # e.g. siren active -> drop speech
        self.q = queue.Queue(maxsize=20)
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

    def say(self, url):
        try:
            self.q.put_nowait(url)
            return True
        except queue.Full:
            return False

    def state(self):
        return {"queue": self.q.qsize(), "dev": self.dev, "duck": self.duck, "dry": self.dry}

    def _worker(self):
        while True:
            url = self.q.get()
            if self.is_busy():          # siren owns the audio path
                continue
            saved = self._radio_pct()
            fd, path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                urllib.request.urlretrieve(url, path)
                self._set_radio(self.duck)
                self._run(["aplay", "-q", "-D", self.dev, path])
            except Exception as e:
                print("announce error: %s" % e)
            finally:
                self._set_radio(saved)
                try:
                    os.unlink(path)
                except OSError:
                    pass
