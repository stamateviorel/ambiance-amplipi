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


class Status(BaseModel):
    zones: List[Zone]
    radio: RadioState
    master_vol: int
    master_mute: bool
    siren: bool


class Station(BaseModel):
    name: str
    url: str


class Stations(BaseModel):
    stations: List[Station]


class ZoneUpdate(BaseModel):
    vol: Optional[int] = None
    mute: Optional[bool] = None
    power: Optional[bool] = None


class MasterUpdate(BaseModel):
    vol: Optional[int] = None
    mute: Optional[bool] = None


class StationSelect(BaseModel):
    station: str


class StationEdit(BaseModel):
    orig: Optional[str] = None
    name: str
    url: str


class Announcement(BaseModel):
    url: str
    vol: Optional[int] = None


class AlarmState(BaseModel):
    on: bool


class ApiResult(BaseModel):
    ok: bool
    error: Optional[str] = None
