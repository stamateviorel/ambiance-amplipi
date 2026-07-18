"""System stats + power control for the web settings page.

Read-only health/stats (CPU, memory, disk, temperature, uptime, unit states) plus
reboot/shutdown of the Pi. Power actions shell out to `systemctl` via sudo and are no-ops
in dry mode (the fail-safe default) — so only a live install can actually reboot the box.
They need a sudoers drop-in giving the service user passwordless `systemctl reboot/poweroff`.
"""
import os
import subprocess
import time


def _run(cmd, timeout=4):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=timeout).decode()
    except Exception:
        return ""


class System:
    def __init__(self, services=None, dry=False):
        self.services = services or ["ambiance", "ambiance-mpd", "ambiance-display"]
        self.dry = dry

    def stats(self):
        return {
            "hostname": _run(["hostname"]).strip() or "ambiance",
            "uptime_s": self._uptime(),
            "cpu_pct": self._cpu(),
            "mem": self._mem(),
            "disk": self._disk(),
            "temp_c": self._temp(),
            "services": self._services(),
        }

    def _uptime(self):
        try:
            with open("/proc/uptime") as f:
                return int(float(f.read().split()[0]))
        except Exception:
            return 0

    def _cpu(self):
        def sample():
            with open("/proc/stat") as f:
                p = [int(x) for x in f.readline().split()[1:]]
            return sum(p), p[3] + p[4]                       # total, idle+iowait
        try:
            t1, i1 = sample(); time.sleep(0.12); t2, i2 = sample()
            dt = t2 - t1
            return round(100 * (1 - (i2 - i1) / dt)) if dt else 0
        except Exception:
            return 0

    def _mem(self):
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, _, v = line.partition(":")
                    info[k] = int(v.strip().split()[0])       # kB
            total = info["MemTotal"]
            avail = info.get("MemAvailable", info.get("MemFree", 0))
            return {"total_mb": total // 1024, "used_mb": (total - avail) // 1024,
                    "pct": round(100 * (total - avail) / total) if total else 0}
        except Exception:
            return {"total_mb": 0, "used_mb": 0, "pct": 0}

    def _disk(self):
        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            return {"total_gb": round(total / 1e9, 1), "used_gb": round((total - free) / 1e9, 1),
                    "pct": round(100 * (total - free) / total) if total else 0}
        except Exception:
            return {"total_gb": 0, "used_gb": 0, "pct": 0}

    def _temp(self):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return round(int(f.read().strip()) / 1000.0, 1)
        except Exception:
            return None

    def _services(self):
        out = []
        for s in self.services:
            unit = s if s.endswith(".service") else s + ".service"
            state = _run(["systemctl", "--user", "is-active", unit]).strip() \
                or _run(["systemctl", "is-active", unit]).strip() or "unknown"
            out.append({"name": s, "active": state == "active", "state": state})
        return out

    def reboot(self):
        if not self.dry:
            subprocess.Popen(["sudo", "-n", "systemctl", "reboot"])
        return not self.dry

    def shutdown(self):
        if not self.dry:
            subprocess.Popen(["sudo", "-n", "systemctl", "poweroff"])
        return not self.dry
