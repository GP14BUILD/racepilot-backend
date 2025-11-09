# app/routes/ai.py

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import math

from ..db.models import SessionLocal, TrackPoint, Maneuver, PerformanceBaseline, PerformanceAnomaly, Session, FleetComparison, Boat, VMGOptimization, CoachingRecommendation, WindShift, WindPattern  # uses your existing DB models
from sqlalchemy import and_
from geopy.distance import geodesic
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import PolynomialFeatures
from sklearn.metrics import r2_score

router = APIRouter()


# ------------------------------
# Request / Response Models
# ------------------------------

class DetectRequest(BaseModel):
    session_id: int
    twd: Optional[float] = Field(default=None, description="True Wind Direction (deg)")
    theta_min_deg: float = 55.0        # minimum heading change for manoeuvre
    max_window_sec: float = 20.0       # maximum duration of window
    smooth_window: int = 3             # moving average window
    min_sog_kn: float = 1.0            # ignore very low speeds (noise)
    speed_drop_kn: float = 0.8         # required speed dip


class ManeuverResponse(BaseModel):
    type: str
    start_ts: datetime
    end_ts: datetime
    angle_change_deg: float
    entry_sog_kn: float
    min_sog_kn: float
    time_through_sec: float
    speed_loss_kn: float
    score_0_100: int


class DetectResponse(BaseModel):
    session_id: int
    maneuvers: List[ManeuverResponse]
    params_used: Dict[str, Any]


# ------------------------------
# Helper Functions
# ------------------------------

def unwrap_deg(degs: List[float]) -> List[float]:
    """Unwrap heading values for continuous curves."""
    out = []
    last = None
    offset = 0
    for d in degs:
        if last is None:
            out.append(d)
            last = d
            continue
        diff = d - last
        if diff > 180:
            offset -= 360
        elif diff < -180:
            offset += 360
        out.append(d + offset)
        last = d
    return out


def movavg(vals: List[float], w: int) -> List[float]:
    """Simple moving average smoothing."""
    if w <= 1 or len(vals) < w:
        return vals[:]
    out = []
    acc = 0
    for i, v in enumerate(vals):
        acc += v
        if i >= w:
            acc -= vals[i - w]
        if i >= w - 1:
            out.append(acc / w)
        else:
            out.append(vals[i])  # warm-up
    return out


# ------------------------------
# Core Route
# ------------------------------

@router.post("/maneuvers/detect", response_model=DetectResponse)
def detect_maneuvers(req: DetectRequest):
    db = SessionLocal()
    try:
        pts = (
            db.query(TrackPoint)
            .filter(TrackPoint.session_id == req.session_id)
            .order_by(TrackPoint.ts.asc())
            .all()
        )

        if not pts or len(pts) < 3:
            return DetectResponse(
                session_id=req.session_id,
                maneuvers=[],
                params_used=req.dict()
            )

        ts = [p.ts for p in pts]
        sog = [float(p.sog or 0.0) for p in pts]
        cog = [float(p.cog or 0.0) for p in pts]

        # Smooth noisy phone data
        sog_s = movavg(sog, req.smooth_window)
        cog_u = unwrap_deg(cog)
        cog_s = movavg(cog_u, req.smooth_window)

        maneuvers = []
        i = 0
        n = len(pts)

        while i < n - 2:
            # Skip stationary/non-sailing noise
            if sog_s[i] < req.min_sog_kn:
                i += 1
                continue

            start_t = ts[i]

            # Look ahead until max_window_sec
            j = i + 1
            while j < n and (ts[j] - start_t).total_seconds() <= req.max_window_sec:
                j += 1

            if j - i < 2:
                i += 1
                continue

            # Compute turn metrics
            head_start = cog_s[i]
            head_end = cog_s[j - 1]
            dtheta = abs(head_end - head_start)

            window_sog = sog_s[i:j]
            entry = window_sog[0]
            vmin = min(window_sog)
            speed_drop = max(0.0, entry - vmin)

            # Strong enough turn + meaningful slowdown?
            if dtheta >= req.theta_min_deg and speed_drop >= req.speed_drop_kn:

                # Duration
                t0 = ts[i]
                t1 = ts[j - 1]
                duration = (t1 - t0).total_seconds()

                # Classify type
                mtype = "turn"
                if req.twd is not None:

                    def diff(a, b):
                        """Shortest signed angle difference."""
                        return (a - b + 540) % 360 - 180

                    sdiff = diff(head_start % 360, req.twd % 360)
                    ediff = diff(head_end % 360, req.twd % 360)

                    # Tack crosses the wind direction
                    if (sdiff > 0 > ediff) or (sdiff < 0 < ediff):
                        mtype = "tack"
                    else:
                        # Gybe if turn happens near 180° to wind
                        mid_h = (head_start + head_end) / 2
                        if abs(diff(mid_h % 360, (req.twd + 180) % 360)) < 60:
                            mtype = "gybe"

                # Score 0–100
                Wt, Ws, Wa = 1.5, 12.0, 0.25
                score = 100 - (Wt * duration) - (Ws * speed_drop) - (Wa * max(0, dtheta - 110))
                score = int(max(0, min(100, round(score))))

                # Get coordinates for start and end positions
                start_pt = pts[i]
                end_pt = pts[j - 1]

                # Create maneuver response object
                maneuver_data = ManeuverResponse(
                    type=mtype,
                    start_ts=t0,
                    end_ts=t1,
                    angle_change_deg=round(dtheta, 1),
                    entry_sog_kn=round(entry, 2),
                    min_sog_kn=round(vmin, 2),
                    time_through_sec=round(duration, 1),
                    speed_loss_kn=round(speed_drop, 2),
                    score_0_100=score,
                )
                maneuvers.append(maneuver_data)

                # Save to database
                db_maneuver = Maneuver(
                    session_id=req.session_id,
                    maneuver_type=mtype,
                    start_ts=t0,
                    end_ts=t1,
                    angle_change_deg=round(dtheta, 1),
                    entry_sog_kn=round(entry, 2),
                    min_sog_kn=round(vmin, 2),
                    time_through_sec=round(duration, 1),
                    speed_loss_kn=round(speed_drop, 2),
                    score_0_100=score,
                    start_lat=start_pt.lat,
                    start_lon=start_pt.lon,
                    end_lat=end_pt.lat,
                    end_lon=end_pt.lon,
                    twd=req.twd,
                    detection_params={
                        "theta_min_deg": req.theta_min_deg,
                        "max_window_sec": req.max_window_sec,
                        "smooth_window": req.smooth_window,
                        "min_sog_kn": req.min_sog_kn,
                        "speed_drop_kn": req.speed_drop_kn,
                    }
                )
                db.add(db_maneuver)

                i = j
                continue

            i += 1

        # Commit all maneuvers to database
        db.commit()

        return DetectResponse(
            session_id=req.session_id,
            maneuvers=maneuvers,
            params_used={
                "theta_min_deg": req.theta_min_deg,
                "max_window_sec": req.max_window_sec,
                "smooth_window": req.smooth_window,
                "min_sog_kn": req.min_sog_kn,
                "speed_drop_kn": req.speed_drop_kn,
                "twd": req.twd,
            },
        )

    finally:
        db.close()


# ------------------------------
# Maneuver History Retrieval
# ------------------------------

class ManeuverHistoryResponse(BaseModel):
    id: int
    session_id: int
    maneuver_type: str
    start_ts: datetime
    end_ts: datetime
    angle_change_deg: float
    entry_sog_kn: float
    min_sog_kn: float
    time_through_sec: float
    speed_loss_kn: float
    score_0_100: int
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    twd: Optional[float]

    class Config:
        from_attributes = True


@router.get("/maneuvers/session/{session_id}", response_model=List[ManeuverHistoryResponse])
def get_session_maneuvers(session_id: int):
    """Get all detected maneuvers for a specific session."""
    db = SessionLocal()
    try:
        maneuvers = (
            db.query(Maneuver)
            .filter(Maneuver.session_id == session_id)
            .order_by(Maneuver.start_ts.asc())
            .all()
        )
        return maneuvers
    finally:
        db.close()


