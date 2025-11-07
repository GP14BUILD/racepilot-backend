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

def init_db():
    Base.metadata.create_all(bind=engine)
