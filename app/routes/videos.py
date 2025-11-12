"""
Video upload and management endpoints for RacePilot.
Allows users to upload race videos and sync them with GPS sessions.
"""

import os
import shutil
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.models import User, Video, Session as RaceSession
from app.auth import get_db, get_current_user

router = APIRouter(prefix="/videos", tags=["Videos"])

# Configuration
UPLOAD_DIR = os.getenv("VIDEO_UPLOAD_DIR", "/data/videos")
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi"}

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)


# Pydantic models
class VideoResponse(BaseModel):
    id: int
    session_id: int
    user_id: int
    user_name: str
    filename: str
    file_size: int
    duration: Optional[float]
    thumbnail_url: Optional[str]
    video_url: Optional[str]
    offset_seconds: float
    title: Optional[str]
    description: Optional[str]
    is_public: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UpdateVideoRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    offset_seconds: Optional[float] = None
    is_public: Optional[bool] = None


# Helper functions
def get_file_extension(filename: str) -> str:
    """Get file extension from filename"""
    return os.path.splitext(filename)[1].lower()


def is_allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return get_file_extension(filename) in ALLOWED_EXTENSIONS


# Endpoints
@router.post("/upload", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: UploadFile = File(...),
    session_id: int = Form(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    offset_seconds: float = Form(0.0),
    is_public: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a race video and link it to a session.

    - **file**: Video file (MP4, MOV, WebM, AVI - max 500MB)
    - **session_id**: Session to link video to
    - **title**: Optional video title
    - **description**: Optional description
    - **offset_seconds**: Time offset from session start for GPS sync
    - **is_public**: Whether video is publicly viewable
    """
    # Validate file type
    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Verify session exists and belongs to user
    session = db.query(RaceSession).filter(
        RaceSession.id == session_id,
        RaceSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or doesn't belong to you"
        )

    # Generate unique filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    ext = get_file_extension(file.filename)
    unique_filename = f"{current_user.id}_{session_id}_{timestamp}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    # Save file
    try:
        with open(file_path, "wb") as buffer:
            file_size = 0
            while chunk := await file.read(1024 * 1024):  # Read 1MB at a time
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    os.remove(file_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
                    )
                buffer.write(chunk)
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save video: {str(e)}"
        )

    # Create database record
    video = Video(
        session_id=session_id,
        user_id=current_user.id,
        club_id=current_user.club_id,
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        video_url=f"/videos/{session_id}/stream",  # Will be set after creation
        title=title,
        description=description,
        offset_seconds=offset_seconds,
        is_public=is_public,
        created_at=datetime.utcnow()
    )

    db.add(video)
    db.commit()
    db.refresh(video)

    # Update video_url with actual ID
    video.video_url = f"/videos/{video.id}/stream"
    db.commit()
    db.refresh(video)

    return VideoResponse(
        id=video.id,
        session_id=video.session_id,
        user_id=video.user_id,
        user_name=current_user.name,
        filename=video.filename,
        file_size=video.file_size,
        duration=video.duration,
        thumbnail_url=video.thumbnail_url,
        video_url=video.video_url,
        offset_seconds=video.offset_seconds,
        title=video.title,
        description=video.description,
        is_public=video.is_public,
        created_at=video.created_at
    )


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get video metadata by ID"""
    video = db.query(Video).filter(Video.id == video_id).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )

    # Check permissions
    if not video.is_public and video.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this video"
        )

    user = db.query(User).filter(User.id == video.user_id).first()

    return VideoResponse(
        id=video.id,
        session_id=video.session_id,
        user_id=video.user_id,
        user_name=user.name if user else "Unknown",
        filename=video.filename,
        file_size=video.file_size,
        duration=video.duration,
        thumbnail_url=video.thumbnail_url,
        video_url=video.video_url,
        offset_seconds=video.offset_seconds,
        title=video.title,
        description=video.description,
        is_public=video.is_public,
        created_at=video.created_at
    )


