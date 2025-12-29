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

# Boat Class Schemas
class BoatClassBase(BaseModel):
    name: str
    portsmouth_yardstick: Optional[float] = None
    typical_upwind_angle_light: Optional[float] = None
    typical_upwind_angle_medium: Optional[float] = None
    typical_upwind_angle_fresh: Optional[float] = None
    typical_upwind_angle_strong: Optional[float] = None
    typical_downwind_angle_light: Optional[float] = None
    typical_downwind_angle_medium: Optional[float] = None
    typical_downwind_angle_fresh: Optional[float] = None
    typical_downwind_angle_strong: Optional[float] = None
    typical_upwind_vmg_light: Optional[float] = None
    typical_upwind_vmg_medium: Optional[float] = None
    typical_upwind_vmg_fresh: Optional[float] = None
    typical_upwind_vmg_strong: Optional[float] = None
    typical_downwind_vmg_light: Optional[float] = None
    typical_downwind_vmg_medium: Optional[float] = None
    typical_downwind_vmg_fresh: Optional[float] = None
    typical_downwind_vmg_strong: Optional[float] = None
    waterline_length_m: Optional[float] = None
    hull_speed_max_kn: Optional[float] = None
    description: Optional[str] = None

class BoatClassCreate(BoatClassBase):
    pass

class BoatClassOut(BoatClassBase):
    id: int
    is_custom: bool
    created_at: datetime

    class Config:
        from_attributes = True

# Boat Schemas
class BoatCreate(BaseModel):
    name: Optional[str] = None
    klass: Optional[str] = None  # Legacy field
    sail_number: str
    boat_class_id: Optional[int] = None
    is_default: Optional[bool] = False

class BoatUpdate(BaseModel):
    name: Optional[str] = None
    sail_number: Optional[str] = None
    boat_class_id: Optional[int] = None
    is_default: Optional[bool] = None

class BoatOut(BaseModel):
    id: int
    user_id: int
    name: Optional[str]
    klass: Optional[str]
    sail_number: str
    boat_class_id: Optional[int]
    is_default: bool
    created_at: datetime
    boat_class: Optional[BoatClassOut] = None

    class Config:
        from_attributes = True
