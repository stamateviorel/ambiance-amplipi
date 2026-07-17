"""Sleep timer: stop the radio after N minutes. Set/cancel/re-set at any time; the current
remaining time is reported in /api/status so the binding, web UI and front screen can show it.
"""
import threading
import time


class Sleep:
    def __init__(self, on_fire):
        self._on_fire = on_fire          # called (no args) when the timer elapses
        self._timer = None
        self._ends_at = None
        self._lock = threading.Lock()

    def _cancel_locked(self):
        if self._timer is not None:
            self._timer.cancel()
        self._timer = None
        self._ends_at = None

    def set(self, minutes):
        """Arm the timer for `minutes` (a falsy / <=0 value cancels it)."""
        with self._lock:
            self._cancel_locked()
            try:
                minutes = int(minutes or 0)
            except (TypeError, ValueError):
                minutes = 0
            if minutes > 0:
                self._ends_at = time.time() + minutes * 60
                self._timer = threading.Timer(minutes * 60, self._fire)
                self._timer.daemon = True
                self._timer.start()

    def cancel(self):
        with self._lock:
            self._cancel_locked()

    def _fire(self):
        with self._lock:
            self._timer = None
            self._ends_at = None
        try:
            self._on_fire()
        except Exception:
            pass

    def state(self):
        ends = self._ends_at
        if not ends:
            return {"active": False, "remaining_s": 0}
        return {"active": True, "remaining_s": max(0, int(ends - time.time()))}
