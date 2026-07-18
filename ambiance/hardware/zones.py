"""6-zone AmpliPi preamp control, over the vendored `preamp` layer.

Pure library (no HTTP — the FastAPI app wraps this). Effective silence for a zone is
`user-mute OR powered-off`, so the openHAB widget's Mute and motion's Power stay
independent (a deliberately-muted zone is not un-silenced when motion powers it on).
The burglar siren LOCKS the preamp at full/unmuted/on. While it's active EVERY zone
command (mute/power/volume) updates only the remembered state — never the live preamp —
so nothing (music-follows-you, an openHAB command, master-mute, a low volume) can quiet
it. On release the remembered state (including anything changed during the siren) is
applied. All zones play source 0 (the radio/announce mix).
"""
import threading

from . import preamp

MIN_DB, MAX_DB = preamp.MIN_VOL_DB, preamp.MAX_VOL_DB


def pct_to_db(pct):
    pct = max(0, min(100, int(pct)))
    return round(pct / 100.0 * (MAX_DB - MIN_DB) + MIN_DB)


def db_to_pct(db):
    return round((db - MIN_DB) / float(MAX_DB - MIN_DB) * 100)


class Zones:
    def __init__(self, zone_defs, hw="mock"):
        # zone_defs: list of {"id", "name", "default_pct"} — driven by declarative config
        self.lock = threading.RLock()
        self.n = len(zone_defs)
        self.names = [z["name"] for z in zone_defs]
        self.vol = [int(z.get("default_pct", 50)) for z in zone_defs]
        self.muted = [False] * self.n          # user mute (widget)
        self.power = [True] * self.n           # zone power (motion: music-follows-you)
        self._siren = False                    # burglar siren active -> preamp locked at full
        # rt.Rpi() RESETS the preamps on construct — only pass hw="rpi" once amplipi.service
        # is stopped (i.e. at cutover). Default Mock is safe everywhere.
        self.rt = preamp.Rpi() if hw == "rpi" else preamp.Mock()
        self._apply_all()

    def _eff(self):
        return [self.muted[z] or (not self.power[z]) for z in range(self.n)]

    @staticmethod
    def _pad6(lst, fill):
        """Pad a per-zone list to a whole preamp board (multiple of 6) — the hardware
        layer asserts that. Zones beyond the configured count stay muted/source-0, so a
        4-zone zones.conf works instead of crashing at startup."""
        return lst + [fill] * ((-len(lst)) % 6)

    def _apply_all(self):
        self.rt.update_zone_sources(0, self._pad6([0] * self.n, 0))  # everything on source 0
        self.rt.update_zone_mutes(0, self._pad6(self._eff(), True))
        for z in range(self.n):
            self.rt.update_zone_vol(z, pct_to_db(self.vol[z]))

    def set_vol(self, z, pct):
        with self.lock:
            if not 0 <= z < self.n:                      # a negative id would wrap in Python
                return
            self.vol[z] = max(0, min(100, int(pct)))
            if not self._siren:                          # siren locks the preamp at full
                self.rt.update_zone_vol(z, pct_to_db(self.vol[z]))

    def set_mute(self, z, on):
        with self.lock:
            if not 0 <= z < self.n:
                return
            self.muted[z] = bool(on)
            if not self._siren:                          # can't mute a zone while the siren blasts
                self.rt.update_zone_mutes(0, self._pad6(self._eff(), True))

    def set_power(self, z, on):
        with self.lock:
            if not 0 <= z < self.n:
                return
            self.power[z] = bool(on)
            if not self._siren:                          # can't power a zone down while the siren blasts
                self.rt.update_zone_mutes(0, self._pad6(self._eff(), True))

    def set_master_mute(self, on):
        for z in range(self.n):
            self.set_mute(z, on)

    def siren(self, on):
        with self.lock:
            if on:
                self._siren = True                            # lock: set_* now update state only
                self.rt.update_zone_mutes(0, self._pad6([False] * self.n, True))  # every REAL zone audible
                for z in range(self.n):
                    self.rt.update_zone_vol(z, MAX_DB)        # full blast, all zones
            else:
                self._siren = False                           # unlock
                # apply the logical state (which reflects anything commanded during the siren)
                self.rt.update_zone_mutes(0, self._pad6(self._eff(), True))
                for z in range(self.n):
                    self.rt.update_zone_vol(z, pct_to_db(self.vol[z]))

    def reassert_siren(self):
        """Re-drive the preamp to full/unmuted — a watchdog belt so even a preamp glitch or
        an out-of-band write can't leave the siren quiet. No-op when the siren is off."""
        with self.lock:
            if self._siren:
                self.rt.update_zone_mutes(0, self._pad6([False] * self.n, True))
                for z in range(self.n):
                    self.rt.update_zone_vol(z, MAX_DB)

    def rename(self, z, name):
        with self.lock:
            if not 0 <= z < self.n:
                return False
            self.names[z] = name
            return True

    @property
    def siren_active(self):
        return self._siren

    def master_mute(self):
        with self.lock:
            if self._siren:      # actual output is unmuted while the alarm blasts
                return False
            return self.n > 0 and all(self.muted)

    def snapshot(self):
        with self.lock:
            if self._siren:      # while the alarm blasts, report the actual output (all full/on)
                return [{"id": z, "name": self.names[z], "vol": 100, "mute": False, "power": True}
                        for z in range(self.n)]
            return [{"id": z, "name": self.names[z], "vol": self.vol[z],
                     "mute": self.muted[z], "power": self.power[z]} for z in range(self.n)]
