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
    def __init__(self, zone_defs, hw="mock", power=None, on_power_change=None):
        # zone_defs: list of {"id", "name", "default_pct"} — driven by declarative config
        self.lock = threading.RLock()
        self.n = len(zone_defs)
        self.names = [z["name"] for z in zone_defs]
        self.vol = [int(z.get("default_pct", 50)) for z in zone_defs]
        self.muted = [False] * self.n          # user mute (widget)
        # Zone power (motion: music-follows-you). Restored from the persisted state when
        # given, so a service restart does not silently switch every zone back ON and blast
        # audio through the whole house; defaults to ON only on a first/unknown start.
        self.power = list(power) if power and len(power) == self.n else [True] * self.n
        self._on_power_change = on_power_change   # persist hook (set by the controller)
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

    def _write_mutes_vols(self, siren):
        """Write the audibility-critical registers (mutes + per-zone volume). siren=True forces
        every zone audible at full volume; otherwise the logical mute/power/vol state."""
        if siren:
            self.rt.update_zone_mutes(0, self._pad6([False] * self.n, True))
            for z in range(self.n):
                self.rt.update_zone_vol(z, MAX_DB)
        else:
            self.rt.update_zone_mutes(0, self._pad6(self._eff(), True))
            for z in range(self.n):
                self.rt.update_zone_vol(z, pct_to_db(self.vol[z]))

    def _write_routing(self, siren):
        """Full re-drive: source assignment + mutes + volumes."""
        self.rt.update_zone_sources(0, self._pad6([0] * self.n, 0))  # everything on source 0
        self._write_mutes_vols(siren)

    def _apply_all(self):
        self._write_routing(False)

    def reapply(self):
        """Re-drive the WHOLE preamp routing (sources+mutes+vols) from the authoritative logical
        state. Called by the health watchdog after a preamp self-heal: an I2C wedge reset leaves the
        hardware at silent defaults, and the low-level in-place recovery re-flushes only its OWN
        register cache — which can be stale/incomplete — so a zone (and the burglar siren) can stay
        silently dead while the code believes everything is fine. Re-applying from the zone state
        recovers audio on its own instead of needing a service restart. Siren-aware."""
        with self.lock:
            self._write_routing(self._siren)

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
            changed = self.power[z] != bool(on)
            self.power[z] = bool(on)
            if not self._siren:                          # can't power a zone down while the siren blasts
                self.rt.update_zone_mutes(0, self._pad6(self._eff(), True))
        # persist OUTSIDE the lock, and only on a real change — the siren's forced-on state is
        # never written (it is not the user's intent, just the alarm holding the zones open)
        if changed and not self._siren and self._on_power_change:
            try:
                self._on_power_change(list(self.power))
            except Exception as exc:
                print("[zones] persisting power state failed: %s" % exc)

    def set_master_mute(self, on):
        for z in range(self.n):
            self.set_mute(z, on)

    def siren(self, on):
        with self.lock:
            self._siren = bool(on)                            # lock: set_* now update state only
            # Re-drive EVERYTHING (incl. the source assignment) so the siren survives a wedged or
            # just-reset preamp; on release this applies the logical state (reflecting anything
            # commanded during the alarm).
            self._write_routing(self._siren)

    def reassert_siren(self):
        """Re-drive the FULL preamp routing (source+mutes+vols) each siren loop — a watchdog belt so
        even a preamp glitch, an out-of-band write, or a mid-alarm I2C wedge+reset can't leave the
        siren quiet. No-op when the siren is off."""
        with self.lock:
            if self._siren:
                self._write_routing(True)

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
