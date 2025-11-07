# app/routes/ai.py

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import math

from ..db.models import SessionLocal, TrackPoint  # uses your existing DB models

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


class Maneuver(BaseModel):
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
    maneuvers: List[Maneuver]
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

                maneuvers.append(
                    Maneuver(
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
                )

                i = j
                continue

            i += 1

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
