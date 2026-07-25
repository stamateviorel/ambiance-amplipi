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
import os
import threading
import time

from . import sdnotify
from .hardware import preamp


class HealthMonitor:
    def __init__(self, ctl, interval=15):
        self.ctl = ctl
        self.interval = max(5, int(interval))
        self._last_recoveries = 0
        self.state = {"ok": True, "issues": [], "mpd": "ok", "preamp": "ok",
                      "recoveries": 0, "checked": 0}

    def _sweep(self):
        radio = self.ctl.radio
        mpd_ok, mpd_detail = radio.health()

        # self-heal a genuine drop (intended-to-play stream that stopped/errored).
        # LOG it: this is the most common self-heal, and without a line here the box keeps
        # no record of an outage it fixed itself (only openHAB's item history showed it).
        if radio.desired_playing and not mpd_ok:
            print("[health] radio unhealthy (%s) -> recovering" % (mpd_detail or "onbekend"))
            try:
                if radio.recover():
                    time.sleep(2)
                    mpd_ok, mpd_detail = radio.health()
                    print("[health] radio recovery %s" % ("OK" if mpd_ok else
                                                          "FAILED (%s)" % (mpd_detail or "onbekend")))
                else:
                    print("[health] radio recovery could not issue a replay")
            except Exception as exc:
                print("[health] radio recovery raised: %s" % exc)

        pre = preamp.preamp_health()

        # A preamp I2C wedge self-heals in the low-level layer (reset + re-flush of its OWN register
        # cache), but that can leave the hardware driven from a stale/incomplete cache — every zone
        # silent (the siren too) while the logical state still says it is on, until a restart. On any
        # NEW recovery, re-apply the routing from the authoritative zone state so audio self-recovers.
        recoveries = pre.get("recoveries", 0)
        if recoveries > self._last_recoveries:
            self._last_recoveries = recoveries
            try:
                self.ctl.zones.reapply()
                print("[health] preamp self-healed (recoveries=%d) -> re-applied zone routing" % recoveries)
            except Exception as exc:
                print("[health] reapply after preamp recovery failed: %s" % exc)

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
        if sdnotify.watchdog_enabled():
            print("[health] systemd watchdog armed (%ss) — pinging after each sweep"
                  % (int(os.environ.get("WATCHDOG_USEC", 0)) // 1000000))
        while True:
            try:
                self.state = self._sweep()
                # Feed the systemd watchdog only after a COMPLETED sweep: if the sweep wedges
                # (mpd/preamp hung), the pings stop and systemd restarts us. Restart=always
                # alone cannot catch that — a hung process never exits.
                sdnotify.notify("WATCHDOG=1")
            except Exception:
                # never let the monitor thread die — a broken sweep must not take audio down
                pass
            time.sleep(self.interval)

    def start(self):
        threading.Thread(target=self._run, name="ambiance-health", daemon=True).start()
