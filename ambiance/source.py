"""ambiance-amplipi — the radio source's own volume.

Two-tier volume model: the radio *source* has one level (this class) and each *zone* has its
own independent level (hardware/zones.py, the preamp). The source is the mpd radio mixed on
ALSA `Ch0` (a softvol), ahead of the per-zone preamp attenuation — so turning the source down
quiets the whole house proportionally while each zone keeps its relative balance. mpd has no
mixer of its own (`mixer_type "none"`), so `Ch0` is the source gain stage.

`Ch0` is also what the announcer ducks (read-then-restore, so it works with any source level),
and the siren plays on `ch0boost` — so the source volume never weakens an announcement or the
safety siren.
"""
import re
import subprocess


class Source:
    def __init__(self, ctl="Ch0", card="0", dry=False):
        self.ctl = ctl
        self.card = str(card)
        self.dry = dry
        self._last = 100          # cache + the value returned in dry/mock mode

    def vol(self):
        if not self.dry:
            try:
                out = subprocess.check_output(
                    ["amixer", "-c", self.card, "sget", self.ctl],
                    stderr=subprocess.DEVNULL).decode()
                m = re.search(r"\[(\d+)%\]", out)
                if m:
                    self._last = int(m.group(1))
            except Exception:
                pass
        return self._last

    def set_vol(self, pct):
        self._last = max(0, min(100, int(pct)))
        if self.dry:
            return
        try:
            subprocess.call(
                ["amixer", "-c", self.card, "sset", self.ctl, "%d%%" % self._last],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
