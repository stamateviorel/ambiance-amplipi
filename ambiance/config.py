"""Declarative config for ambiance — no mutable house.json. Values come from the
environment (AMBIANCE_*) with a zones file (`id|name|default_pct`). Fail-safe defaults:
hardware = Mock and audio = dry unless explicitly set live (so a missing/edited config can
never surprise-play audio or reset the real preamps).
"""
import os


def _load_zones(path):
    zones = []
    try:
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = (line.split("|") + ["", ""])[:3]
            zones.append({"id": int(parts[0]), "name": parts[1].strip(),
                          "default_pct": int(parts[2] or 50)})
    except Exception:
        pass
    return zones


# Reference deployment defaults (this site). A shareable install overrides via env + files.
_DEFAULT_ZONES = [{"id": i, "name": n, "default_pct": p} for i, (n, p) in enumerate(
    [("Office", 70), ("Wc up", 59), ("Main area", 80),
     ("Kitchen", 70), ("Wc down", 60), ("Showroom", 39)])]


class Config:
    def __init__(self):
        base = os.environ.get("AMBIANCE_DIR", "/home/pi/ambiance-amplipi")
        self.zones_file = os.environ.get("AMBIANCE_ZONES", base + "/config/zones.conf")
        self.stations_file = os.environ.get("AMBIANCE_STATIONS", base + "/config/stations.conf")
        self.alarm_wav = os.environ.get("AMBIANCE_ALARM", base + "/assets/alarm.wav")
        self.zones = _load_zones(self.zones_file) or _DEFAULT_ZONES
        self.hw = os.environ.get("AMBIANCE_HW", "mock")               # mock | rpi (rpi resets preamps)
        self.dry = os.environ.get("AMBIANCE_DRY", "1") == "1"          # fail-safe: dry unless =0
        self.announce_dev = os.environ.get("AMBIANCE_ANNOUNCE_DEV", "ch0boost")
        self.vol_ctl = os.environ.get("AMBIANCE_VOL_CTL", "Ch0")   # the ch0 softvol amixer control
        self.duck_pct = int(os.environ.get("AMBIANCE_DUCK_PCT", "45"))
        self.mpd_host = os.environ.get("AMBIANCE_MPD_HOST", "127.0.0.1")
        self.mpd_port = int(os.environ.get("AMBIANCE_MPD_PORT", "6600"))
        self.port = int(os.environ.get("AMBIANCE_PORT", "8080"))
