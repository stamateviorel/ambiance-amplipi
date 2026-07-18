"""ambiance-amplipi — FastAPI app: radio + announcements + alarm over 6 zones.

Radio-first REST API consumed by the openHAB `ambianceamplipi` binding (+ SSE for push).
The controller wires the hardware (zones), radio (mpd), announcer, siren and cover. The
siren orchestrates pause-radio + all-zones-full + alarm-loop and overrides announcements.

Endpoints are sync `def` so FastAPI runs the blocking mpc/aplay/amixer work in its
threadpool (never blocking the event loop). Pydantic v1 (Python 3.7 on the Pi).
"""
import asyncio
import json
import os
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sse_starlette.sse import EventSourceResponse

from . import models
from .announce import Announcer
from .alarm import Siren
from .config import Config
from .cover import Cover
from .health import HealthMonitor
from .radio import Radio
from .sleep import Sleep
from .source import Source
from .spotify import Spotify
from .streams import RadioAdapter, Sources
from .system import System
from .hardware.zones import Zones


class Controller:
    def __init__(self, cfg):
        self.cfg = cfg
        self.zones = Zones(cfg.zones, hw=cfg.hw)
        self.radio = Radio(cfg.stations_file, cfg.mpd_host, cfg.mpd_port,
                           is_blocked=lambda: self.siren.active)      # no radio over the alarm
        self.boost = Source(ctl="Ch0 Boost", dry=cfg.dry)            # ch0boost softvol, forced full during the alarm
        self.siren = Siren(cfg.alarm_wav, dev=cfg.announce_dev, dry=cfg.dry,
                           on_loop=self._siren_reassert)             # re-assert full each wav loop
        self.announcer = Announcer(dev=cfg.announce_dev, vol_ctl=cfg.vol_ctl,
                                   duck_pct=cfg.duck_pct, dry=cfg.dry,
                                   is_busy=lambda: self.siren.active,
                                   boost=self.boost)   # per-announcement volume on the boost channel
        self.cover = Cover()
        self.source = Source(ctl=cfg.vol_ctl, dry=cfg.dry)   # source (Ch0) volume, independent of zones
        # ---- playback sources (extensible: register an adapter -> it appears everywhere) ----
        self.spotify = Spotify(api=getattr(cfg, "spotify_api", "http://127.0.0.1:3678"),
                               on_playing=lambda: self.sources.claim("spotify"))  # phone pressed play
        self.sources = Sources()
        self.sources.register("radio", RadioAdapter(self.radio))
        if getattr(cfg, "spotify", True):
            self.sources.register("spotify", self.spotify)
        self._resume_source = None   # source playing when the siren fired (resume, not start)
        services = ["ambiance", "ambiance-mpd", "ambiance-display"]
        if getattr(cfg, "spotify", True):
            services.append("ambiance-spotify")
        self.system = System(services=services, dry=cfg.dry)  # stats + power for the settings page
        self.groups = getattr(cfg, "groups", [])
        self.sleep = Sleep(on_fire=lambda: self.sources.pause_all())  # silence whatever plays
        self.monitor = HealthMonitor(self, getattr(cfg, "health_interval", 15))

    def status(self):
        return {
            "zones": self.zones.snapshot(),
            "radio": self.radio.state(),
            "master_vol": self.source.vol(),        # source level (Ch0), NOT an average of zones
            "master_mute": self.zones.master_mute(),
            "siren": self.siren.active,
            "health": self.monitor.state,
            "groups": self._group_states(),
            "sleep": self.sleep.state(),
            "source": self.sources.state(),
            "spotify": self.spotify.state(),
        }

    def _group_states(self):
        snap = {z["id"]: z for z in self.zones.snapshot()}
        out = []
        for g in self.groups:
            zs = [snap[i] for i in g["zones"] if i in snap]
            if not zs:
                continue
            out.append({"name": g["name"], "zones": [z["id"] for z in zs],
                        "vol": round(sum(z["vol"] for z in zs) / len(zs)),
                        "mute": all(z["mute"] for z in zs),
                        "power": all(z["power"] for z in zs)})
        return out

    def apply_group(self, name, vol=None, mute=None, power=None):
        g = next((g for g in self.groups if g["name"] == name), None)
        if not g:
            return False
        for i in g["zones"]:
            if 0 <= i < self.zones.n:
                if vol is not None:
                    self.zones.set_vol(i, vol)
                if mute is not None:
                    self.zones.set_mute(i, mute)
                if power is not None:
                    self.zones.set_power(i, power)
        return True

    def _siren_reassert(self):
        # watchdog belt (called each wav loop): keep every zone full/unmuted, the boost
        # channel at 100%, and every music source silent (a phone pressing play mid-alarm
        # must not mix Spotify over the siren) no matter what else tried mid-alarm.
        # The source pausing is ASYNC: a hung mpd/daemon (mpc timeout 8s) must never
        # stretch the gap between siren wav loops.
        self.zones.reassert_siren()
        self.boost.set_vol(100)
        threading.Thread(target=self.sources.pause_all, daemon=True).start()

    # ---- source arbitration (used by the /api/source endpoints + power/away semantics) ----
    @staticmethod
    def _adapter_playing(adapter):
        try:
            return bool(adapter.playing())
        except Exception:
            return False

    def select_source(self, name):
        """Switch to + start `name`. Refused for unknown names; ignored during the siren."""
        if name not in self.sources.available:
            return False
        if self.siren.active:
            return True                    # nothing may play over the alarm
        self.sources.claim(name)           # pauses the others
        try:
            self.sources.get(name).resume()
        except Exception:
            pass
        return True

    def play_active(self):
        """Resume the active source; a dead remote session falls back to the radio."""
        if self.siren.active:
            return
        name = self.sources.active
        src = self.sources.get(name)
        if src is None or (name != "radio" and not src.can_resume()):
            name = "radio"
        self.select_source(name)

    def transport(self, delta):
        src = self.sources.get()
        if src is None or self.siren.active:
            return
        try:
            src.next() if delta > 0 else src.prev()
        except Exception:
            pass

    def alarm(self, on):
        # safety-critical: independent of mpd — fires even if the radio player is dead
        if on:
            if not self.siren.active:    # a retried ON must not clobber the remembered state
                act = self.sources.get()
                self._resume_source = self.sources.active \
                    if (act is not None and self._adapter_playing(act)) else None
            # SIREN FIRST — never gate the alarm on pausing players (a hung mpd/daemon
            # could block for seconds); silencing follows async + per-loop belt.
            self.boost.set_vol(100)      # alarm channel full up-front
            self.zones.siren(True)       # lock all zones full/unmuted/on (commands can't quiet it)
            self.siren.on()              # loop alarm.wav on ch0boost (re-asserts each loop)
            threading.Thread(target=self.sources.pause_all, daemon=True).start()
        else:
            self.siren.off()
            self.zones.siren(False)      # unlock + restore the logical zone state
            if self._resume_source:      # RESUME what was playing pre-alarm (never start fresh)
                name, self._resume_source = self._resume_source, None
                self.select_source(name)