@router.get("/maneuvers/stats/{session_id}")
def get_maneuver_stats(session_id: int):
    """Get statistics for all maneuvers in a session."""
    db = SessionLocal()
    try:
        maneuvers = (
            db.query(Maneuver)
            .filter(Maneuver.session_id == session_id)
            .all()
        )

        if not maneuvers:
            return {
                "session_id": session_id,
                "total_maneuvers": 0,
                "tacks": 0,
                "gybes": 0,
                "turns": 0,
                "avg_tack_score": None,
                "avg_gybe_score": None,
                "avg_tack_time": None,
                "avg_speed_loss": None,
                "best_tack": None,
                "worst_tack": None,
            }

        tacks = [m for m in maneuvers if m.maneuver_type == "tack"]
        gybes = [m for m in maneuvers if m.maneuver_type == "gybe"]
        turns = [m for m in maneuvers if m.maneuver_type == "turn"]

        avg_tack_score = sum(t.score_0_100 for t in tacks) / len(tacks) if tacks else None
        avg_gybe_score = sum(g.score_0_100 for g in gybes) / len(gybes) if gybes else None
        avg_tack_time = sum(t.time_through_sec for t in tacks) / len(tacks) if tacks else None
        avg_speed_loss = sum(m.speed_loss_kn for m in maneuvers) / len(maneuvers) if maneuvers else None

        best_tack = max(tacks, key=lambda t: t.score_0_100) if tacks else None
        worst_tack = min(tacks, key=lambda t: t.score_0_100) if tacks else None

        return {
            "session_id": session_id,
            "total_maneuvers": len(maneuvers),
            "tacks": len(tacks),
            "gybes": len(gybes),
            "turns": len(turns),
            "avg_tack_score": round(avg_tack_score, 1) if avg_tack_score else None,
            "avg_gybe_score": round(avg_gybe_score, 1) if avg_gybe_score else None,
            "avg_tack_time": round(avg_tack_time, 1) if avg_tack_time else None,
            "avg_speed_loss": round(avg_speed_loss, 2) if avg_speed_loss else None,
            "best_tack": {
                "id": best_tack.id,
                "score": best_tack.score_0_100,
                "time": best_tack.time_through_sec,
                "timestamp": best_tack.start_ts.isoformat(),
            } if best_tack else None,
            "worst_tack": {
                "id": worst_tack.id,
                "score": worst_tack.score_0_100,
                "time": worst_tack.time_through_sec,
                "timestamp": worst_tack.start_ts.isoformat(),
            } if worst_tack else None,
        }
    finally:
        db.close()


# ------------------------------
# Performance Anomaly Detection
# ------------------------------

def calculate_baseline_for_boat(db, boat_id: int, force_recalc: bool = False):
    """Calculate performance baselines for a boat across different wind conditions."""
    # Define wind speed and angle bins
    tws_bins = [(0, 6), (6, 12), (12, 18), (18, 30)]  # Light, Medium, Fresh, Strong
    twa_bins = [(0, 50), (50, 70), (70, 110), (110, 180)]  # Close-hauled, Reaching, Broad reach, Running

    # Get all sessions for this boat
    sessions = db.query(Session).filter(Session.boat_id == boat_id).all()
    session_ids = [s.id for s in sessions]

    if not session_ids:
        return []

    # Get all track points with wind data
    points = (
        db.query(TrackPoint)
        .filter(and_(
            TrackPoint.session_id.in_(session_ids),
            TrackPoint.tws.isnot(None),
            TrackPoint.twa.isnot(None),
            TrackPoint.sog > 0.5  # Filter out stopped/drifting
        ))
        .all()
    )

    baselines = []

    # Calculate baseline for each combination of wind conditions
    for tws_min, tws_max in tws_bins:
        for twa_min, twa_max in twa_bins:
            # Filter points in this wind condition
            bin_points = [
                p for p in points
                if tws_min <= p.tws < tws_max and twa_min <= abs(p.twa) < twa_max
            ]

            if len(bin_points) < 10:  # Need at least 10 points for meaningful statistics
                continue

            # Calculate statistics
            speeds = [p.sog for p in bin_points]
            avg_sog = sum(speeds) / len(speeds)
            variance = sum((s - avg_sog) ** 2 for s in speeds) / len(speeds)
            std_sog = variance ** 0.5

            # Check if baseline exists
            existing = db.query(PerformanceBaseline).filter(
                and_(
                    PerformanceBaseline.boat_id == boat_id,
                    PerformanceBaseline.tws_min == tws_min,
                    PerformanceBaseline.tws_max == tws_max,
                    PerformanceBaseline.twa_min == twa_min,
                    PerformanceBaseline.twa_max == twa_max
                )
            ).first()

            if existing and not force_recalc:
                # Update existing
                existing.avg_sog = avg_sog
                existing.std_sog = std_sog
                existing.sample_count = len(bin_points)
                existing.last_updated = datetime.utcnow()
            else:
                # Create new
                baseline = PerformanceBaseline(
                    boat_id=boat_id,
                    tws_min=tws_min,
                    tws_max=tws_max,
                    twa_min=twa_min,
                    twa_max=twa_max,
                    avg_sog=avg_sog,
                    std_sog=std_sog,
                    sample_count=len(bin_points),
                    last_updated=datetime.utcnow()
                )
                db.add(baseline)
                baselines.append(baseline)

    db.commit()
    return baselines


@router.post("/anomalies/detect/{session_id}")
def detect_anomalies(session_id: int, z_threshold: float = 2.0):
    """Detect performance anomalies in a session using statistical analysis."""
    db = SessionLocal()
    try:
        # Get session info
        session = db.query(Session).filter(Session.id == session_id).first()
        if not session:
            return {"error": "Session not found"}

        # Ensure we have baselines for this boat
        baselines_count = db.query(PerformanceBaseline).filter(
            PerformanceBaseline.boat_id == session.boat_id
        ).count()

        if baselines_count == 0:
            # Calculate baselines first
            calculate_baseline_for_boat(db, session.boat_id)

        # Get all baselines for this boat
        baselines = db.query(PerformanceBaseline).filter(
            PerformanceBaseline.boat_id == session.boat_id
        ).all()

        if not baselines:
            return {
                "session_id": session_id,
                "anomalies": [],
                "message": "Insufficient data to establish performance baselines"
            }

        # Get track points with wind data
        points = (
            db.query(TrackPoint)
            .filter(and_(
                TrackPoint.session_id == session_id,
                TrackPoint.tws.isnot(None),
                TrackPoint.twa.isnot(None),
                TrackPoint.sog > 0.5
            ))
            .all()
        )

        anomalies = []

        for point in points:
            # Find matching baseline
            matching_baseline = None
            for bl in baselines:
                if (bl.tws_min <= point.tws < bl.tws_max and
                    bl.twa_min <= abs(point.twa) < bl.twa_max):
                    matching_baseline = bl
                    break

            if not matching_baseline or matching_baseline.std_sog == 0:
                continue

            # Calculate z-score
            deviation = point.sog - matching_baseline.avg_sog
            z_score = deviation / matching_baseline.std_sog

            # Check if anomaly (significantly slower)
            if z_score < -z_threshold:  # Negative = slower than expected
                # Determine severity
                if z_score < -3.0:
                    severity = "severe"
                elif z_score < -2.5:
                    severity = "moderate"
                else:
                    severity = "minor"

                # Analyze possible causes
                possible_causes = []

                # Check if just after a tack
                recent_maneuver = db.query(Maneuver).filter(
                    and_(
                        Maneuver.session_id == session_id,
                        Maneuver.start_ts <= point.ts,
                        Maneuver.end_ts >= point.ts - timedelta(seconds=10)
                    )
                ).first()

                if recent_maneuver:
                    possible_causes.append("Speed loss from recent tack/gybe")

                # Check wind angle (pinching or sailing too low)
                if abs(point.twa) < 35:
                    possible_causes.append("Sailing too close to wind (pinching)")
                elif abs(point.twa) > 50 and matching_baseline.twa_max <= 70:
                    possible_causes.append("Sailing too low (footing)")

                # Check if wind dropped
                if point.tws < matching_baseline.tws_min + 2:
                    possible_causes.append("Wind speed below normal for conditions")

                if not possible_causes:
                    possible_causes.append("Unknown - review sail trim and technique")

                # Create anomaly record
                anomaly = PerformanceAnomaly(
                    session_id=session_id,
                    trackpoint_id=point.id,
                    ts=point.ts,
                    lat=point.lat,
                    lon=point.lon,
                    actual_sog=point.sog,
                    expected_sog=matching_baseline.avg_sog,
                    deviation_kts=deviation,
                    z_score=z_score,
                    severity=severity,
                    possible_causes=possible_causes,
                    wind_speed=point.tws,
                    wind_angle=point.twa
                )
                db.add(anomaly)
                anomalies.append(anomaly)

        db.commit()

        return {
            "session_id": session_id,
            "anomalies_detected": len(anomalies),
            "anomalies": [{
                "id": a.id,
                "ts": a.ts.isoformat(),
                "lat": a.lat,
                "lon": a.lon,
                "actual_sog": round(a.actual_sog, 2),
                "expected_sog": round(a.expected_sog, 2),
                "deviation_kts": round(a.deviation_kts, 2),
                "z_score": round(a.z_score, 2),
                "severity": a.severity,
                "possible_causes": a.possible_causes
            } for a in anomalies]
        }

    finally:
        db.close()


