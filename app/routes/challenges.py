"""
Ghost Boat Racing - Challenge system for RacePilot.
Allows users to create and compete against GPS tracks.
"""

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from pydantic import BaseModel

from app.db.models import User, Challenge, ChallengeAttempt, Session as RaceSession, TrackPoint
from app.auth import get_db, get_current_user

router = APIRouter(prefix="/challenges", tags=["Challenges"])


# Pydantic models
class CreateChallengeRequest(BaseModel):
    session_id: int
    title: str
    description: Optional[str] = None
    is_public: bool = False
    expires_in_days: Optional[int] = None
    boat_class: Optional[str] = None


class ChallengeResponse(BaseModel):
    id: int
    creator_id: int
    creator_name: str
    session_id: int
    title: str
    description: Optional[str]
    difficulty: str
    is_public: bool
    expires_at: Optional[datetime]
    boat_class: Optional[str]
    created_at: datetime
    attempt_count: int
    best_time: Optional[float]
    can_attempt: bool  # Whether current user can attempt

    class Config:
        from_attributes = True


class AttemptResponse(BaseModel):
    id: int
    challenge_id: int
    user_id: int
    user_name: str
    session_id: int
    time_difference: float
    result: str
    submitted_at: datetime
    xp_earned: int

    class Config:
        from_attributes = True


class SubmitAttemptRequest(BaseModel):
    session_id: int


# Helper functions
def calculate_difficulty(session: RaceSession, db: Session) -> str:
    """Calculate challenge difficulty based on session metrics"""
    # Get track points to calculate average speed
    points = db.query(TrackPoint).filter(TrackPoint.session_id == session.id).all()

    if not points:
        return 'medium'

    avg_speed = sum(p.sog for p in points) / len(points)

    if avg_speed < 5:
        return 'easy'
    elif avg_speed < 8:
        return 'medium'
    else:
        return 'hard'


def calculate_time_difference(ghost_session_id: int, attempt_session_id: int, db: Session) -> tuple:
    """
    Calculate time difference between ghost and attempt sessions.
    Returns (time_difference, max_lead, max_deficit, result)
    """
    # Get track points for both sessions
    ghost_points = db.query(TrackPoint).filter(
        TrackPoint.session_id == ghost_session_id
    ).order_by(TrackPoint.ts).all()

    attempt_points = db.query(TrackPoint).filter(
        TrackPoint.session_id == attempt_session_id
    ).order_by(TrackPoint.ts).all()

    if not ghost_points or not attempt_points:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sessions must have GPS data"
        )

    # Calculate total time for each session
    ghost_duration = (ghost_points[-1].ts - ghost_points[0].ts).total_seconds()
    attempt_duration = (attempt_points[-1].ts - attempt_points[0].ts).total_seconds()

    time_difference = attempt_duration - ghost_duration

    # For now, simplified calculation
    # TODO: Implement proper point-by-point comparison for max_lead/deficit
    max_lead = abs(min(0, time_difference))
    max_deficit = max(0, time_difference)

    # Determine result
    if time_difference < -2:  # Beat by more than 2 seconds
        result = 'won'
    elif time_difference > 2:  # Lost by more than 2 seconds
        result = 'lost'
    else:
        result = 'tie'

    return time_difference, max_lead, max_deficit, result


# Endpoints
@router.post("/create", response_model=ChallengeResponse, status_code=status.HTTP_201_CREATED)
def create_challenge(
    request: CreateChallengeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new ghost boat challenge from a session.
    """
    # Verify session exists and belongs to user
    session = db.query(RaceSession).filter(
        RaceSession.id == request.session_id,
        RaceSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or doesn't belong to you"
        )

    # Check if session has GPS data
    point_count = db.query(TrackPoint).filter(
        TrackPoint.session_id == request.session_id
    ).count()

    if point_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session must have GPS data to create a challenge"
        )

    # Calculate difficulty
    difficulty = calculate_difficulty(session, db)

    # Calculate expiration
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)

    # Create challenge
    challenge = Challenge(
        creator_id=current_user.id,
        session_id=request.session_id,
        club_id=current_user.club_id,
        title=request.title,
        description=request.description,
        difficulty=difficulty,
        is_public=request.is_public,
        expires_at=expires_at,
        boat_class=request.boat_class,
        created_at=datetime.utcnow()
    )

    db.add(challenge)
    db.commit()
    db.refresh(challenge)

    return ChallengeResponse(
        id=challenge.id,
        creator_id=challenge.creator_id,
        creator_name=current_user.name,
        session_id=challenge.session_id,
        title=challenge.title,
        description=challenge.description,
        difficulty=challenge.difficulty,
        is_public=challenge.is_public,
        expires_at=challenge.expires_at,
        boat_class=challenge.boat_class,
        created_at=challenge.created_at,
        attempt_count=0,
        best_time=None,
        can_attempt=False  # Can't attempt own challenge
    )


@router.get("/", response_model=List[ChallengeResponse])
def list_challenges(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    difficulty: Optional[str] = None,
    boat_class: Optional[str] = None,
    public_only: bool = False
):
    """
    List available challenges.
    Shows public challenges + challenges from your club.
    """
    query = db.query(Challenge)

    # Filter expired challenges
    query = query.filter(
        or_(
            Challenge.expires_at == None,
            Challenge.expires_at > datetime.utcnow()
        )
    )

    # Filter by visibility
    if public_only:
        query = query.filter(Challenge.is_public == True)
    else:
        # Show public challenges OR challenges from my club
        query = query.filter(
            or_(
                Challenge.is_public == True,
                Challenge.club_id == current_user.club_id
            )
        )

    # Apply filters
    if difficulty:
        query = query.filter(Challenge.difficulty == difficulty)
    if boat_class:
        query = query.filter(Challenge.boat_class == boat_class)

    # Order by created date
    challenges = query.order_by(Challenge.created_at.desc()).all()

    # Build response with creator names
    result = []
    for challenge in challenges:
        creator = db.query(User).filter(User.id == challenge.creator_id).first()
        can_attempt = challenge.creator_id != current_user.id

        result.append(ChallengeResponse(
            id=challenge.id,
            creator_id=challenge.creator_id,
            creator_name=creator.name if creator else "Unknown",
            session_id=challenge.session_id,
            title=challenge.title,
            description=challenge.description,
            difficulty=challenge.difficulty,
            is_public=challenge.is_public,
            expires_at=challenge.expires_at,
            boat_class=challenge.boat_class,
            created_at=challenge.created_at,
            attempt_count=challenge.attempt_count,
            best_time=challenge.best_time,
            can_attempt=can_attempt
        ))

    return result


@router.get("/{challenge_id}", response_model=ChallengeResponse)
def get_challenge(
    challenge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific challenge"""
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()

    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Challenge not found"
        )

    # Check permissions
    if not challenge.is_public and challenge.club_id != current_user.club_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this challenge"
        )

    creator = db.query(User).filter(User.id == challenge.creator_id).first()
    can_attempt = challenge.creator_id != current_user.id

    return ChallengeResponse(
        id=challenge.id,
        creator_id=challenge.creator_id,
        creator_name=creator.name if creator else "Unknown",
        session_id=challenge.session_id,
        title=challenge.title,
        description=challenge.description,
        difficulty=challenge.difficulty,
        is_public=challenge.is_public,
        expires_at=challenge.expires_at,
        boat_class=challenge.boat_class,
        created_at=challenge.created_at,
        attempt_count=challenge.attempt_count,
        best_time=challenge.best_time,
        can_attempt=can_attempt
    )