@router.get("/session/{session_id}", response_model=List[VideoResponse])
def get_session_videos(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all videos for a session"""
    # Verify session exists and user has access
    session = db.query(RaceSession).filter(RaceSession.id == session_id).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    # Get videos (own videos + public videos from other users)
    videos = db.query(Video).filter(
        Video.session_id == session_id
    ).filter(
        (Video.user_id == current_user.id) | (Video.is_public == True)
    ).order_by(Video.created_at.desc()).all()

    result = []
    for video in videos:
        user = db.query(User).filter(User.id == video.user_id).first()
        result.append(VideoResponse(
            id=video.id,
            session_id=video.session_id,
            user_id=video.user_id,
            user_name=user.name if user else "Unknown",
            filename=video.filename,
            file_size=video.file_size,
            duration=video.duration,
            thumbnail_url=video.thumbnail_url,
            video_url=video.video_url,
            offset_seconds=video.offset_seconds,
            title=video.title,
            description=video.description,
            is_public=video.is_public,
            created_at=video.created_at
        ))

    return result


@router.get("/{video_id}/stream")
async def stream_video(
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stream video file"""
    video = db.query(Video).filter(Video.id == video_id).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )

    # Check permissions
    if not video.is_public and video.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this video"
        )

    if not os.path.exists(video.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found on server"
        )

    # Return video file with proper content type
    ext = get_file_extension(video.filename)
    media_type = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".avi": "video/x-msvideo"
    }.get(ext, "video/mp4")

    return FileResponse(
        video.file_path,
        media_type=media_type,
        filename=video.filename
    )


@router.put("/{video_id}", response_model=VideoResponse)
def update_video(
    video_id: int,
    request: UpdateVideoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update video metadata"""
    video = db.query(Video).filter(Video.id == video_id).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )

    # Only owner can update
    if video.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this video"
        )

    # Update fields
    if request.title is not None:
        video.title = request.title
    if request.description is not None:
        video.description = request.description
    if request.offset_seconds is not None:
        video.offset_seconds = request.offset_seconds
    if request.is_public is not None:
        video.is_public = request.is_public

    db.commit()
    db.refresh(video)

    user = db.query(User).filter(User.id == video.user_id).first()

    return VideoResponse(
        id=video.id,
        session_id=video.session_id,
        user_id=video.user_id,
        user_name=user.name if user else "Unknown",
        filename=video.filename,
        file_size=video.file_size,
        duration=video.duration,
        thumbnail_url=video.thumbnail_url,
        video_url=video.video_url,
        offset_seconds=video.offset_seconds,
        title=video.title,
        description=video.description,
        is_public=video.is_public,
        created_at=video.created_at
    )


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a video"""
    video = db.query(Video).filter(Video.id == video_id).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )

    # Only owner or admin can delete
    if video.user_id != current_user.id and current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this video"
        )

    # Delete file from disk
    if os.path.exists(video.file_path):
        try:
            os.remove(video.file_path)
        except Exception as e:
            print(f"Failed to delete video file: {e}")

    # Delete database record
    db.delete(video)
    db.commit()

    return None


@router.get("/", response_model=List[VideoResponse])
def list_my_videos(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all videos uploaded by current user"""
    videos = db.query(Video).filter(
        Video.user_id == current_user.id
    ).order_by(Video.created_at.desc()).all()

    result = []
    for video in videos:
        result.append(VideoResponse(
            id=video.id,
            session_id=video.session_id,
            user_id=video.user_id,
            user_name=current_user.name,
            filename=video.filename,
            file_size=video.file_size,
            duration=video.duration,
            thumbnail_url=video.thumbnail_url,
            video_url=video.video_url,
            offset_seconds=video.offset_seconds,
            title=video.title,
            description=video.description,
            is_public=video.is_public,
            created_at=video.created_at
        ))

    return result