@router.get("/anomalies/session/{session_id}")
def get_session_anomalies(session_id: int):
    """Get all detected anomalies for a session."""
    db = SessionLocal()
    try:
        anomalies = (
            db.query(PerformanceAnomaly)
            .filter(PerformanceAnomaly.session_id == session_id)
            .order_by(PerformanceAnomaly.ts.asc())
            .all()
        )

        return {
            "session_id": session_id,
            "total_anomalies": len(anomalies),
            "by_severity": {
                "severe": len([a for a in anomalies if a.severity == "severe"]),
                "moderate": len([a for a in anomalies if a.severity == "moderate"]),
                "minor": len([a for a in anomalies if a.severity == "minor"])
            },
            "anomalies": [{
                "id": a.id,
                "ts": a.ts.isoformat(),
                "lat": a.lat,
                "lon": a.lon,
                "actual_sog": round(a.actual_sog, 2),
                "expected_sog": round(a.expected_sog, 2),
                "deviation_kts": round(a.deviation_kts, 2),
                "z_score": round(a.z_score, 2),
                "severity": a.severity,
                "possible_causes": a.possible_causes,
                "wind_speed": a.wind_speed,
                "wind_angle": a.wind_angle
            } for a in anomalies]
        }
    finally:
        db.close()


@router.post("/baselines/calculate/{boat_id}")
def calculate_baselines(boat_id: int):
    """Manually trigger baseline calculation for a boat."""
    db = SessionLocal()
    try:
        baselines = calculate_baseline_for_boat(db, boat_id, force_recalc=True)
        return {
            "boat_id": boat_id,
            "baselines_created": len(baselines),
            "message": "Performance baselines calculated successfully"
        }
    finally:
        db.close()


@router.get("/baselines/{boat_id}")
def get_boat_baselines(boat_id: int):
    """Get all performance baselines for a boat."""
    db = SessionLocal()
    try:
        baselines = (
            db.query(PerformanceBaseline)
            .filter(PerformanceBaseline.boat_id == boat_id)
            .all()
        )

        return {
            "boat_id": boat_id,
            "total_baselines": len(baselines),
            "baselines": [{
                "id": bl.id,
                "wind_speed_range": f"{bl.tws_min}-{bl.tws_max} kts",
                "wind_angle_range": f"{bl.twa_min}-{bl.twa_max}°",
                "avg_speed": round(bl.avg_sog, 2),
                "std_dev": round(bl.std_sog, 2),
                "sample_count": bl.sample_count,
                "last_updated": bl.last_updated.isoformat() if bl.last_updated else None
            } for bl in baselines]
        }
    finally:
        db.close()


# ------------------------------
# Fleet Comparison & Analytics
# ------------------------------

def calculate_vmg(sog: float, cog: float, twa: float, twd: float) -> float:
    """Calculate Velocity Made Good towards wind."""
    # Calculate angle to wind
    wind_angle = abs(((cog - twd) + 180) % 360 - 180)
    # VMG = SOG * cos(angle_to_wind)
    return sog * math.cos(math.radians(wind_angle))


@router.post("/fleet/compare")
def compare_sessions(session_a_id: int, session_b_id: int):
    """Compare two sailing sessions with detailed performance metrics."""
    db = SessionLocal()
    try:
        # Get sessions
        session_a = db.query(Session).filter(Session.id == session_a_id).first()
        session_b = db.query(Session).filter(Session.id == session_b_id).first()

        if not session_a or not session_b:
            return {"error": "One or both sessions not found"}

        # Get track points
        points_a = (
            db.query(TrackPoint)
            .filter(TrackPoint.session_id == session_a_id)
            .order_by(TrackPoint.ts.asc())
            .all()
        )
        points_b = (
            db.query(TrackPoint)
            .filter(TrackPoint.session_id == session_b_id)
            .order_by(TrackPoint.ts.asc())
            .all()
        )

        if not points_a or not points_b:
            return {"error": "Insufficient data for comparison"}

        # Calculate average speeds
        avg_speed_a = sum(p.sog for p in points_a) / len(points_a)
        avg_speed_b = sum(p.sog for p in points_b) / len(points_b)
        speed_advantage = avg_speed_a - avg_speed_b

        # Calculate VMG if wind data available
        avg_vmg_a = None
        avg_vmg_b = None
        vmg_advantage = None

        points_a_with_wind = [p for p in points_a if p.twa and p.tws]
        points_b_with_wind = [p for p in points_b if p.twa and p.tws]

        if points_a_with_wind and points_b_with_wind:
            # Use simple VMG calculation
            vmg_a_vals = []
            for p in points_a_with_wind:
                twd = (p.cog + p.twa) % 360
                vmg = calculate_vmg(p.sog, p.cog, p.twa, twd)
                vmg_a_vals.append(vmg)
            avg_vmg_a = sum(vmg_a_vals) / len(vmg_a_vals) if vmg_a_vals else None

            vmg_b_vals = []
            for p in points_b_with_wind:
                twd = (p.cog + p.twa) % 360
                vmg = calculate_vmg(p.sog, p.cog, p.twa, twd)
                vmg_b_vals.append(vmg)
            avg_vmg_b = sum(vmg_b_vals) / len(vmg_b_vals) if vmg_b_vals else None

            if avg_vmg_a is not None and avg_vmg_b is not None:
                vmg_advantage = avg_vmg_a - avg_vmg_b

        # Calculate total distances
        total_distance_a = 0.0
        for i in range(len(points_a) - 1):
            p1 = (points_a[i].lat, points_a[i].lon)
            p2 = (points_a[i + 1].lat, points_a[i + 1].lon)
            total_distance_a += geodesic(p1, p2).kilometers

        total_distance_b = 0.0
        for i in range(len(points_b) - 1):
            p1 = (points_b[i].lat, points_b[i].lon)
            p2 = (points_b[i + 1].lat, points_b[i + 1].lon)
            total_distance_b += geodesic(p1, p2).kilometers

        distance_ratio = total_distance_a / total_distance_b if total_distance_b > 0 else 1.0

        # Get tack statistics
        maneuvers_a = db.query(Maneuver).filter(Maneuver.session_id == session_a_id).all()
        maneuvers_b = db.query(Maneuver).filter(Maneuver.session_id == session_b_id).all()

        tacks_a = [m for m in maneuvers_a if m.maneuver_type == "tack"]
        tacks_b = [m for m in maneuvers_b if m.maneuver_type == "tack"]

        avg_tack_time_a = sum(t.time_through_sec for t in tacks_a) / len(tacks_a) if tacks_a else None
        avg_tack_time_b = sum(t.time_through_sec for t in tacks_b) / len(tacks_b) if tacks_b else None

        tack_advantage = None
        if avg_tack_time_a and avg_tack_time_b:
            tack_advantage = avg_tack_time_b - avg_tack_time_a  # Positive = A is faster

        # Determine winner
        score_a = 0
        score_b = 0

        if avg_speed_a > avg_speed_b:
            score_a += 1
        elif avg_speed_b > avg_speed_a:
            score_b += 1

        if avg_vmg_a and avg_vmg_b:
            if avg_vmg_a > avg_vmg_b:
                score_a += 1
            elif avg_vmg_b > avg_vmg_a:
                score_b += 1

        if avg_tack_time_a and avg_tack_time_b:
            if avg_tack_time_a < avg_tack_time_b:
                score_a += 1
            elif avg_tack_time_b < avg_tack_time_a:
                score_b += 1

        if score_a > score_b:
            winner = "boat_a"
        elif score_b > score_a:
            winner = "boat_b"
        else:
            winner = "tie"

        # Calculate overall performance gap
        speed_gap = abs(speed_advantage) / max(avg_speed_a, avg_speed_b) * 100 if max(avg_speed_a, avg_speed_b) > 0 else 0

        # Save comparison
        comparison = FleetComparison(
            session_a_id=session_a_id,
            session_b_id=session_b_id,
            boat_a_id=session_a.boat_id,
            boat_b_id=session_b.boat_id,
            comparison_ts=datetime.utcnow(),
            avg_speed_a=avg_speed_a,
            avg_speed_b=avg_speed_b,
            speed_advantage_kts=speed_advantage,
            avg_vmg_a=avg_vmg_a,
            avg_vmg_b=avg_vmg_b,
            vmg_advantage_kts=vmg_advantage,
            avg_tack_time_a=avg_tack_time_a,
            avg_tack_time_b=avg_tack_time_b,
            tack_efficiency_advantage=tack_advantage,
            total_distance_a=total_distance_a,
            total_distance_b=total_distance_b,
            distance_sailed_ratio=distance_ratio,
            winner=winner,
            performance_gap_percent=speed_gap,
            comparison_metadata={
                "tacks_a": len(tacks_a),
                "tacks_b": len(tacks_b),
                "points_a": len(points_a),
                "points_b": len(points_b)
            }
        )
        db.add(comparison)
        db.commit()

        # Get boat names
        boat_a = db.query(Boat).filter(Boat.id == session_a.boat_id).first()
        boat_b = db.query(Boat).filter(Boat.id == session_b.boat_id).first()

        return {
            "comparison_id": comparison.id,
            "session_a": {
                "id": session_a_id,
                "boat_name": boat_a.name if boat_a else "Unknown",
                "avg_speed": round(avg_speed_a, 2),
                "avg_vmg": round(avg_vmg_a, 2) if avg_vmg_a else None,
                "avg_tack_time": round(avg_tack_time_a, 2) if avg_tack_time_a else None,
                "total_distance": round(total_distance_a, 2),
                "tacks": len(tacks_a)
            },
            "session_b": {
                "id": session_b_id,
                "boat_name": boat_b.name if boat_b else "Unknown",
                "avg_speed": round(avg_speed_b, 2),
                "avg_vmg": round(avg_vmg_b, 2) if avg_vmg_b else None,
                "avg_tack_time": round(avg_tack_time_b, 2) if avg_tack_time_b else None,
                "total_distance": round(total_distance_b, 2),
                "tacks": len(tacks_b)
            },
            "comparison": {
                "winner": winner,
                "speed_advantage_kts": round(speed_advantage, 2),
                "vmg_advantage_kts": round(vmg_advantage, 2) if vmg_advantage else None,
                "tack_time_advantage_sec": round(tack_advantage, 2) if tack_advantage else None,
                "distance_ratio": round(distance_ratio, 3),
                "performance_gap_percent": round(speed_gap, 1)
            }
        }

    finally:
        db.close()


