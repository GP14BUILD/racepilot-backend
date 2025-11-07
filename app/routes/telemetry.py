from fastapi import APIRouter
from ..db.models import SessionLocal, TrackPoint
from ..schemas import TelemetryIngest
router = APIRouter()

@router.post("/ingest")
def ingest(req: TelemetryIngest):
    db = SessionLocal()
    try:
        for p in req.points:
            tp = TrackPoint(
                session_id=req.session_id, ts=p.ts, lat=p.lat, lon=p.lon,
                sog=p.sog, cog=p.cog, awa=p.awa, aws=p.aws, hdg=p.hdg,
                tws=p.tws, twa=p.twa
            )
            db.add(tp)
        db.commit()
        return {"ingested": len(req.points)}
    finally:
        db.close()
