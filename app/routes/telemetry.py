from fastapi import APIRouter, HTTPException
from ..db.models import SessionLocal, TrackPoint
from ..schemas import TelemetryIngest
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/ingest")
def ingest(req: TelemetryIngest):
    db = SessionLocal()
    try:
        logger.info(f"Ingesting {len(req.points)} points for session {req.session_id}")

        for p in req.points:
            tp = TrackPoint(
                session_id=req.session_id, ts=p.ts, lat=p.lat, lon=p.lon,
                sog=p.sog, cog=p.cog, awa=p.awa, aws=p.aws, hdg=p.hdg,
                tws=p.tws, twa=p.twa
            )
            db.add(tp)

        db.commit()
        logger.info(f"Successfully committed {len(req.points)} points for session {req.session_id}")
        return {"ingested": len(req.points)}
    except Exception as e:
        logger.error(f"Error ingesting telemetry: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to ingest telemetry: {str(e)}")
    finally:
        db.close()