@router.get("/fleet/leaderboard")
def get_leaderboard(metric: str = "avg_speed", limit: int = 10):
    """Get leaderboard of top performers by various metrics."""
    db = SessionLocal()
    try:
        # Get all sessions with track points
        sessions = (
            db.query(Session)
            .join(TrackPoint, TrackPoint.session_id == Session.id)
            .distinct()
            .all()
        )

        leaderboard = []

        for session in sessions:
            points = (
                db.query(TrackPoint)
                .filter(TrackPoint.session_id == session.id)
                .all()
            )

            if not points:
                continue

            boat = db.query(Boat).filter(Boat.id == session.boat_id).first()

            # Calculate metrics
            avg_speed = sum(p.sog for p in points) / len(points)
            max_speed = max(p.sog for p in points)

            # Distance
            total_distance = 0.0
            for i in range(len(points) - 1):
                p1 = (points[i].lat, points[i].lon)
                p2 = (points[i + 1].lat, points[i + 1].lon)
                total_distance += geodesic(p1, p2).kilometers

            # Tack stats
            maneuvers = db.query(Maneuver).filter(Maneuver.session_id == session.id).all()
            tacks = [m for m in maneuvers if m.maneuver_type == "tack"]
            avg_tack_score = sum(t.score_0_100 for t in tacks) / len(tacks) if tacks else 0

            leaderboard.append({
                "session_id": session.id,
                "boat_name": boat.name if boat else "Unknown",
                "boat_class": boat.klass if boat else "Unknown",
                "date": session.start_ts.isoformat(),
                "avg_speed": round(avg_speed, 2),
                "max_speed": round(max_speed, 2),
                "total_distance": round(total_distance, 2),
                "avg_tack_score": round(avg_tack_score, 1),
                "tacks_count": len(tacks)
            })

        # Sort by requested metric
        metric_key_map = {
            "avg_speed": "avg_speed",
            "max_speed": "max_speed",
            "distance": "total_distance",
            "tack_score": "avg_tack_score"
        }

        sort_key = metric_key_map.get(metric, "avg_speed")
        leaderboard.sort(key=lambda x: x[sort_key], reverse=True)

        return {
            "metric": metric,
            "total_sessions": len(leaderboard),
            "leaderboard": leaderboard[:limit]
        }

    finally:
        db.close()


# ------------------------------
# VMG Optimization & Learning
# ------------------------------

def calculate_vmg_from_point(point) -> Optional[float]:
    """Calculate VMG from a track point with wind data."""
    if not point.twa or not point.tws or not point.sog:
        return None

    # VMG = SOG * cos(TWA)
    vmg = point.sog * math.cos(math.radians(abs(point.twa)))
    return vmg


@router.post("/vmg/optimize/{boat_id}")
def optimize_vmg_for_boat(boat_id: int):
    """Train personalized VMG optimization model for a boat using historical data."""
    db = SessionLocal()
    try:
        # Get all sessions for this boat
        sessions = db.query(Session).filter(Session.boat_id == boat_id).all()
        session_ids = [s.id for s in sessions]

        if not session_ids:
            return {"error": "No sessions found for this boat"}

        # Get all track points with wind data
        points = (
            db.query(TrackPoint)
            .filter(and_(
                TrackPoint.session_id.in_(session_ids),
                TrackPoint.tws.isnot(None),
                TrackPoint.twa.isnot(None),
                TrackPoint.sog > 1.0  # Filter out very slow/stationary points
            ))
            .all()
        )

        if len(points) < 50:
            return {"error": "Insufficient data for VMG optimization (need at least 50 points)"}

        # Convert to pandas DataFrame for analysis
        data = []
        for p in points:
            vmg = calculate_vmg_from_point(p)
            if vmg is not None:
                data.append({
                    'tws': p.tws,
                    'twa': abs(p.twa),  # Use absolute angle
                    'sog': p.sog,
                    'vmg': vmg
                })

        df = pd.DataFrame(data)

        # Define wind speed bins
        tws_bins = [(0, 6), (6, 12), (12, 18), (18, 30)]

        results = []

        for tws_min, tws_max in tws_bins:
            # Filter points in this wind range
            bin_df = df[(df['tws'] >= tws_min) & (df['tws'] < tws_max)]

            if len(bin_df) < 20:
                continue  # Not enough data for this wind range

            # Separate upwind and downwind
            upwind_df = bin_df[bin_df['twa'] < 90]
            downwind_df = bin_df[bin_df['twa'] >= 90]

            optimal_upwind_angle = None
            upwind_vmg = None
            upwind_samples = 0

            if len(upwind_df) >= 10:
                # Find optimal upwind angle (angle with best average VMG)
                # Group by TWA ranges and find best
                upwind_df['twa_bin'] = (upwind_df['twa'] / 5).round() * 5  # 5° bins
                vmg_by_angle = upwind_df.groupby('twa_bin')['vmg'].agg(['mean', 'count'])
                vmg_by_angle = vmg_by_angle[vmg_by_angle['count'] >= 3]  # At least 3 samples

                if len(vmg_by_angle) > 0:
                    best_angle_idx = vmg_by_angle['mean'].idxmax()
                    optimal_upwind_angle = float(best_angle_idx)
                    upwind_vmg = float(vmg_by_angle.loc[best_angle_idx, 'mean'])
                    upwind_samples = int(len(upwind_df))

            optimal_downwind_angle = None
            downwind_vmg = None
            downwind_samples = 0

            if len(downwind_df) >= 10:
                # Find optimal downwind angle
                downwind_df['twa_bin'] = (downwind_df['twa'] / 5).round() * 5  # 5° bins
                vmg_by_angle = downwind_df.groupby('twa_bin')['vmg'].agg(['mean', 'count'])
                vmg_by_angle = vmg_by_angle[vmg_by_angle['count'] >= 3]

                if len(vmg_by_angle) > 0:
                    best_angle_idx = vmg_by_angle['mean'].idxmax()
                    optimal_downwind_angle = float(best_angle_idx)
                    downwind_vmg = float(vmg_by_angle.loc[best_angle_idx, 'mean'])
                    downwind_samples = int(len(downwind_df))

            # Skip if we don't have at least one direction
            if optimal_upwind_angle is None and optimal_downwind_angle is None:
                continue

            # Check if optimization already exists
            existing = db.query(VMGOptimization).filter(
                and_(
                    VMGOptimization.boat_id == boat_id,
                    VMGOptimization.tws_min == tws_min,
                    VMGOptimization.tws_max == tws_max
                )
            ).first()

            # Calculate R² score as training accuracy
            r2 = 0.0
            if len(bin_df) > 20:
                try:
                    X = bin_df[['twa', 'tws']].values
                    y = bin_df['vmg'].values
                    poly = PolynomialFeatures(degree=2)
                    X_poly = poly.fit_transform(X)
                    model = Ridge(alpha=1.0)
                    model.fit(X_poly, y)
                    y_pred = model.predict(X_poly)
                    r2 = r2_score(y, y_pred)
                except:
                    r2 = 0.0

            if existing:
                # Update existing
                if optimal_upwind_angle is not None:
                    existing.optimal_upwind_angle = optimal_upwind_angle
                    existing.upwind_vmg = upwind_vmg
                    existing.upwind_sample_count = upwind_samples
                if optimal_downwind_angle is not None:
                    existing.optimal_downwind_angle = optimal_downwind_angle
                    existing.downwind_vmg = downwind_vmg
                    existing.downwind_sample_count = downwind_samples
                existing.last_trained = datetime.utcnow()
                existing.training_accuracy = r2
                existing.training_metadata = {
                    "total_points": int(len(bin_df)),
                    "upwind_points": int(len(upwind_df)),
                    "downwind_points": int(len(downwind_df))
                }
            else:
                # Create new
                vmg_opt = VMGOptimization(
                    boat_id=boat_id,
                    tws_min=tws_min,
                    tws_max=tws_max,
                    optimal_upwind_angle=optimal_upwind_angle,
                    upwind_vmg=upwind_vmg,
                    upwind_sample_count=upwind_samples,
                    optimal_downwind_angle=optimal_downwind_angle,
                    downwind_vmg=downwind_vmg,
                    downwind_sample_count=downwind_samples,
                    model_version="v1",
                    training_accuracy=r2,
                    last_trained=datetime.utcnow(),
                    training_metadata={
                        "total_points": int(len(bin_df)),
                        "upwind_points": int(len(upwind_df)),
                        "downwind_points": int(len(downwind_df))
                    }
                )
                db.add(vmg_opt)

            results.append({
                "wind_range": f"{tws_min}-{tws_max} kts",
                "upwind_angle": round(optimal_upwind_angle, 1) if optimal_upwind_angle else None,
                "upwind_vmg": round(upwind_vmg, 2) if upwind_vmg else None,
                "downwind_angle": round(optimal_downwind_angle, 1) if optimal_downwind_angle else None,
                "downwind_vmg": round(downwind_vmg, 2) if downwind_vmg else None,
                "training_accuracy": round(r2, 3)
            })

        db.commit()

        return {
            "boat_id": boat_id,
            "optimizations_created": len(results),
            "total_data_points": len(df),
            "results": results
        }

    finally:
        db.close()


