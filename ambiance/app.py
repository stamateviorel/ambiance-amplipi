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

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from sse_starlette.sse import EventSourceResponse

from . import models
from .announce import Announcer
from .alarm import Siren
from .config import Config
from .cover import Cover
from .health import HealthMonitor
from .radio import Radio
from .hardware.zones import Zones


class Controller:
    def __init__(self, cfg):
        self.cfg = cfg
        self.zones = Zones(cfg.zones, hw=cfg.hw)
        self.radio = Radio(cfg.stations_file, cfg.mpd_host, cfg.mpd_port)
        self.siren = Siren(cfg.alarm_wav, dev=cfg.announce_dev, dry=cfg.dry)
        self.announcer = Announcer(dev=cfg.announce_dev, vol_ctl=cfg.vol_ctl,
                                   duck_pct=cfg.duck_pct, dry=cfg.dry,
                                   is_busy=lambda: self.siren.active)
        self.cover = Cover()
        self.monitor = HealthMonitor(self, getattr(cfg, "health_interval", 15))

    def status(self):
        return {
            "zones": self.zones.snapshot(),
            "radio": self.radio.state(),
            "master_vol": self.zones.master_vol(),
            "master_mute": self.zones.master_mute(),
            "siren": self.siren.active,
            "health": self.monitor.state,
        }

    def alarm(self, on):
        # safety-critical: independent of mpd — fires even if the radio player is dead
        if on:
            self.radio.stop()
            self.zones.siren(True)
            self.siren.on()
        else:
            self.siren.off()
            self.zones.siren(False)
            self.radio.play()


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


# ---- radio + stations ----
@app.post("/api/radio", response_model=models.Status)
def radio_play(sel: models.StationSelect):
    ctl.radio.play_station(sel.station)
    return ctl.status()


@app.post("/api/radio/play", response_model=models.Status)
def radio_resume():
    ctl.radio.play()
    return ctl.status()


@app.post("/api/radio/stop", response_model=models.Status)
def radio_stop():
    ctl.radio.stop()
    return ctl.status()


@app.post("/api/radio/next", response_model=models.Status)
def radio_next():
    ctl.radio.cycle(1)
    return ctl.status()


@app.post("/api/radio/prev", response_model=models.Status)
def radio_prev():
    ctl.radio.cycle(-1)
    return ctl.status()


@app.get("/api/stations", response_model=models.Stations)
def get_stations():
    return {"stations": ctl.radio.stations}


@app.post("/api/stations", response_model=models.ApiResult)
def add_station(s: models.StationEdit):
    ok, err = ctl.radio.add_station(s.name, s.url)
    return {"ok": ok, "error": err}


@app.patch("/api/stations", response_model=models.ApiResult)
def edit_station(s: models.StationEdit):
    ok, err = ctl.radio.update_station(s.orig, s.name, s.url)
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
        ctl.zones.set_master_vol(u.vol)
    if u.mute is not None:
        ctl.zones.set_master_mute(u.mute)
    return ctl.status()


# ---- announce + alarm + cover ----
@app.post("/api/announce", response_model=models.ApiResult)
def announce(a: models.Announcement):
    ok = ctl.announcer.say(a.url)
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
    data = ctl.cover.bytes_for(ctl.radio.now_playing()["title"])
    if data:
        return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
    return Response(status_code=204)


@app.on_event("startup")
def _startup():
    ctl.monitor.start()   # background health sweeps + dropped-stream self-heal
    # boot-to-radio: after mpd is up, if nothing is queued, play the default station
    def boot():
        time.sleep(4)
        try:
            ctl.radio.ensure_default()
        except Exception:
            pass
    threading.Thread(target=boot, daemon=True).start()
