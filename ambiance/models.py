"""Pydantic models for the ambiance REST API (and the /openapi.json the openHAB binding
generates its DTOs from). Pydantic v1 — the Pi runs Python 3.7, which cannot run v2.
"""
from typing import List, Optional

from pydantic import BaseModel


class Zone(BaseModel):
    id: int
    name: str
    vol: int          # 0..100
    mute: bool        # user mute
    power: bool       # zone power (music-follows-you)


class RadioState(BaseModel):
    playing: bool
    station: Optional[str] = None
    title: str = ""
    artist: str = ""
    track: str = ""
    stations: List[str] = []


class Health(BaseModel):
    ok: bool = True
    issues: List[str] = []        # human-readable (Dutch), for the notification body
    mpd: str = "ok"               # ok | <reason>
    preamp: str = "ok"            # ok | wedged
    recoveries: int = 0           # count of successful in-place self-heals (informational)
    checked: int = 0              # unix ts of the last health sweep


class Group(BaseModel):
    name: str
    zones: List[int]      # zone ids
    vol: int              # average of the group's zone volumes
    mute: bool            # all zones muted
    power: bool           # all zones powered


class SleepState(BaseModel):
    active: bool = False
    remaining_s: int = 0


class SpotifyState(BaseModel):
    running: bool = False     # go-librespot daemon reachable
    playing: bool = False
    track: str = ""
    artist: str = ""
    album: str = ""
    cover: str = ""           # album art URL (fetched+served via /api/cover)


class SourceState(BaseModel):
    active: str = "radio"             # which source owns the audio path
    available: List[str] = ["radio"]  # registered sources (extensible)


class Status(BaseModel):
    zones: List[Zone]
    radio: RadioState
    master_vol: int
    master_mute: bool
    siren: bool
    health: Health = Health()
    groups: List[Group] = []
    sleep: SleepState = SleepState()
    source: SourceState = SourceState()
    spotify: SpotifyState = SpotifyState()


class Station(BaseModel):
    name: str
    url: str
    logo: Optional[str] = None


class Stations(BaseModel):
    stations: List[Station]


class ZoneUpdate(BaseModel):
    vol: Optional[int] = None
    mute: Optional[bool] = None
    power: Optional[bool] = None


class MasterUpdate(BaseModel):
    vol: Optional[int] = None
    mute: Optional[bool] = None


class GroupUpdate(BaseModel):
    vol: Optional[int] = None
    mute: Optional[bool] = None
    power: Optional[bool] = None


class SleepUpdate(BaseModel):
    minutes: int = 0   # 0 cancels the sleep timer


class StationSelect(BaseModel):
    station: str


class SourceSelect(BaseModel):
    name: str      # one of Status.source.available


class StationEdit(BaseModel):
    orig: Optional[str] = None
    name: str
    url: str
    logo: Optional[str] = None


class Announcement(BaseModel):
    url: str
    vol: Optional[int] = None


class AlarmState(BaseModel):
    on: bool


class ApiResult(BaseModel):
    ok: bool
    error: Optional[str] = None
