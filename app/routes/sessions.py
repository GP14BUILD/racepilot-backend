from fastapi import APIRouter
from ..db.models import SessionLocal, Session as S
from ..schemas import SessionCreate
from datetime import datetime

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

@router.get("/{session_id}")
def get_session(session_id: int):
    db = SessionLocal()
    try:
        s = db.get(S, session_id)
        if not s: return {"error": "not found"}
        return {"id": s.id, "title": s.title, "start_ts": s.start_ts, "end_ts": s.end_ts}
    finally:
        db.close()
