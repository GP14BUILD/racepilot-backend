from fastapi import APIRouter
from ..db.models import SessionLocal, TrackPoint, Polar
from ..schemas import StartLine, TTLRequest, AnalyticsRequest
from ..services.ai import bearing_and_distance, start_line_bias, time_to_line, layline_recommendation, _interp_polar

router = APIRouter()

@router.post("/start-line/bias")
def compute_bias(req: StartLine):
    pin_brg, _ = bearing_and_distance(req.pin_lat, req.pin_lon, req.com_lat, req.com_lon)
    com_brg, _ = bearing_and_distance(req.com_lat, req.com_lon, req.pin_lat, req.pin_lon)
    bias = start_line_bias(pin_brg, com_brg, req.twd)
    best = "PIN" if bias > 0 else "COMMITTEE"
    return {"bias_deg": bias, "best_end": best}

@router.post("/start-line/ttl")
def compute_ttl(req: TTLRequest):
    ttl = time_to_line(req.distance_m, req.sog)
    return {"time_to_line_sec": ttl}

@router.post("/laylines")
def laylines(req: AnalyticsRequest):
    db = SessionLocal()
    try:
        p = db.get(Polar, req.polar_id)
        if not p: return {"error": "polar not found"}
        # Use last point of the session for demo
        tp = db.query(TrackPoint).filter(TrackPoint.session_id==req.session_id).order_by(TrackPoint.ts.desc()).first()
        if not tp: return {"error": "no telemetry"}
        res = layline_recommendation(tp.lat, tp.lon, req.mark_lat, req.mark_lon, req.twd, p.data_json, req.tws, tp.twa if tp.twa is not None else 45.0)
        return res
    finally:
        db.close()
