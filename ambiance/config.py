"""Declarative config for ambiance — no mutable house.json. Values come from the
environment (AMBIANCE_*) with a zones file (`id|name|default_pct`). Fail-safe defaults:
hardware = Mock and audio = dry unless explicitly set live (so a missing/edited config can
never surprise-play audio or reset the real preamps).

zones.conf stays the single source of truth for zone names; the web UI's zone-rename
rewrites it ATOMICALLY via save_zones() (tmp+rename+.bak — same pattern as the station
list, never a half-written file).
"""
import os
import shutil
import tempfile


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


def _load_groups(path):
    """Zone groups: `Group Name | comma-separated zone ids`  (e.g. `Downstairs|2,3,4`)."""
    groups = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                name, _, ids = line.partition("|")
                zids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
                if name.strip() and zids:
                    groups.append({"name": name.strip(), "zones": zids})
    except Exception:
        pass
    return groups


def save_zones(path, zones):
    """Atomically rewrite zones.conf (used by the web UI's zone rename)."""
    header = ("# ambiance-amplipi — zones.conf   (id | name | default_volume_percent)\n"
              "# Editable from the web UI (tap a zone name); ids match the AmpliPi preamp channels.\n\n")
    body = "".join("%d|%s|%d\n" % (z["id"], z["name"], int(z.get("default_pct", 50)))
                   for z in zones)
    d = os.path.dirname(path) or "."
    try:
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".zones-", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(header + body)
        if os.path.exists(path):
            try:
                shutil.copy2(path, path + ".bak")
            except OSError:
                pass
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o644)
        except OSError:
            pass
        return True
    except Exception:
        return False


# Generic fallback, used ONLY when zones.conf is missing/empty. Real installs name their
# zones in config/zones.conf (this repo ships an example) — no site data lives in code.
_DEFAULT_ZONES = [{"id": i, "name": "Zone %d" % (i + 1), "default_pct": 50} for i in range(6)]


class Config:
    def __init__(self):
        base = os.environ.get("AMBIANCE_DIR", "/home/pi/ambiance-amplipi")
        self.zones_file = os.environ.get("AMBIANCE_ZONES", base + "/config/zones.conf")
        self.stations_file = os.environ.get("AMBIANCE_STATIONS", base + "/config/stations.conf")
        self.groups_file = os.environ.get("AMBIANCE_GROUPS", base + "/config/groups.conf")
        self.alarm_wav = os.environ.get("AMBIANCE_ALARM", base + "/assets/alarm.wav")
        self.zones = _load_zones(self.zones_file) or _DEFAULT_ZONES
        self.groups = _load_groups(self.groups_file)
        self.hw = os.environ.get("AMBIANCE_HW", "mock")               # mock | rpi (rpi resets preamps)
        self.dry = os.environ.get("AMBIANCE_DRY", "1") == "1"          # fail-safe: dry unless =0
        self.announce_dev = os.environ.get("AMBIANCE_ANNOUNCE_DEV", "ch0boost")
        self.vol_ctl = os.environ.get("AMBIANCE_VOL_CTL", "Ch0")   # the ch0 softvol amixer control
        self.duck_pct = int(os.environ.get("AMBIANCE_DUCK_PCT", "45"))
        self.mpd_host = os.environ.get("AMBIANCE_MPD_HOST", "127.0.0.1")
        self.mpd_port = int(os.environ.get("AMBIANCE_MPD_PORT", "6600"))
        # Spotify Connect source (go-librespot in ambiance-spotify.service). Enabled by
        # default: with the daemon absent it is simply reported not-running (inert).
        self.spotify = os.environ.get("AMBIANCE_SPOTIFY", "1") == "1"
        self.spotify_api = os.environ.get("AMBIANCE_SPOTIFY_API", "http://127.0.0.1:3678")
        self.port = int(os.environ.get("AMBIANCE_PORT", "8080"))
        self.health_interval = int(os.environ.get("AMBIANCE_HEALTH_INTERVAL", "15"))
