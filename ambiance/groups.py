"""Zone groups — control several zones as one.

This owns the group LIST (create / rename / re-member / delete) and its persistence:
groups.conf stays the single source of truth, rewritten atomically on every edit (same
tmp+rename+.bak pattern as the station list and zones.conf), so edits made in the web UI
survive restarts. The control fan-out (apply vol/mute/power to the member zones) lives in
the Controller; derived group state (avg vol / all-mute / all-power) in /api/status.
"""
from .config import _load_groups, save_groups


class Groups:
    def __init__(self, path, zone_count):
        self.path = path
        self._zone_count = zone_count          # callable -> number of zones (validates ids)
        self.entries = _load_groups(path)      # [{"name": str, "zones": [ids]}]

    @staticmethod
    def _clean(s):
        return str(s or "").replace("|", " ").replace("\n", " ").replace("\r", " ").strip()[:32]

    def _valid_zones(self, ids):
        n = self._zone_count()
        out = []
        for i in ids or []:
            try:
                i = int(i)
            except (TypeError, ValueError):
                continue
            if 0 <= i < n and i not in out:
                out.append(i)
        return out

    def get(self, name):
        return next((g for g in self.entries if g["name"] == name), None)

    # CRUD -> (ok, error) — messages are user-facing (Dutch), like the station CRUD
    def create(self, name, zones):
        name = self._clean(name)
        zs = self._valid_zones(zones)
        if not name:
            return False, "naam vereist"
        if self.get(name):
            return False, "naam bestaat al"
        if not zs:
            return False, "geen geldige zones"
        self.entries.append({"name": name, "zones": zs})
        save_groups(self.path, self.entries)
        return True, None

    def update(self, orig, name=None, zones=None):
        g = self.get(orig)
        if g is None:
            return False, "groep niet gevonden"
        if name is not None:
            name = self._clean(name)
            if not name:
                return False, "naam vereist"
            if name != g["name"] and self.get(name):
                return False, "naam bestaat al"
            g["name"] = name
        if zones is not None:
            zs = self._valid_zones(zones)
            if not zs:
                return False, "geen geldige zones"
            g["zones"] = zs
        save_groups(self.path, self.entries)
        return True, None

    def delete(self, name):
        g = self.get(name)
        if g is None:
            return False, "groep niet gevonden"
        self.entries.remove(g)
        save_groups(self.path, self.entries)
        return True, None