cfg = Config()
ctl = Controller(cfg)
app = FastAPI(title="ambiance-amplipi", version="0.1.0")

_WEB_DIR = os.path.join(os.path.dirname(__file__), "web")


# ---- web UI (a self-contained control page over the same API) ----
@app.get("/", response_class=HTMLResponse)
def index():
    try:
        with open(os.path.join(_WEB_DIR, "index.html"), encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except OSError:
        return HTMLResponse("<h1>Ambiance AmpliPi</h1><p>Web UI niet gevonden.</p>")


# ---- status + events ----
@app.get("/api/status", response_model=models.Status)
def get_status():
    return ctl.status()


@app.get("/api/events")
async def events(request: Request):
    async def gen():
        last = None
        loop = asyncio.get_event_loop()
        while not await request.is_disconnected():
            st = await loop.run_in_executor(None, ctl.status)
            cur = json.dumps(st, sort_keys=True)
            if cur != last:
                last = cur
                yield {"event": "status", "data": cur}
            await asyncio.sleep(1)
    return EventSourceResponse(gen())


# ---- radio + stations (explicitly playing the radio claims the audio path) ----
@app.post("/api/radio", response_model=models.Status)
def radio_play(sel: models.StationSelect):
    ctl.sources.claim("radio")             # spotify (or any other source) yields
    ctl.radio.play_station(sel.station)
    return ctl.status()


@app.post("/api/radio/play", response_model=models.Status)
def radio_resume():
    ctl.sources.claim("radio")
    ctl.radio.play()
    return ctl.status()


@app.post("/api/radio/stop", response_model=models.Status)
def radio_stop():
    ctl.radio.stop()
    return ctl.status()


@app.post("/api/radio/next", response_model=models.Status)
def radio_next():
    ctl.sources.claim("radio")
    ctl.radio.cycle(1)
    return ctl.status()


@app.post("/api/radio/prev", response_model=models.Status)
def radio_prev():
    ctl.sources.claim("radio")
    ctl.radio.cycle(-1)
    return ctl.status()


# ---- sources (source-aware transport: works for radio, spotify, and future services) ----
@app.post("/api/source", response_model=models.Status)
def source_select(s: models.SourceSelect):
    if not ctl.select_source(s.name):
        raise HTTPException(status_code=404, detail="bron onbekend")
    return ctl.status()


@app.post("/api/source/play", response_model=models.Status)
def source_play():
    ctl.play_active()
    return ctl.status()


@app.post("/api/source/stop", response_model=models.Status)
def source_stop():
    ctl.sources.pause_all()
    return ctl.status()


@app.post("/api/source/next", response_model=models.Status)
def source_next():
    ctl.transport(1)
    return ctl.status()


@app.post("/api/source/prev", response_model=models.Status)
def source_prev():
    ctl.transport(-1)
    return ctl.status()


@app.get("/api/stations", response_model=models.Stations)
def get_stations():
    return {"stations": ctl.radio.stations}


@app.post("/api/stations", response_model=models.ApiResult)
def add_station(s: models.StationEdit):
    ok, err = ctl.radio.add_station(s.name, s.url, s.logo)
    return {"ok": ok, "error": err}


@app.patch("/api/stations", response_model=models.ApiResult)
def edit_station(s: models.StationEdit):
    ok, err = ctl.radio.update_station(s.orig, s.name, s.url, s.logo)
    return {"ok": ok, "error": err}


@app.delete("/api/stations/{name}", response_model=models.ApiResult)
def delete_station(name: str):
    ok, err = ctl.radio.delete_station(name)
    return {"ok": ok, "error": err}


@app.post("/api/stations/{name}/default", response_model=models.ApiResult)
def default_station(name: str):
    ok, err = ctl.radio.set_default(name)
    return {"ok": ok, "error": err}


# ---- zones ----
@app.patch("/api/zones/{zid}", response_model=models.Status)
def zone_update(zid: int, u: models.ZoneUpdate):
    if not 0 <= zid < ctl.zones.n:      # explicit 404 (a negative id would wrap in Python)
        raise HTTPException(status_code=404, detail="zone bestaat niet")
    if u.vol is not None:
        ctl.zones.set_vol(zid, u.vol)
    if u.mute is not None:
        ctl.zones.set_mute(zid, u.mute)
    if u.power is not None:
        ctl.zones.set_power(zid, u.power)
    return ctl.status()


@app.patch("/api/zones", response_model=models.Status)
def zones_master(u: models.MasterUpdate):
    if u.vol is not None:
        ctl.source.set_vol(u.vol)          # master = the source (Ch0) level; zones keep their own volumes
    if u.mute is not None:
        ctl.zones.set_master_mute(u.mute)
    return ctl.status()


@app.patch("/api/groups/{name}", response_model=models.Status)
def group_update(name: str, u: models.GroupUpdate):
    ctl.apply_group(name, u.vol, u.mute, u.power)
    return ctl.status()


@app.post("/api/sleep", response_model=models.Status)
def sleep_set(s: models.SleepUpdate):
    ctl.sleep.set(s.minutes)   # 0 cancels
    return ctl.status()


# ---- announce + alarm + cover ----
@app.post("/api/announce", response_model=models.ApiResult)
def announce(a: models.Announcement):
    ok = ctl.announcer.say(a.url, a.vol)   # optional per-announcement volume (boost channel)
    return {"ok": ok, "error": None if ok else "queue full"}


@app.post("/api/alarm", response_model=models.Status)
def alarm(a: models.AlarmState):
    ctl.alarm(a.on)
    return ctl.status()


@app.get("/api/alarm/selftest")
def alarm_selftest():
    return ctl.siren.selftest()


@app.get("/api/cover")
def cover():
    # Spotify active -> serve its album art (same normalise+cache path as station logos)
    sp = ctl.spotify.state()
    if ctl.sources.active == "spotify" and sp["playing"]:
        data = ctl.cover.bytes_for("", sp["cover"] or None, sp["track"] or "Spotify")
        if data:
            return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
        return Response(status_code=204)
    r = ctl.radio
    if not r.is_playing():
        return Response(status_code=204)   # nothing playing -> no cover (widget shows its placeholder)
    np = r.now_playing()
    # while playing there is ALWAYS a cover: song art -> station logo -> a tile (station name).
    # Search only on REAL "Artist + Song" metadata (a lone show/song name gives noisy art hits).
    term = ("%s %s" % (np["artist"], np["title"])).strip() if (np["artist"] and np["title"]) else ""
    tile = r.current_station() or np["track"] or "Radio"
    data = ctl.cover.bytes_for(term, r.current_station_logo(), tile)
    if data:
        return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
    return Response(status_code=204)


# ---- system (settings page): stats + power ----
@app.get("/api/system")
def system_stats():
    return ctl.system.stats()


@app.post("/api/system/reboot", response_model=models.ApiResult)
def system_reboot():
    ok = ctl.system.reboot()
    return {"ok": ok, "error": None if ok else "dry-run: no live hardware"}


@app.post("/api/system/shutdown", response_model=models.ApiResult)
def system_shutdown():
    ok = ctl.system.shutdown()
    return {"ok": ok, "error": None if ok else "dry-run: no live hardware"}


@app.on_event("startup")
def _startup():
    ctl.monitor.start()   # background health sweeps + dropped-stream self-heal
    if "spotify" in ctl.sources.available:
        ctl.spotify.start()   # poll go-librespot: state cache + phone-started-playback events
    # boot-to-radio: after mpd is up, if nothing is queued, play the default station
    def boot():
        time.sleep(4)
        try:
            ctl.radio.ensure_default()
        except Exception:
            pass
    threading.Thread(target=boot, daemon=True).start()