@router.get("/vmg/optimal/{boat_id}")
def get_optimal_vmg(boat_id: int, tws: float, upwind: bool = True):
    """Get optimal VMG angle for given wind conditions."""
    db = SessionLocal()
    try:
        # Find matching optimization
        optimizations = db.query(VMGOptimization).filter(
            and_(
                VMGOptimization.boat_id == boat_id,
                VMGOptimization.tws_min <= tws,
                VMGOptimization.tws_max > tws
            )
        ).all()

        if not optimizations:
            # Fall back to generic angles if no learned data
            if upwind:
                # Generic upwind angles based on wind speed
                if tws < 8:
                    angle = 45
                elif tws < 12:
                    angle = 42
                elif tws < 18:
                    angle = 38
                else:
                    angle = 35
            else:
                # Generic downwind angles
                if tws < 8:
                    angle = 150
                elif tws < 12:
                    angle = 145
                else:
                    angle = 140

            return {
                "boat_id": boat_id,
                "tws": tws,
                "optimal_angle": angle,
                "learned": False,
                "message": "Using generic polar - no learned data available. Run optimization to learn your boat's performance."
            }

        opt = optimizations[0]

        if upwind:
            if opt.optimal_upwind_angle is None:
                return {"error": "No upwind data learned for this wind range"}

            return {
                "boat_id": boat_id,
                "tws": tws,
                "wind_range": f"{opt.tws_min}-{opt.tws_max} kts",
                "optimal_angle": round(opt.optimal_upwind_angle, 1),
                "expected_vmg": round(opt.upwind_vmg, 2),
                "sample_count": opt.upwind_sample_count,
                "learned": True,
                "last_trained": opt.last_trained.isoformat() if opt.last_trained else None,
                "training_accuracy": round(opt.training_accuracy, 3) if opt.training_accuracy else None
            }
        else:
            if opt.optimal_downwind_angle is None:
                return {"error": "No downwind data learned for this wind range"}

            return {
                "boat_id": boat_id,
                "tws": tws,
                "wind_range": f"{opt.tws_min}-{opt.tws_max} kts",
                "optimal_angle": round(opt.optimal_downwind_angle, 1),
                "expected_vmg": round(opt.downwind_vmg, 2),
                "sample_count": opt.downwind_sample_count,
                "learned": True,
                "last_trained": opt.last_trained.isoformat() if opt.last_trained else None,
                "training_accuracy": round(opt.training_accuracy, 3) if opt.training_accuracy else None
            }

    finally:
        db.close()


@router.get("/vmg/all/{boat_id}")
def get_all_vmg_optimizations(boat_id: int):
    """Get all VMG optimizations for a boat."""
    db = SessionLocal()
    try:
        optimizations = db.query(VMGOptimization).filter(
            VMGOptimization.boat_id == boat_id
        ).all()

        return {
            "boat_id": boat_id,
            "total_optimizations": len(optimizations),
            "optimizations": [{
                "id": opt.id,
                "wind_range": f"{opt.tws_min}-{opt.tws_max} kts",
                "upwind_angle": round(opt.optimal_upwind_angle, 1) if opt.optimal_upwind_angle else None,
                "upwind_vmg": round(opt.upwind_vmg, 2) if opt.upwind_vmg else None,
                "upwind_samples": opt.upwind_sample_count,
                "downwind_angle": round(opt.optimal_downwind_angle, 1) if opt.optimal_downwind_angle else None,
                "downwind_vmg": round(opt.downwind_vmg, 2) if opt.downwind_vmg else None,
                "downwind_samples": opt.downwind_sample_count,
                "last_trained": opt.last_trained.isoformat() if opt.last_trained else None,
                "accuracy": round(opt.training_accuracy, 3) if opt.training_accuracy else None
            } for opt in optimizations]
        }

    finally:
        db.close()


# ==============================
# COACHING RECOMMENDATION ENGINE
# ==============================

def calculate_vmg(sog: float, twa: float) -> float:
    """Calculate VMG (Velocity Made Good)."""
    return abs(sog * math.cos(math.radians(twa)))


