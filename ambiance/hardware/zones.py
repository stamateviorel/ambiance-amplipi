"""6-zone AmpliPi preamp control, over the vendored `preamp` layer.

Pure library (no HTTP — the FastAPI app wraps this). Effective silence for a zone is
`user-mute OR powered-off`, so the openHAB widget's Mute and motion's Power stay
independent (a deliberately-muted zone is not un-silenced when motion powers it on).
Siren snapshots the whole zone state, drives everything to full/unmuted, and restores
on release. All zones play source 0 (the radio/announce mix).
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
        self._saved = None                     # siren snapshot
        # rt.Rpi() RESETS the preamps on construct — only pass hw="rpi" once amplipi.service
        # is stopped (i.e. at cutover). Default Mock is safe everywhere.
        self.rt = preamp.Rpi() if hw == "rpi" else preamp.Mock()
        self._apply_all()

    def _eff(self):
        return [self.muted[z] or (not self.power[z]) for z in range(self.n)]

    def _apply_all(self):
        self.rt.update_zone_sources(0, [0] * self.n)      # everything on source 0
        self.rt.update_zone_mutes(0, self._eff())
        for z in range(self.n):
            self.rt.update_zone_vol(z, pct_to_db(self.vol[z]))

    def set_vol(self, z, pct):
        with self.lock:
            self.vol[z] = max(0, min(100, int(pct)))
            self.rt.update_zone_vol(z, pct_to_db(self.vol[z]))

    def set_mute(self, z, on):
        with self.lock:
            self.muted[z] = bool(on)
            self.rt.update_zone_mutes(0, self._eff())

    def set_power(self, z, on):
        with self.lock:
            self.power[z] = bool(on)
            self.rt.update_zone_mutes(0, self._eff())

    def set_master_mute(self, on):
        for z in range(self.n):
            self.set_mute(z, on)

    def siren(self, on):
        with self.lock:
            if on:
                if self._saved is None:                    # snapshot once
                    self._saved = (list(self.vol), list(self.muted), list(self.power))
                self.muted = [False] * self.n
                self.power = [True] * self.n
                self.rt.update_zone_mutes(0, [False] * self.n)   # all audible, override
                for z in range(self.n):
                    self.rt.update_zone_vol(z, MAX_DB)     # full blast, all zones
            else:
                if self._saved is not None:
                    self.vol, self.muted, self.power = self._saved
                    self._saved = None
                self.rt.update_zone_mutes(0, self._eff())
                for z in range(self.n):
                    self.rt.update_zone_vol(z, pct_to_db(self.vol[z]))

    @property
    def siren_active(self):
        return self._saved is not None

    def master_mute(self):
        return self.n > 0 and all(self.muted)

    def snapshot(self):
        with self.lock:
            return [{"id": z, "name": self.names[z], "vol": self.vol[z],
                     "mute": self.muted[z], "power": self.power[z]} for z in range(self.n)]
