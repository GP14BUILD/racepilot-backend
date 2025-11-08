from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./racepilot.db")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    password_hash = Column(String)

class Boat(Base):
    __tablename__ = "boats"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    klass = Column(String)
    sail_number = Column(String)

class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    boat_id = Column(Integer, ForeignKey("boats.id"))
    title = Column(String)
    start_ts = Column(DateTime)
    end_ts = Column(DateTime, nullable=True)

class TrackPoint(Base):
    __tablename__ = "trackpoints"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True)
    ts = Column(DateTime, index=True)
    lat = Column(Float)
    lon = Column(Float)
    sog = Column(Float)  # speed over ground (kn)
    cog = Column(Float)  # course over ground (deg)
    awa = Column(Float)  # apparent wind angle (deg)
    aws = Column(Float)  # apparent wind speed (kn)
    hdg = Column(Float)  # compass heading (deg)
    tws = Column(Float, nullable=True)  # true wind speed (kn)
    twa = Column(Float, nullable=True)  # true wind angle (deg)

class Polar(Base):
    __tablename__ = "polars"
    id = Column(Integer, primary_key=True)
    boat_id = Column(Integer, ForeignKey("boats.id"))
    data_json = Column(JSON)  # {'tws_kn': [...], 'twa_deg': [...], 'target_kn': [[...]]}

class RaceCourse(Base):
    __tablename__ = "race_courses"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime)
    config_json = Column(JSON)  # {'type': 'windward_leeward', 'laps': 3, etc.}

class RaceMark(Base):
    __tablename__ = "race_marks"
    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("race_courses.id"), index=True)
    name = Column(String)  # e.g., "Start Pin", "Windward Mark", "Leeward Gate Left"
    lat = Column(Float)
    lon = Column(Float)
    mark_type = Column(String)  # 'start', 'windward', 'leeward', 'offset', 'gate', 'finish'
    color = Column(String, default='#FF6B6B')  # Hex color for map display
    sequence = Column(Integer)  # Order in course
    shape = Column(String, default='circle')  # 'circle', 'triangle', 'square', 'pin'

class WeatherData(Base):
    __tablename__ = "weather_data"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True, nullable=True)
    ts = Column(DateTime, index=True)
    lat = Column(Float)
    lon = Column(Float)
    wind_speed = Column(Float)  # knots
    wind_direction = Column(Float)  # degrees true
    wind_gust = Column(Float, nullable=True)
    wave_height = Column(Float, nullable=True)  # meters
    current_speed = Column(Float, nullable=True)  # knots
    current_direction = Column(Float, nullable=True)  # degrees

class TacticalEvent(Base):
    __tablename__ = "tactical_events"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True)
    ts = Column(DateTime)
    lat = Column(Float)
    lon = Column(Float)
    event_type = Column(String)  # 'tack', 'gybe', 'mark_rounding', 'start', 'finish'
    metadata_json = Column(JSON, nullable=True)  # Additional event data

class StartLine(Base):
    __tablename__ = "start_lines"
    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("race_courses.id"))
    pin_lat = Column(Float)
    pin_lon = Column(Float)
    boat_lat = Column(Float)
    boat_lon = Column(Float)
    line_heading = Column(Float)  # degrees
    favored_end = Column(String, nullable=True)  # 'pin' or 'boat'
    bias_degrees = Column(Float, nullable=True)  # positive = pin favored

def init_db():
    Base.metadata.create_all(bind=engine)
