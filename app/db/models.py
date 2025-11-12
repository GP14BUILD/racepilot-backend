from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import os
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./racepilot.db")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Club(Base):
    __tablename__ = "clubs"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=False, index=True)  # e.g., "BRYC"
    subscription_tier = Column(String, default='free')  # 'free', 'basic', 'pro'
    created_at = Column(DateTime, default=datetime.utcnow)
    settings = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)

    # Privacy settings
    privacy_level = Column(String, default='club_only')  # 'public', 'club_only', 'private'
    share_to_global = Column(Boolean, default=False)  # Opt-in for global platform
    allow_anonymous_sharing = Column(Boolean, default=True)  # Anonymize data when shared globally

    # Additional fields for global platform
    description = Column(String, nullable=True)
    location = Column(String, nullable=True)
    website = Column(String, nullable=True)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)
    role = Column(String, nullable=False, default='sailor')  # 'sailor', 'coach', 'admin'
    sail_number = Column(String, nullable=True)  # Personal sail number for sailors
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

class Boat(Base):
    __tablename__ = "boats"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String, nullable=True)
    klass = Column(String, nullable=True)  # Boat class: "Laser", "420", "GP14", etc.
    sail_number = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_default = Column(Boolean, default=False)

class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    boat_id = Column(Integer, ForeignKey("boats.id"))
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)
    title = Column(String)
    start_ts = Column(DateTime)
    end_ts = Column(DateTime, nullable=True)
    notes = Column(String, nullable=True)

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

class Maneuver(Base):
    __tablename__ = "maneuvers"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)
    maneuver_type = Column(String)  # 'tack', 'gybe', 'turn'
    start_ts = Column(DateTime, index=True)
    end_ts = Column(DateTime)
    angle_change_deg = Column(Float)
    entry_sog_kn = Column(Float)
    min_sog_kn = Column(Float)
    time_through_sec = Column(Float)
    speed_loss_kn = Column(Float)
    score_0_100 = Column(Integer)
    start_lat = Column(Float)
    start_lon = Column(Float)
    end_lat = Column(Float)
    end_lon = Column(Float)
    twd = Column(Float, nullable=True)  # True wind direction at time of maneuver
    detection_params = Column(JSON, nullable=True)  # Store detection parameters used

class PerformanceBaseline(Base):
    __tablename__ = "performance_baselines"
    id = Column(Integer, primary_key=True)
    boat_id = Column(Integer, ForeignKey("boats.id"), index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)
    tws_min = Column(Float)  # Wind speed range min (kts)
    tws_max = Column(Float)  # Wind speed range max (kts)
    twa_min = Column(Float)  # Wind angle range min (degrees)
    twa_max = Column(Float)  # Wind angle range max (degrees)
    avg_sog = Column(Float)  # Average speed over ground (kts)
    std_sog = Column(Float)  # Standard deviation of speed
    sample_count = Column(Integer)  # Number of data points used
    last_updated = Column(DateTime)

class PerformanceAnomaly(Base):
    __tablename__ = "performance_anomalies"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)
    trackpoint_id = Column(Integer, ForeignKey("trackpoints.id"), nullable=True)
    ts = Column(DateTime, index=True)
    lat = Column(Float)
    lon = Column(Float)
    actual_sog = Column(Float)  # Actual speed
    expected_sog = Column(Float)  # Expected speed from baseline
    deviation_kts = Column(Float)  # How much slower/faster
    z_score = Column(Float)  # Statistical significance
    severity = Column(String)  # 'minor', 'moderate', 'severe'
    possible_causes = Column(JSON)  # List of likely explanations
    wind_speed = Column(Float, nullable=True)
    wind_angle = Column(Float, nullable=True)

class FleetComparison(Base):
    __tablename__ = "fleet_comparisons"
    id = Column(Integer, primary_key=True)
    session_a_id = Column(Integer, ForeignKey("sessions.id"), index=True)
    session_b_id = Column(Integer, ForeignKey("sessions.id"), index=True)
    boat_a_id = Column(Integer, ForeignKey("boats.id"))
    boat_b_id = Column(Integer, ForeignKey("boats.id"))
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)
    comparison_ts = Column(DateTime, index=True)

    # Speed comparison
    avg_speed_a = Column(Float)
    avg_speed_b = Column(Float)
    speed_advantage_kts = Column(Float)  # Positive = A faster

    # VMG comparison
    avg_vmg_a = Column(Float, nullable=True)
    avg_vmg_b = Column(Float, nullable=True)
    vmg_advantage_kts = Column(Float, nullable=True)

    # Tack comparison
    avg_tack_time_a = Column(Float, nullable=True)
    avg_tack_time_b = Column(Float, nullable=True)
    tack_efficiency_advantage = Column(Float, nullable=True)  # Seconds saved per tack

    # Distance comparison
    total_distance_a = Column(Float)
    total_distance_b = Column(Float)
    distance_sailed_ratio = Column(Float)  # A/B

    # Overall metrics
    winner = Column(String)  # 'boat_a', 'boat_b', or 'tie'
    performance_gap_percent = Column(Float)  # Overall performance difference
    comparison_metadata = Column(JSON, nullable=True)

class VMGOptimization(Base):
    __tablename__ = "vmg_optimizations"
    id = Column(Integer, primary_key=True)
    boat_id = Column(Integer, ForeignKey("boats.id"), index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)
    tws_min = Column(Float)  # Wind speed range min (kts)
    tws_max = Column(Float)  # Wind speed range max (kts)

    # Upwind optimization
    optimal_upwind_angle = Column(Float)  # Degrees from true wind
    upwind_vmg = Column(Float)  # Best VMG achieved upwind (kts)
    upwind_sample_count = Column(Integer)  # Training data points

    # Downwind optimization
    optimal_downwind_angle = Column(Float)  # Degrees from true wind
    downwind_vmg = Column(Float)  # Best VMG achieved downwind (kts)
    downwind_sample_count = Column(Integer)  # Training data points

    # Model metadata
    model_version = Column(String, default="v1")
    training_accuracy = Column(Float, nullable=True)  # R² score
    last_trained = Column(DateTime)
    training_metadata = Column(JSON, nullable=True)  # Store model parameters

