from fastapi import APIRouter, HTTPException
from ..db.models import SessionLocal, Session as S, TrackPoint
from ..schemas import SessionCreate
from datetime import datetime
from typing import List

router = APIRouter()

@router.post("")
def create_session(req: SessionCreate):
    db = SessionLocal()
    try:
        s = S(user_id=req.user_id, boat_id=req.boat_id, title=req.title, start_ts=req.start_ts)
        db.add(s); db.commit(); db.refresh(s)
        return {"id": s.id}
    finally:
        db.close()

@router.get("")
def list_sessions():
    """Get all sessions"""
    db = SessionLocal()
    try:
        sessions = db.query(S).order_by(S.start_ts.desc()).all()
        return [{
            "id": s.id,
            "user_id": s.user_id,
            "boat_id": s.boat_id,
            "title": s.title,
            "start_ts": s.start_ts,
            "end_ts": s.end_ts,
            "created_at": s.start_ts
        } for s in sessions]
    finally:
        db.close()

@router.get("/{session_id}")
def get_session(session_id: int):
    db = SessionLocal()
    try:
        s = db.get(S, session_id)
        if not s: return {"error": "not found"}
        return {"id": s.id, "user_id": s.user_id, "boat_id": s.boat_id, "title": s.title, "start_ts": s.start_ts, "end_ts": s.end_ts, "created_at": s.start_ts}
    finally:
        db.close()

@router.get("/{session_id}/points")
def get_session_points(session_id: int):
    """Get all track points for a session"""
    db = SessionLocal()
    try:
        # Verify session exists
        session = db.get(S, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get all track points for this session
        points = (
            db.query(TrackPoint)
            .filter(TrackPoint.session_id == session_id)
            .order_by(TrackPoint.ts.asc())
            .all()
        )

        if not points:
            raise HTTPException(status_code=404, detail="No track points found for this session")

        return [{
            "id": p.id,
            "session_id": p.session_id,
            "ts": p.ts,
            "lat": p.lat,
            "lon": p.lon,
            "sog": p.sog,
            "cog": p.cog,
            "awa": p.awa,
            "aws": p.aws,
            "hdg": p.hdg,
            "tws": p.tws,
            "twa": p.twa,
        } for p in points]
    finally:
        db.close()