@router.post("/coaching/analyze/{session_id}")
def analyze_and_recommend(session_id: int, current_time: Optional[datetime] = None):
    """
    Multi-criteria coaching engine that analyzes current sailing conditions
    and provides contextual recommendations.

    Analyzes:
    - VMG optimization (are you at optimal angle?)
    - Speed performance (are you sailing at expected speed?)
    - Maneuver timing (should you tack?)
    - Wind shift patterns (is the wind shifting?)
    - Tactical positioning
    """
    db = SessionLocal()
    try:
        # Get session and boat info
        session = db.query(Session).filter(Session.id == session_id).first()
        if not session:
            return {"error": "Session not found"}

        boat_id = session.boat_id
        if not boat_id:
            return {"error": "Session has no associated boat"}

        # Get recent track points (last 5 minutes for analysis)
        if current_time is None:
            # Get the most recent track point time
            latest_point = db.query(TrackPoint).filter(
                TrackPoint.session_id == session_id
            ).order_by(TrackPoint.ts.desc()).first()

            if not latest_point:
                return {"error": "No track points found"}

            current_time = latest_point.ts

        # Get last 5 minutes of data
        analysis_window = current_time - timedelta(minutes=5)
        recent_points = db.query(TrackPoint).filter(
            and_(
                TrackPoint.session_id == session_id,
                TrackPoint.ts >= analysis_window,
                TrackPoint.ts <= current_time
            )
        ).order_by(TrackPoint.ts.desc()).all()

        if len(recent_points) < 10:
            return {"error": "Insufficient data for analysis"}

        # Get current point (most recent)
        current_point = recent_points[0]

        # Validate required data
        if current_point.tws is None or current_point.twa is None:
            return {"error": "Missing wind data for analysis"}

        recommendations = []

        # ====================
        # 1. VMG ANALYSIS
        # ====================
        current_tws = current_point.tws
        current_twa = abs(current_point.twa)
        current_sog = current_point.sog
        current_vmg = calculate_vmg(current_sog, current_twa)

        # Determine if upwind or downwind
        is_upwind = current_twa < 90

        # Get optimal VMG for current conditions
        vmg_opts = db.query(VMGOptimization).filter(
            VMGOptimization.boat_id == boat_id,
            VMGOptimization.tws_min <= current_tws,
            VMGOptimization.tws_max > current_tws
        ).first()

        if vmg_opts:
            if is_upwind and vmg_opts.optimal_upwind_angle:
                optimal_angle = vmg_opts.optimal_upwind_angle
                optimal_vmg = vmg_opts.upwind_vmg
                angle_deviation = current_twa - optimal_angle
                vmg_loss = optimal_vmg - current_vmg

                if abs(angle_deviation) > 5:
                    if angle_deviation > 0:
                        # Sailing too high (pinching)
                        priority = "high" if angle_deviation > 10 else "medium"
                        recommendations.append({
                            "type": "sail_lower",
                            "priority": priority,
                            "text": f"Sail {abs(angle_deviation):.1f}° lower to optimal VMG angle. You're pinching and losing {vmg_loss:.2f} kts of VMG.",
                            "confidence": 85,
                            "reasoning": f"Current TWA: {current_twa:.1f}°, Optimal: {optimal_angle:.1f}°. Current VMG: {current_vmg:.2f} kts vs optimal {optimal_vmg:.2f} kts",
                            "context": {
                                "current_twa": round(current_twa, 1),
                                "optimal_twa": round(optimal_angle, 1),
                                "angle_deviation": round(angle_deviation, 1),
                                "current_vmg": round(current_vmg, 2),
                                "optimal_vmg": round(optimal_vmg, 2),
                                "vmg_loss": round(vmg_loss, 2)
                            }
                        })
                    else:
                        # Sailing too low (footing)
                        priority = "high" if abs(angle_deviation) > 10 else "medium"
                        recommendations.append({
                            "type": "sail_higher",
                            "priority": priority,
                            "text": f"Sail {abs(angle_deviation):.1f}° higher to optimal VMG angle. You're footing and losing {vmg_loss:.2f} kts of VMG.",
                            "confidence": 85,
                            "reasoning": f"Current TWA: {current_twa:.1f}°, Optimal: {optimal_angle:.1f}°. Current VMG: {current_vmg:.2f} kts vs optimal {optimal_vmg:.2f} kts",
                            "context": {
                                "current_twa": round(current_twa, 1),
                                "optimal_twa": round(optimal_angle, 1),
                                "angle_deviation": round(angle_deviation, 1),
                                "current_vmg": round(current_vmg, 2),
                                "optimal_vmg": round(optimal_vmg, 2),
                                "vmg_loss": round(vmg_loss, 2)
                            }
                        })

            elif not is_upwind and vmg_opts.optimal_downwind_angle:
                optimal_angle = vmg_opts.optimal_downwind_angle
                optimal_vmg = vmg_opts.downwind_vmg
                angle_deviation = current_twa - optimal_angle
                vmg_loss = optimal_vmg - current_vmg

                if abs(angle_deviation) > 8:
                    if angle_deviation > 0:
                        recommendations.append({
                            "type": "sail_lower",
                            "priority": "medium",
                            "text": f"Sail {abs(angle_deviation):.1f}° lower to optimal downwind angle. Potential VMG gain: {vmg_loss:.2f} kts.",
                            "confidence": 80,
                            "reasoning": f"Current TWA: {current_twa:.1f}°, Optimal: {optimal_angle:.1f}°",
                            "context": {
                                "current_twa": round(current_twa, 1),
                                "optimal_twa": round(optimal_angle, 1),
                                "angle_deviation": round(angle_deviation, 1),
                                "vmg_loss": round(vmg_loss, 2)
                            }
                        })
                    else:
                        recommendations.append({
                            "type": "sail_higher",
                            "priority": "medium",
                            "text": f"Sail {abs(angle_deviation):.1f}° higher to optimal downwind angle. Potential VMG gain: {vmg_loss:.2f} kts.",
                            "confidence": 80,
                            "reasoning": f"Current TWA: {current_twa:.1f}°, Optimal: {optimal_angle:.1f}°",
                            "context": {
                                "current_twa": round(current_twa, 1),
                                "optimal_twa": round(optimal_angle, 1),
                                "angle_deviation": round(angle_deviation, 1),
                                "vmg_loss": round(vmg_loss, 2)
                            }
                        })

        # ====================
        # 2. SPEED ANALYSIS
        # ====================
        # Check if speed is significantly below baseline
        baselines = db.query(PerformanceBaseline).filter(
            PerformanceBaseline.boat_id == boat_id,
            PerformanceBaseline.tws_min <= current_tws,
            PerformanceBaseline.tws_max > current_tws,
            PerformanceBaseline.twa_min <= current_twa,
            PerformanceBaseline.twa_max > current_twa
        ).first()

        if baselines and baselines.sample_count >= 20:
            expected_sog = baselines.avg_sog
            std_sog = baselines.std_sog
            speed_deficit = expected_sog - current_sog

            if std_sog > 0:
                z_score = speed_deficit / std_sog

                if z_score > 1.5:  # More than 1.5 std deviations slow
                    recommendations.append({
                        "type": "speed_mode",
                        "priority": "high" if z_score > 2.5 else "medium",
                        "text": f"You're sailing {speed_deficit:.2f} kts slower than expected. Focus on boatspeed - check sail trim, weight distribution, and steering.",
                        "confidence": 75,
                        "reasoning": f"Expected {expected_sog:.2f} kts, actual {current_sog:.2f} kts ({z_score:.1f}σ below normal)",
                        "context": {
                            "expected_sog": round(expected_sog, 2),
                            "actual_sog": round(current_sog, 2),
                            "speed_deficit": round(speed_deficit, 2),
                            "z_score": round(z_score, 2)
                        }
                    })

        # ====================
        # 3. WIND SHIFT DETECTION
        # ====================
        if len(recent_points) >= 30:
            # Get wind directions over last 5 minutes
            wind_samples = []
            for pt in recent_points[:30]:
                if pt.tws and pt.twa and pt.cog:
                    # Calculate true wind direction
                    twd = (pt.cog + pt.twa) % 360
                    wind_samples.append(twd)

            if len(wind_samples) >= 20:
                # Calculate wind shift
                recent_twd = sum(wind_samples[:10]) / 10  # Last minute
                earlier_twd = sum(wind_samples[10:20]) / 10  # 1-2 minutes ago

                # Calculate shift (accounting for 360° wrap)
                shift = recent_twd - earlier_twd
                if shift > 180:
                    shift -= 360
                elif shift < -180:
                    shift += 360

                if abs(shift) > 10:
                    if shift > 0:
                        # Wind has shifted right (clock)
                        if is_upwind:
                            # On port tack, right shift is a header
                            # On starboard tack, right shift is a lift
                            recommendations.append({
                                "type": "wind_shift_detected",
                                "priority": "high",
                                "text": f"Wind has shifted right {abs(shift):.1f}°. If on port tack, you're headed - consider tacking. If on starboard, you're lifted - good!",
                                "confidence": 70,
                                "reasoning": f"Wind direction changed from {earlier_twd:.0f}° to {recent_twd:.0f}° over last 2 minutes",
                                "context": {
                                    "shift_degrees": round(shift, 1),
                                    "direction": "right",
                                    "earlier_twd": round(earlier_twd, 0),
                                    "recent_twd": round(recent_twd, 0)
                                }
                            })
                    else:
                        # Wind has shifted left (counter)
                        recommendations.append({
                            "type": "wind_shift_detected",
                            "priority": "high",
                            "text": f"Wind has shifted left {abs(shift):.1f}°. If on starboard tack, you're headed - consider tacking. If on port, you're lifted - good!",
                            "confidence": 70,
                            "reasoning": f"Wind direction changed from {earlier_twd:.0f}° to {recent_twd:.0f}° over last 2 minutes",
                            "context": {
                                "shift_degrees": round(shift, 1),
                                "direction": "left",
                                "earlier_twd": round(earlier_twd, 0),
                                "recent_twd": round(recent_twd, 0)
                            }
                        })

        # ====================
        # 4. MANEUVER ANALYSIS
        # ====================
        # Check recent maneuvers
        recent_maneuvers = db.query(Maneuver).filter(
            and_(
                Maneuver.session_id == session_id,
                Maneuver.start_ts >= analysis_window
            )
        ).order_by(Maneuver.start_ts.desc()).all()

        if recent_maneuvers:
            last_maneuver = recent_maneuvers[0]
            time_since_maneuver = (current_time - last_maneuver.end_ts).total_seconds()

            # If just tacked (< 60 seconds ago), don't recommend another tack
            if time_since_maneuver < 60 and last_maneuver.maneuver_type == 'tack':
                # Check if the tack was poor quality
                if last_maneuver.score_0_100 < 60:
                    recommendations.append({
                        "type": "maneuver_review",
                        "priority": "low",
                        "text": f"Last tack scored {last_maneuver.score_0_100}/100. Try to maintain speed through the tack - lost {last_maneuver.speed_loss_kn:.2f} kts.",
                        "confidence": 90,
                        "reasoning": f"Tack took {last_maneuver.time_through_sec:.1f}s, speed dropped from {last_maneuver.entry_sog_kn:.2f} to {last_maneuver.min_sog_kn:.2f} kts",
                        "context": {
                            "maneuver_type": last_maneuver.maneuver_type,
                            "score": last_maneuver.score_0_100,
                            "time_through": round(last_maneuver.time_through_sec, 1),
                            "speed_loss": round(last_maneuver.speed_loss_kn, 2)
                        }
                    })

        # ====================
        # 5. SAVE RECOMMENDATIONS
        # ====================
        saved_recommendations = []
        for rec in recommendations:
            coaching_rec = CoachingRecommendation(
                session_id=session_id,
                ts=current_time,
                lat=current_point.lat,
                lon=current_point.lon,
                recommendation_type=rec["type"],
                priority=rec["priority"],
                recommendation_text=rec["text"],
                confidence_score=rec["confidence"],
                context_data=rec["context"],
                reasoning=rec["reasoning"]
            )
            db.add(coaching_rec)
            saved_recommendations.append({
                "type": rec["type"],
                "priority": rec["priority"],
                "text": rec["text"],
                "confidence": rec["confidence"],
                "reasoning": rec["reasoning"]
            })

        db.commit()

        return {
            "session_id": session_id,
            "analyzed_at": current_time.isoformat(),
            "current_conditions": {
                "sog": round(current_sog, 2),
                "tws": round(current_tws, 1),
                "twa": round(current_twa, 1),
                "vmg": round(current_vmg, 2),
                "sailing_mode": "upwind" if is_upwind else "downwind"
            },
            "recommendations_count": len(recommendations),
            "recommendations": saved_recommendations
        }

    finally:
        db.close()


