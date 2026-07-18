"""Playback-source registry + arbitration for everything feeding the ch0 mix.

All playback sources (radio, Spotify Connect, later AirPlay / Bluetooth / ...) share ONE
audio path (the `ch0` softvol -> dmix), so exactly one may play at a time. Each source
registers a small adapter with five methods:

    playing() -> bool     is it audibly playing right now
    pause()               silence it (radio: stop; spotify: pause)
    resume()              start/resume it
    next() / prev()       transport (radio: cycle stations)
    can_resume() -> bool  is there anything to resume (spotify: a live session)

`claim(name)` pauses every OTHER source and marks `name` active — call it whenever a
source starts (a user pressed play here, or a phone started a remote session). Everything
downstream (the /api/source endpoints, /api/status.source, the web UI chips, the openHAB
`source` channel) is driven by `available`, so ADDING A SERVICE = implement the adapter +
register it in the Controller. No other layer changes.
"""


class Sources:
    def __init__(self):
        self._srcs = {}          # name -> adapter (insertion-ordered)
        self.active = None       # name of the source that owns the audio path

    def register(self, name, adapter):
        self._srcs[name] = adapter
        if self.active is None:
            self.active = name

    @property
    def available(self):
        return list(self._srcs)

    def get(self, name=None):
        return self._srcs.get(name or self.active)

    def claim(self, name):
        """`name` starts playing: pause everyone else, make it the active source."""
        if name not in self._srcs:
            return False
        for n, s in self._srcs.items():
            if n != name:
                try:
                    s.pause()
                except Exception:
                    pass
        self.active = name
        return True

    def pause_all(self):
        """Silence every source (siren / sleep timer / away-mode)."""
        for s in self._srcs.values():
            try:
                s.pause()
            except Exception:
                pass

    def state(self):
        return {"active": self.active, "available": self.available}


class RadioAdapter:
    """Source adapter over Radio (mpd): pause == stop for a live stream."""

    def __init__(self, radio):
        self.radio = radio

    def playing(self):
        # intent-level (`desired_playing`), NOT a live mpc probe: instant — the alarm's
        # remember-what-played must never block on a possibly-hung mpd, and "meant to be
        # playing" is the right semantic for resume-after-siren anyway.
        return self.radio.desired_playing

    def pause(self):
        self.radio.stop()

    def resume(self):
        self.radio.play()

    def next(self):
        self.radio.cycle(1)

    def prev(self):
        self.radio.cycle(-1)

    def can_resume(self):
        return True
