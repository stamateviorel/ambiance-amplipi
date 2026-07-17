"""Burglar siren on ch0boost.

Loops alarm.wav with aplay (per-iteration = self-healing; a crash just respawns next loop,
and there's no long-lived decoder to fall silent). Zone orchestration (pause radio, drive
all zones to full/unmuted, restore) is done by the app/controller. `selftest` validates the
WAV without making a sound (used by the daily openHAB check).
"""
import os
import subprocess
import threading
import time
import wave


class Siren:
    def __init__(self, alarm_wav, dev="ch0boost", dry=False):
        self.alarm = alarm_wav
        self.dev = dev
        self.dry = dry
        self.on_flag = False
        self.proc = None
        self.lock = threading.Lock()

    @property
    def active(self):
        return self.on_flag

    def on(self):
        with self.lock:
            if not self.on_flag:
                self.on_flag = True
                threading.Thread(target=self._loop, daemon=True).start()

    def off(self):
        with self.lock:
            if self.on_flag:
                self.on_flag = False
                p = self.proc
                if p is not None:
                    try:
                        p.terminate()      # unblock the loop's wait() so it re-checks on_flag
                    except Exception:
                        pass

    def _loop(self):
        while self.on_flag:
            if self.dry:
                print("DRY: aplay loop %s -> %s" % (self.alarm, self.dev))
                time.sleep(1)
                continue
            try:
                self.proc = subprocess.Popen(["aplay", "-q", "-D", self.dev, self.alarm])
                self.proc.wait()
            except Exception as e:
                print("siren loop error: %s" % e)
                time.sleep(0.5)
        self.proc = None

    def selftest(self):
        if not os.path.exists(self.alarm):
            return {"ok": False, "reason": "alarm file missing", "alarm": self.alarm}
        try:
            w = wave.open(self.alarm, "rb")
            rate, frames = w.getframerate(), w.getnframes()
            w.close()
            return {"ok": True, "alarm": self.alarm, "rate": rate, "dur": round(frames / float(rate), 2)}
        except Exception as e:
            return {"ok": False, "reason": "not a valid WAV: %s" % e, "alarm": self.alarm}
