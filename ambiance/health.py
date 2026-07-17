"""Background health monitor for ambiance-amplipi.

Runs one lightweight sweep every `interval` seconds in a daemon thread:

  * self-heals a DROPPED radio stream — only when the service intended to be playing
    (`radio.desired_playing`), so it never fights an intentional stop (music-follows-you
    going away, a user pause, the siren pausing the radio);
  * reads the preamp I2C health surfaced by `hardware.preamp` (the low-level layer already
    self-heals a wedged preamp in place; this only reports when that self-heal could not
    fix it and a human should look);
  * caches a compact `state` dict that `/api/status` returns, so the openHAB binding can
    expose it on a channel and push a notification — without every status poll re-running
    the mpc/preamp checks.

The cached `state` matches models.Health.
"""
import threading
import time

from .hardware import preamp


class HealthMonitor:
    def __init__(self, ctl, interval=15):
        self.ctl = ctl
        self.interval = max(5, int(interval))
        self.state = {"ok": True, "issues": [], "mpd": "ok", "preamp": "ok",
                      "recoveries": 0, "checked": 0}

    def _sweep(self):
        radio = self.ctl.radio
        mpd_ok, mpd_detail = radio.health()

        # self-heal a genuine drop (intended-to-play stream that stopped/errored)
        if radio.desired_playing and not mpd_ok:
            try:
                if radio.recover():
                    time.sleep(2)
                    mpd_ok, mpd_detail = radio.health()
            except Exception:
                pass

        pre = preamp.preamp_health()

        issues = []
        if not mpd_ok:
            issues.append("Radio: %s" % (mpd_detail or "mpd-fout"))
        if not pre["ok"]:
            issues.append("Versterker: I2C-fout, automatisch herstel mislukt")

        return {
            "ok": not issues,
            "issues": issues,
            "mpd": "ok" if mpd_ok else (mpd_detail or "fout"),
            "preamp": "ok" if pre["ok"] else "wedged",
            "recoveries": pre.get("recoveries", 0),
            "checked": int(time.time()),
        }

    def _run(self):
        while True:
            try:
                self.state = self._sweep()
            except Exception:
                # never let the monitor thread die — a broken sweep must not take audio down
                pass
            time.sleep(self.interval)

    def start(self):
        threading.Thread(target=self._run, name="ambiance-health", daemon=True).start()