@router.get("/{challenge_id}/leaderboard", response_model=List[AttemptResponse])
def get_challenge_leaderboard(
    challenge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get leaderboard for a challenge"""
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()

    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Challenge not found"
        )

    # Get all attempts, ordered by time_difference (fastest first)
    attempts = db.query(ChallengeAttempt).filter(
        ChallengeAttempt.challenge_id == challenge_id
    ).order_by(ChallengeAttempt.time_difference).all()

    result = []
    for attempt in attempts:
        user = db.query(User).filter(User.id == attempt.user_id).first()
        result.append(AttemptResponse(
            id=attempt.id,
            challenge_id=attempt.challenge_id,
            user_id=attempt.user_id,
            user_name=user.name if user else "Unknown",
            session_id=attempt.session_id,
            time_difference=attempt.time_difference,
            result=attempt.result,
            submitted_at=attempt.submitted_at,
            xp_earned=attempt.xp_earned
        ))

    return result


@router.post("/{challenge_id}/submit", response_model=AttemptResponse, status_code=status.HTTP_201_CREATED)
def submit_attempt(
    challenge_id: int,
    request: SubmitAttemptRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit an attempt for a challenge"""
    # Get challenge
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()

    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Challenge not found"
        )

    # Check if challenge is expired
    if challenge.expires_at and challenge.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Challenge has expired"
        )

    # Can't attempt own challenge
    if challenge.creator_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot attempt your own challenge"
        )

    # Verify session exists and belongs to user
    attempt_session = db.query(RaceSession).filter(
        RaceSession.id == request.session_id,
        RaceSession.user_id == current_user.id
    ).first()

    if not attempt_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or doesn't belong to you"
        )

    # Calculate results
    try:
        time_diff, max_lead, max_deficit, result = calculate_time_difference(
            challenge.session_id,
            request.session_id,
            db
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error calculating results: {str(e)}"
        )

    # Calculate XP reward
    xp_earned = 50  # Base XP
    if result == 'won':
        xp_earned += 150
    elif result == 'tie':
        xp_earned += 75

    # Create attempt
    attempt = ChallengeAttempt(
        challenge_id=challenge_id,
        user_id=current_user.id,
        session_id=request.session_id,
        time_difference=time_diff,
        max_lead=max_lead,
        max_deficit=max_deficit,
        result=result,
        submitted_at=datetime.utcnow(),
        xp_earned=xp_earned
    )

    db.add(attempt)

    # Update challenge stats
    challenge.attempt_count += 1
    if challenge.best_time is None or abs(time_diff) < abs(challenge.best_time):
        challenge.best_time = time_diff

    db.commit()
    db.refresh(attempt)

    return AttemptResponse(
        id=attempt.id,
        challenge_id=attempt.challenge_id,
        user_id=attempt.user_id,
        user_name=current_user.name,
        session_id=attempt.session_id,
        time_difference=attempt.time_difference,
        result=attempt.result,
        submitted_at=attempt.submitted_at,
        xp_earned=attempt.xp_earned
    )


@router.delete("/{challenge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_challenge(
    challenge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a challenge (only creator or admin)"""
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()

    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Challenge not found"
        )

    # Check permissions
    if challenge.creator_id != current_user.id and current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this challenge"
        )

    # Delete all attempts first
    db.query(ChallengeAttempt).filter(ChallengeAttempt.challenge_id == challenge_id).delete()

    # Delete challenge
    db.delete(challenge)
    db.commit()

    return None