@router.get("/coaching/session/{session_id}")
def get_session_coaching(session_id: int, limit: int = 50):
    """Get coaching recommendations for a session."""
    db = SessionLocal()
    try:
        recommendations = db.query(CoachingRecommendation).filter(
            CoachingRecommendation.session_id == session_id
        ).order_by(CoachingRecommendation.ts.desc()).limit(limit).all()

        return {
            "session_id": session_id,
            "total_recommendations": len(recommendations),
            "recommendations": [{
                "id": rec.id,
                "ts": rec.ts.isoformat(),
                "type": rec.recommendation_type,
                "priority": rec.priority,
                "text": rec.recommendation_text,
                "confidence": rec.confidence_score,
                "reasoning": rec.reasoning,
                "context": rec.context_data,
                "was_followed": rec.was_followed,
                "dismissed": rec.dismissed == 1
            } for rec in recommendations]
        }

    finally:
        db.close()


@router.post("/coaching/dismiss/{recommendation_id}")
def dismiss_recommendation(recommendation_id: int):
    """Mark a recommendation as dismissed."""
    db = SessionLocal()
    try:
        rec = db.query(CoachingRecommendation).filter(
            CoachingRecommendation.id == recommendation_id
        ).first()

        if not rec:
            return {"error": "Recommendation not found"}

        rec.dismissed = 1
        db.commit()

        return {"success": True, "recommendation_id": recommendation_id}

    finally:
        db.close()


@router.post("/coaching/feedback/{recommendation_id}")
def provide_feedback(recommendation_id: int, followed: bool, outcome_data: Optional[Dict[str, Any]] = None):
    """Provide feedback on whether a recommendation was followed and its outcome."""
    db = SessionLocal()
    try:
        rec = db.query(CoachingRecommendation).filter(
            CoachingRecommendation.id == recommendation_id
        ).first()

        if not rec:
            return {"error": "Recommendation not found"}

        rec.was_followed = 1 if followed else 0
        if outcome_data:
            rec.outcome_data = outcome_data

        db.commit()

        return {
            "success": True,
            "recommendation_id": recommendation_id,
            "followed": followed
        }

    finally:
        db.close()


# ===============================
# WIND SHIFT PATTERN RECOGNITION
# ===============================

def calculate_twd(cog: float, twa: float) -> float:
    """Calculate true wind direction from COG and TWA."""
    return (cog + twa) % 360


def normalize_angle_difference(angle1: float, angle2: float) -> float:
    """Calculate the smallest angle difference accounting for 360° wrap."""
    diff = angle2 - angle1
    if diff > 180:
        diff -= 360
    elif diff < -180:
        diff += 360
    return diff


@router.post("/wind/detect-shifts/{session_id}")
def detect_wind_shifts(session_id: int, min_shift_deg: float = 8.0, window_minutes: int = 3):
    """
    Detect wind shifts in a session using sliding window analysis.

    Parameters:
    - min_shift_deg: Minimum shift magnitude to detect (default 8°)
    - window_minutes: Window size for detecting shifts (default 3 minutes)
    """
    db = SessionLocal()
    try:
        # Get all track points with wind data
        points = db.query(TrackPoint).filter(
            and_(
                TrackPoint.session_id == session_id,
                TrackPoint.tws.isnot(None),
                TrackPoint.twa.isnot(None),
                TrackPoint.cog.isnot(None)
            )
        ).order_by(TrackPoint.ts).all()

        if len(points) < 20:
            return {"error": "Insufficient data for wind shift analysis"}

        # Calculate true wind direction for all points
        twd_data = []
        for pt in points:
            twd = calculate_twd(pt.cog, pt.twa)
            twd_data.append({
                'ts': pt.ts,
                'twd': twd,
                'tws': pt.tws
            })

        # Detect shifts using sliding window
        shifts_detected = []
        window_seconds = window_minutes * 60

        for i in range(len(twd_data) - 1):
            current_point = twd_data[i]
            current_ts = current_point['ts']

            # Get points in the window before and after
            before_window = [p for p in twd_data[:i+1]
                           if (current_ts - p['ts']).total_seconds() <= window_seconds]
            after_start_idx = i + 1
            after_end_ts = current_ts + timedelta(seconds=window_seconds)
            after_window = [p for p in twd_data[after_start_idx:]
                          if p['ts'] <= after_end_ts]

            if len(before_window) < 5 or len(after_window) < 5:
                continue

            # Calculate average TWD before and after
            avg_twd_before = sum(p['twd'] for p in before_window) / len(before_window)
            avg_tws_before = sum(p['tws'] for p in before_window) / len(before_window)
            avg_twd_after = sum(p['twd'] for p in after_window) / len(after_window)
            avg_tws_after = sum(p['tws'] for p in after_window) / len(after_window)

            # Calculate shift
            shift = normalize_angle_difference(avg_twd_before, avg_twd_after)

            if abs(shift) >= min_shift_deg:
                # Check if this is a new shift (not too close to previous)
                is_new_shift = True
                for prev_shift in shifts_detected:
                    time_diff = (current_ts - prev_shift['start_ts']).total_seconds()
                    if time_diff < window_seconds:
                        is_new_shift = False
                        break

                if is_new_shift:
                    shifts_detected.append({
                        'start_ts': current_ts,
                        'end_ts': after_window[-1]['ts'] if after_window else current_ts,
                        'shift_magnitude': abs(shift),
                        'shift_direction': 'right' if shift > 0 else 'left',
                        'twd_before': avg_twd_before,
                        'twd_after': avg_twd_after,
                        'avg_tws_before': avg_tws_before,
                        'avg_tws_after': avg_tws_after
                    })

        # Classify each shift as persistent, oscillating, or transient
        for i, shift in enumerate(shifts_detected):
            # Look ahead to see if the shift reverses
            is_persistent = True
            is_oscillating = False

            for j in range(i + 1, len(shifts_detected)):
                next_shift = shifts_detected[j]
                time_between = (next_shift['start_ts'] - shift['start_ts']).total_seconds() / 60

                # If there's a reverse shift within 15 minutes, it might be oscillating
                if time_between < 15:
                    if shift['shift_direction'] != next_shift['shift_direction']:
                        is_oscillating = True
                        is_persistent = False
                        shift['oscillation_period'] = time_between
                        break
                else:
                    break

            # Classify
            if is_oscillating:
                shift['shift_type'] = 'oscillating'
                shift['confidence'] = 0.8
            elif is_persistent:
                shift['shift_type'] = 'persistent'
                shift['confidence'] = 0.9
            else:
                shift['shift_type'] = 'transient'
                shift['confidence'] = 0.6

        # Save shifts to database
        for shift in shifts_detected:
            wind_shift = WindShift(
                session_id=session_id,
                start_ts=shift['start_ts'],
                end_ts=shift['end_ts'],
                shift_magnitude=shift['shift_magnitude'],
                shift_direction=shift['shift_direction'],
                shift_type=shift['shift_type'],
                confidence=shift['confidence'],
                avg_tws_before=shift['avg_tws_before'],
                avg_tws_after=shift['avg_tws_after'],
                twd_before=shift['twd_before'],
                twd_after=shift['twd_after'],
                oscillation_period=shift.get('oscillation_period'),
                pattern_metadata={}
            )
            db.add(wind_shift)

        db.commit()

        return {
            "session_id": session_id,
            "total_shifts_detected": len(shifts_detected),
            "shifts": [{
                "start_ts": s['start_ts'].isoformat(),
                "magnitude": round(s['shift_magnitude'], 1),
                "direction": s['shift_direction'],
                "type": s['shift_type'],
                "confidence": round(s['confidence'], 2)
            } for s in shifts_detected]
        }

    finally:
        db.close()


