from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session as DbSession
from ..db.models import SessionLocal, Session as S, TrackPoint, User, Boat
from ..schemas import SessionCreate
from ..auth import get_current_user, get_db, check_session_limit
from datetime import datetime
from typing import List

router = APIRouter()

@router.post("")
def create_session(
    req: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db)
):
    """
    Create a new sailing session.
    Free tier users are limited to 5 sessions per month.
    Pro/Club subscribers have unlimited sessions.
    """
    # Check session limit for free users
    check_session_limit(current_user, db)

    # Validate boat_id exists if provided
    validated_boat_id = None
    if req.boat_id:
        boat = db.query(Boat).filter(Boat.id == req.boat_id, Boat.user_id == current_user.id).first()
        if boat:
            validated_boat_id = boat.id

    # Calculate next session number for this user
    from sqlalchemy import func
    max_session_num = db.query(func.max(S.session_number)).filter(S.user_id == current_user.id).scalar()
    next_session_num = (max_session_num or 0) + 1

    # Create session with authenticated user's ID
    try:
        s = S(
            user_id=current_user.id,
            session_number=next_session_num,
            club_id=current_user.club_id,
            boat_id=validated_boat_id,
            title=req.title,
            start_ts=req.start_ts
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return {"id": s.id, "session_id": s.id}
    except Exception as e:
        db.rollback()
        print(f"❌ Session creation error: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

@router.get("")
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db)
):
    """Get all sessions for the current user"""
    sessions = db.query(S).filter(S.user_id == current_user.id).order_by(S.start_ts.desc()).all()
    return [{
        "id": s.id,
        "session_number": s.session_number,
        "user_id": s.user_id,
        "boat_id": s.boat_id,
        "title": s.title,
        "start_ts": s.start_ts,
        "end_ts": s.end_ts,
        "created_at": s.start_ts
    } for s in sessions]

@router.get("/{session_id}")
def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db)
):
    s = db.get(S, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify the session belongs to the current user
    if s.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this session")

    return {"id": s.id, "session_number": s.session_number, "user_id": s.user_id, "boat_id": s.boat_id, "title": s.title, "start_ts": s.start_ts, "end_ts": s.end_ts, "created_at": s.start_ts}

@router.get("/{session_id}/points")
def get_session_points(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db)
):
    """Get all track points for a session"""
    # Verify session exists
    session = db.get(S, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify the session belongs to the current user
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this session")

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
