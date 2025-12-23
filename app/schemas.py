from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str

class SessionCreate(BaseModel):
    boat_id: Optional[int] = None
    title: str
    start_ts: datetime

class TrackPointIn(BaseModel):
    ts: datetime
    lat: float
    lon: float
    sog: float
    cog: float
    awa: float
    aws: float
    hdg: float
    tws: float | None = None
    twa: float | None = None

class TelemetryIngest(BaseModel):
    session_id: int
    points: List[TrackPointIn]

class StartLine(BaseModel):
    pin_lat: float
    pin_lon: float
    com_lat: float
    com_lon: float
    twd: float  # true wind direction (deg)

class TTLRequest(BaseModel):
    sog: float
    distance_m: float

class AnalyticsRequest(BaseModel):
    session_id: int
    mark_lat: float
    mark_lon: float
    twd: float
    tws: float
    polar_id: int