@router.post("/wind/analyze-pattern/{session_id}")
def analyze_wind_pattern(session_id: int):
    """
    Analyze overall wind pattern for a session using ML techniques.
    Classifies as persistent, oscillating, unstable, or stable.
    """
    db = SessionLocal()
    try:
        # Get all wind shifts for this session
        shifts = db.query(WindShift).filter(
            WindShift.session_id == session_id
        ).order_by(WindShift.start_ts).all()

        if len(shifts) == 0:
            # No shifts detected - wind is stable
            pattern = WindPattern(
                session_id=session_id,
                analyzed_at=datetime.utcnow(),
                dominant_pattern='stable',
                pattern_strength=1.0,
                is_oscillating=0,
                total_shifts_detected=0,
                avg_shift_magnitude=0.0,
                wind_stability_score=100.0,
                analysis_metadata={}
            )
            db.add(pattern)
            db.commit()

            return {
                "session_id": session_id,
                "dominant_pattern": "stable",
                "pattern_strength": 1.0,
                "total_shifts": 0,
                "wind_stability_score": 100.0
            }

        # Analyze shift directions
        right_shifts = [s for s in shifts if s.shift_direction == 'right']
        left_shifts = [s for s in shifts if s.shift_direction == 'left']
        oscillating_shifts = [s for s in shifts if s.shift_type == 'oscillating']

        # Calculate metrics
        total_shifts = len(shifts)
        avg_magnitude = sum(s.shift_magnitude for s in shifts) / total_shifts

        # Determine dominant pattern
        dominant_pattern = 'unstable'
        pattern_strength = 0.5

        if len(oscillating_shifts) > total_shifts * 0.5:
            # More than half are oscillating
            dominant_pattern = 'oscillating'
            pattern_strength = len(oscillating_shifts) / total_shifts
            is_oscillating = 1

            # Calculate average oscillation period
            oscillating_with_period = [s for s in oscillating_shifts if s.oscillation_period]
            if oscillating_with_period:
                avg_period = sum(s.oscillation_period for s in oscillating_with_period) / len(oscillating_with_period)
                avg_amplitude = sum(s.shift_magnitude for s in oscillating_shifts) / len(oscillating_shifts)
            else:
                avg_period = None
                avg_amplitude = None
        else:
            is_oscillating = 0
            avg_period = None
            avg_amplitude = None

            # Check for persistent trend
            if len(right_shifts) > len(left_shifts) * 2:
                dominant_pattern = 'persistent_right'
                pattern_strength = len(right_shifts) / total_shifts
            elif len(left_shifts) > len(right_shifts) * 2:
                dominant_pattern = 'persistent_left'
                pattern_strength = len(left_shifts) / total_shifts

        # Calculate wind stability score (0-100, higher = more stable)
        # Based on number of shifts and their magnitude
        stability_score = max(0, 100 - (total_shifts * 5) - (avg_magnitude * 2))

        # Predict next shift
        next_shift_prediction = None
        prediction_confidence = None

        if dominant_pattern == 'oscillating' and avg_period:
            # For oscillating winds, predict based on last shift
            last_shift = shifts[-1]
            next_shift_prediction = 'left' if last_shift.shift_direction == 'right' else 'right'
            prediction_confidence = pattern_strength * 0.7
        elif dominant_pattern == 'persistent_right':
            next_shift_prediction = 'right'
            prediction_confidence = pattern_strength * 0.6
        elif dominant_pattern == 'persistent_left':
            next_shift_prediction = 'left'
            prediction_confidence = pattern_strength * 0.6
        else:
            next_shift_prediction = 'stable'
            prediction_confidence = 0.5

        # Save pattern analysis
        pattern = WindPattern(
            session_id=session_id,
            analyzed_at=datetime.utcnow(),
            dominant_pattern=dominant_pattern,
            pattern_strength=pattern_strength,
            is_oscillating=is_oscillating,
            avg_oscillation_period=avg_period,
            oscillation_amplitude=avg_amplitude,
            next_shift_prediction=next_shift_prediction,
            prediction_confidence=prediction_confidence,
            total_shifts_detected=total_shifts,
            avg_shift_magnitude=avg_magnitude,
            wind_stability_score=stability_score,
            analysis_metadata={
                'right_shifts': len(right_shifts),
                'left_shifts': len(left_shifts),
                'oscillating_shifts': len(oscillating_shifts)
            }
        )
        db.add(pattern)
        db.commit()

        return {
            "session_id": session_id,
            "dominant_pattern": dominant_pattern,
            "pattern_strength": round(pattern_strength, 2),
            "is_oscillating": is_oscillating == 1,
            "avg_oscillation_period": round(avg_period, 1) if avg_period else None,
            "oscillation_amplitude": round(avg_amplitude, 1) if avg_amplitude else None,
            "next_shift_prediction": next_shift_prediction,
            "prediction_confidence": round(prediction_confidence, 2) if prediction_confidence else None,
            "total_shifts": total_shifts,
            "avg_shift_magnitude": round(avg_magnitude, 1),
            "wind_stability_score": round(stability_score, 1),
            "breakdown": {
                "right_shifts": len(right_shifts),
                "left_shifts": len(left_shifts),
                "oscillating_shifts": len(oscillating_shifts)
            }
        }

    finally:
        db.close()


@router.get("/wind/shifts/{session_id}")
def get_wind_shifts(session_id: int):
    """Get all detected wind shifts for a session."""
    db = SessionLocal()
    try:
        shifts = db.query(WindShift).filter(
            WindShift.session_id == session_id
        ).order_by(WindShift.start_ts).all()

        return {
            "session_id": session_id,
            "total_shifts": len(shifts),
            "shifts": [{
                "id": s.id,
                "start_ts": s.start_ts.isoformat(),
                "end_ts": s.end_ts.isoformat(),
                "magnitude": round(s.shift_magnitude, 1),
                "direction": s.shift_direction,
                "type": s.shift_type,
                "confidence": round(s.confidence, 2),
                "twd_before": round(s.twd_before, 0),
                "twd_after": round(s.twd_after, 0),
                "avg_tws_before": round(s.avg_tws_before, 1),
                "avg_tws_after": round(s.avg_tws_after, 1)
            } for s in shifts]
        }

    finally:
        db.close()


@router.get("/wind/pattern/{session_id}")
def get_wind_pattern(session_id: int):
    """Get wind pattern analysis for a session."""
    db = SessionLocal()
    try:
        pattern = db.query(WindPattern).filter(
            WindPattern.session_id == session_id
        ).order_by(WindPattern.analyzed_at.desc()).first()

        if not pattern:
            return {"error": "No pattern analysis found. Run /wind/analyze-pattern first."}

        return {
            "session_id": session_id,
            "analyzed_at": pattern.analyzed_at.isoformat(),
            "dominant_pattern": pattern.dominant_pattern,
            "pattern_strength": round(pattern.pattern_strength, 2),
            "is_oscillating": pattern.is_oscillating == 1,
            "avg_oscillation_period": round(pattern.avg_oscillation_period, 1) if pattern.avg_oscillation_period else None,
            "oscillation_amplitude": round(pattern.oscillation_amplitude, 1) if pattern.oscillation_amplitude else None,
            "next_shift_prediction": pattern.next_shift_prediction,
            "prediction_confidence": round(pattern.prediction_confidence, 2) if pattern.prediction_confidence else None,
            "total_shifts_detected": pattern.total_shifts_detected,
            "avg_shift_magnitude": round(pattern.avg_shift_magnitude, 1),
            "wind_stability_score": round(pattern.wind_stability_score, 1)
        }

    finally:
        db.close()
