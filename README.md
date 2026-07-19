# Ambiance AmpliPi

A small, single-purpose whole-house audio appliance for a Raspberry-Pi + [AmpliPi](https://github.com/micro-nova/AmpliPi) preamp: **internet radio**, **Spotify Connect**, **public-address announcements**, and a **burglar siren**, over up to six amplified zones. It is a heavily stripped fork of AmpliPi that keeps only the hardware layer (`amplipi.rt` → the 6-zone preamp over I²C) and replaces everything else with a tiny radio-first REST service.

It pairs with the [`ambianceamplipi` openHAB binding](https://github.com/stamateviorel/openhab-addons/tree/ambianceamplipi/bundles/org.openhab.binding.ambianceamplipi) but is fully usable stand-alone (REST API + a built-in web UI).

## Why

The full AmpliPi stack (FastAPI + a mutable `house.json` + streams + LMS + squeezelite) is heavy and its mutable state has wiped itself and killed all audio. Ambiance is declarative (no mutable house state), fails safe (mock hardware + dry audio unless explicitly enabled), and does three things well.

## What it keeps vs. drops

- **Keeps:** `amplipi/rt.py`, vendored + slimmed into a standalone `ambiance/hardware/preamp.py` (depends only on `smbus2` + `pyserial` + stdlib — no FastAPI/house.json closure); the verified ILI9341 front-panel init.
- **Drops:** `house.json` persistence, streams/presets/groups/source-mux, the web app, the updater, auth, zeroconf, mpris.

## Architecture

```
mpd (radio) ──────────────┐
go-librespot (spotify) ───┼─ ch0 / ch0boost @44.1k ─ dmix ─ HiFiBerry DAC ─ AmpliPi preamp ─ 6 zones
aplay (PA/siren) ─────────┘
       ▲
ambiance.service (FastAPI)  ── REST + SSE + web UI ──▶ openHAB ambianceamplipi binding
  radio.py (mpc)  ·  spotify.py (go-librespot API)  ·  streams.py (source arbitration)
  announce.py  ·  alarm.py (siren)  ·  hardware/zones.py (preamp)
  health.py (self-heal + report)  ·  cover.py (album art)
ambiance-display.service ── ILI9341 front screen (own process; a screen crash never touches audio)
```

## Playback sources (extensible)

Everything feeding the mix registers as a **source** (`ambiance/streams.py`): the radio and, when
`ambiance-spotify.service` runs, **Spotify Connect** via [go-librespot](https://github.com/devgianlu/go-librespot)
(a static Go binary — `scripts/install-spotify.sh`; the phone discovers "Ambiance AmpliPi" on the LAN,
Spotify Premium required). Exactly one source plays at a time: starting one makes the others yield —
including a phone starting Spotify remotely. Because every source plays into the same `ch0` softvol,
the announcement duck, the source volume and the siren's dominance apply to all of them automatically.
Adding another service later (AirPlay, Bluetooth, ...) = implement the 5-method adapter + register it;
the API, web UI and openHAB channel pick it up dynamically.

## Install

Requires Python 3.7+ with `fastapi`, `uvicorn`, `pydantic` **v1**, `smbus2`, `pyserial`, `sse-starlette`, `Pillow`, `adafruit-rgb-display`, `requests` (the AmpliPi venv already has these). Radio control uses the `mpc` CLI.

```bash
# from a checkout on the Pi
cp -r ambiance config assets systemd scripts /home/pi/ambiance-amplipi/
systemctl --user enable --now ambiance-mpd ambiance ambiance-display
# optional — Spotify Connect (fetches the go-librespot binary):
scripts/install-spotify.sh && systemctl --user enable --now ambiance-spotify
```

## Configuration (declarative, env-driven — no mutable house state)

| Variable | Default | Description |
|---|---|---|
| `AMBIANCE_DIR` | `/home/pi/ambiance-amplipi` | install root (config/assets paths derive from it) |
| `AMBIANCE_HW` | `mock` | `mock` or `rpi` (`rpi` resets the preamps on start) |
| `AMBIANCE_DRY` | `1` | `1` = no audio side effects (fail-safe); `0` = live |
| `AMBIANCE_PORT` | `8080` | HTTP port |
| `AMBIANCE_VOL_CTL` | `Ch0` | the source softvol amixer control (master volume; ducked for announcements) |
| `AMBIANCE_ANNOUNCE_DEV` | `ch0boost` | ALSA device announcements + the siren play on |
| `AMBIANCE_DUCK_PCT` | `45` | source level (%) while an announcement plays |
| `AMBIANCE_ANNOUNCE_VOL` | _(unset)_ | default announcement loudness (boost %, 0–100) for messages without their own `vol`; unset = leave the boost level untouched. Runtime-settable + persisted to `settings.conf` |
| `AMBIANCE_MPD_HOST` / `AMBIANCE_MPD_PORT` | `127.0.0.1` / `6600` | where mpd listens |
| `AMBIANCE_HEALTH_INTERVAL` | `15` | health sweep / self-heal interval (s) |
| `AMBIANCE_ZONES` / `AMBIANCE_STATIONS` / `AMBIANCE_GROUPS` | `config/*.conf` | zones (`id\|name\|default_pct`; renameable from the web UI), stations (`name\|url\|logo?`, first = default), groups (`Name\|ids`) |
| `AMBIANCE_ALARM` | `assets/alarm.wav` | the siren WAV |
| `AMBIANCE_SPOTIFY` | `1` | register the Spotify Connect source (inert if the daemon is absent); `0` hides it |
| `AMBIANCE_SPOTIFY_API` | `http://127.0.0.1:3678` | go-librespot local API |

## REST API

`GET /` — web UI · `GET /api/status` · `GET /api/events` (SSE) · `POST /api/radio` `{station}` / `/api/radio/{play,stop,next,prev}` · `POST /api/source` `{name}` / `/api/source/{play,stop,next,prev}` (source-aware transport) · `GET/POST /api/stations`, `PATCH/DELETE /api/stations/{name}`, `POST /api/stations/{name}/default` · `PATCH /api/zones/{id}` `{vol,mute,power,name}` (rename persists to zones.conf) · `PATCH /api/zones` (master) · group CRUD: `POST /api/groups` `{name,zones}`, `PATCH /api/groups/{name}` `{vol,mute,power,new_name?,zones?}`, `DELETE /api/groups/{name}` (edits persist to groups.conf) · announcements (a bounded FIFO the box drains one at a time): `POST /api/announce` `{url,vol?}` (enqueue; `503` when full), `PATCH /api/announce` `{vol}` (set/clear the persisted default loudness), `DELETE /api/announce` (flush what's still queued) — the queue depth + default vol appear in `/api/status`'s `announce` object · `POST /api/alarm` `{on}` · `GET /api/alarm/selftest` · `GET /api/cover`.

## Reliability

The preamp layer self-heals a wedged I²C bus in place (reset + re-flush, rate-limited); `health.py` self-heals a *dropped* radio stream (only one it meant to be playing) and reports `mpd` + preamp status in `/api/status.health` so openHAB can alert. The display process re-inits a wedged SPI panel. All units are `Restart=always`.

## Credits & license

Derived from [micro-nova/AmpliPi](https://github.com/micro-nova/AmpliPi) (GPL-3.0). The vendored `ambiance/hardware/preamp.py` is a slimmed derivative of AmpliPi's `amplipi/rt.py`. This project is licensed **GPL-3.0-or-later** accordingly.