class CoachingRecommendation(Base):
    __tablename__ = "coaching_recommendations"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)
    ts = Column(DateTime, index=True)
    lat = Column(Float)
    lon = Column(Float)

    # Recommendation details
    recommendation_type = Column(String)  # 'tack_now', 'sail_higher', 'sail_lower', 'wind_shift_coming', 'layline_approach', 'speed_mode', 'vmg_mode'
    priority = Column(String)  # 'low', 'medium', 'high', 'critical'
    recommendation_text = Column(String)  # Human-readable coaching advice
    confidence_score = Column(Integer)  # 0-100, how confident the AI is

    # Context and analysis
    context_data = Column(JSON)  # Factors considered: current TWA, VMG, wind conditions, position, etc.
    reasoning = Column(String, nullable=True)  # Why this recommendation was made

    # Tracking effectiveness
    was_followed = Column(Integer, nullable=True)  # 1=yes, 0=no, null=unknown
    outcome_data = Column(JSON, nullable=True)  # Measure recommendation effectiveness
    dismissed = Column(Integer, default=0)  # User dismissed this recommendation

class WindShift(Base):
    __tablename__ = "wind_shifts"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)
    start_ts = Column(DateTime, index=True)
    end_ts = Column(DateTime)

    # Shift characteristics
    shift_magnitude = Column(Float)  # Degrees of shift
    shift_direction = Column(String)  # 'left' (counter-clockwise) or 'right' (clockwise)
    shift_type = Column(String)  # 'persistent', 'oscillating', 'transient'
    confidence = Column(Float)  # 0-1, confidence in classification

    # Wind conditions
    avg_tws_before = Column(Float)  # Average wind speed before shift
    avg_tws_after = Column(Float)  # Average wind speed after shift
    twd_before = Column(Float)  # True wind direction before shift
    twd_after = Column(Float)  # True wind direction after shift

    # Pattern analysis
    oscillation_period = Column(Float, nullable=True)  # Minutes between oscillations (if oscillating)
    pattern_metadata = Column(JSON, nullable=True)  # Additional pattern data

class WindPattern(Base):
    __tablename__ = "wind_patterns"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)
    analyzed_at = Column(DateTime)

    # Overall pattern classification
    dominant_pattern = Column(String)  # 'persistent_right', 'persistent_left', 'oscillating', 'unstable', 'stable'
    pattern_strength = Column(Float)  # 0-1, how consistent the pattern is

    # Oscillation analysis (if applicable)
    is_oscillating = Column(Integer, default=0)  # 1 if oscillating pattern detected
    avg_oscillation_period = Column(Float, nullable=True)  # Average minutes per cycle
    oscillation_amplitude = Column(Float, nullable=True)  # Average degrees of oscillation

    # Prediction
    next_shift_prediction = Column(String, nullable=True)  # 'left', 'right', or 'stable'
    prediction_confidence = Column(Float, nullable=True)  # 0-1

    # Statistical data
    total_shifts_detected = Column(Integer)
    avg_shift_magnitude = Column(Float)
    wind_stability_score = Column(Float)  # 0-100, higher = more stable
    analysis_metadata = Column(JSON, nullable=True)

class Challenge(Base):
    __tablename__ = "challenges"
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True, nullable=False)  # The "ghost" track
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)

    # Challenge details
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    difficulty = Column(String, default='medium')  # 'easy', 'medium', 'hard' - auto-calculated

    # Access control
    is_public = Column(Boolean, default=False)  # Public challenges visible to everyone
    expires_at = Column(DateTime, nullable=True)  # Optional expiration

    # Conditions/filters
    boat_class = Column(String, nullable=True)  # Required boat class to attempt
    min_wind_speed = Column(Float, nullable=True)  # Minimum wind speed
    max_wind_speed = Column(Float, nullable=True)  # Maximum wind speed

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    attempt_count = Column(Integer, default=0)  # Number of attempts
    best_time = Column(Float, nullable=True)  # Best time in seconds vs ghost

class ChallengeAttempt(Base):
    __tablename__ = "challenge_attempts"
    id = Column(Integer, primary_key=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True, nullable=False)  # The attempt session

    # Results
    time_difference = Column(Float, nullable=False)  # Seconds vs ghost (negative = beat ghost)
    max_lead = Column(Float, nullable=True)  # Maximum lead in seconds
    max_deficit = Column(Float, nullable=True)  # Maximum deficit in seconds
    result = Column(String, nullable=False)  # 'won', 'lost', 'tie'

    # Metadata
    submitted_at = Column(DateTime, default=datetime.utcnow, index=True)
    xp_earned = Column(Integer, default=0)  # XP earned from this attempt

class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, index=True)

    # File information
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)  # Path to video file on disk
    file_size = Column(Integer, nullable=False)  # Size in bytes
    duration = Column(Float, nullable=True)  # Duration in seconds

    # URLs
    thumbnail_url = Column(String, nullable=True)  # Thumbnail image URL
    video_url = Column(String, nullable=True)  # Streaming URL

    # Synchronization
    offset_seconds = Column(Float, default=0.0)  # Time offset from session start (for GPS sync)

    # Metadata
    title = Column(String, nullable=True)
    description = Column(String, nullable=True)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

def init_db():
    Base.metadata.create_all(bind=engine)
