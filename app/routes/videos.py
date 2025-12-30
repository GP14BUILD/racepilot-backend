"""
Video upload and management endpoints for RacePilot.
Allows users to upload race videos and sync them with GPS sessions.
Supports both local storage and Cloudflare R2.
"""

import os
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.models import User, Video, Session as RaceSession
from app.auth import get_db, get_current_user
from app.storage import get_video_storage

router = APIRouter(prefix="/videos", tags=["Videos"])

# Configuration
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi"}


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


def get_content_type(filename: str) -> str:
    """Get content type from filename"""
    ext = get_file_extension(filename)
    return {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".avi": "video/x-msvideo"
    }.get(ext, "video/mp4")


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

    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Seek back to beginning

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # Upload to storage (local or R2)
    try:
        storage = get_video_storage()
        content_type = get_content_type(file.filename)

        storage_path, actual_file_size = storage.upload_file(
            file_obj=file.file,
            filename=file.filename,
            user_id=current_user.id,
            session_id=session_id,
            content_type=content_type
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload video: {str(e)}"
        )

    # Create database record
    video = Video(
        session_id=session_id,
        user_id=current_user.id,
        club_id=current_user.club_id,
        filename=file.filename,
        file_path=storage_path,
        file_size=actual_file_size,
        video_url=None,  # Will be set dynamically when accessed
        title=title,
        description=description,
        offset_seconds=offset_seconds,
        is_public=is_public,
        created_at=datetime.utcnow()
    )

    db.add(video)
    db.commit()
    db.refresh(video)

    # Generate video URL
    video_url = storage.get_url(storage_path)

    return VideoResponse(
        id=video.id,
        session_id=video.session_id,
        user_id=video.user_id,
        user_name=current_user.name,
        filename=video.filename,
        file_size=video.file_size,
        duration=video.duration,
        thumbnail_url=video.thumbnail_url,
        video_url=video_url,
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

    # Generate video URL dynamically
    storage = get_video_storage()
    video_url = storage.get_url(video.file_path)

    return VideoResponse(
        id=video.id,
        session_id=video.session_id,
        user_id=video.user_id,
        user_name=user.name if user else "Unknown",
        filename=video.filename,
        file_size=video.file_size,
        duration=video.duration,
        thumbnail_url=video.thumbnail_url,
        video_url=video_url,
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

    storage = get_video_storage()
    result = []

    for video in videos:
        user = db.query(User).filter(User.id == video.user_id).first()
        video_url = storage.get_url(video.file_path)

        result.append(VideoResponse(
            id=video.id,
            session_id=video.session_id,
            user_id=video.user_id,
            user_name=user.name if user else "Unknown",
            filename=video.filename,
            file_size=video.file_size,
            duration=video.duration,
            thumbnail_url=video.thumbnail_url,
            video_url=video_url,
            offset_seconds=video.offset_seconds,
            title=video.title,
            description=video.description,
            is_public=video.is_public,
            created_at=video.created_at
        ))

    return result


@router.get("/stream/{filename}")
async def stream_video_by_filename(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Stream video file by filename (legacy endpoint for local storage).
    For R2 storage, this redirects to the presigned URL.
    """
    # Find video by filename pattern
    video = db.query(Video).filter(
        Video.file_path.contains(filename)
    ).first()

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

    storage = get_video_storage()

    # For R2, redirect to presigned URL
    if storage.storage_type == "r2":
        video_url = storage.get_url(video.file_path, expires_in=3600)
        return RedirectResponse(url=video_url)

    # For local storage, stream the file
    try:
        file_path = storage.get_file_stream(video.file_path)
        content_type = get_content_type(video.filename)

        return FileResponse(
            file_path,
            media_type=content_type,
            filename=video.filename
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found on server"
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
    storage = get_video_storage()
    video_url = storage.get_url(video.file_path)

    return VideoResponse(
        id=video.id,
        session_id=video.session_id,
        user_id=video.user_id,
        user_name=user.name if user else "Unknown",
        filename=video.filename,
        file_size=video.file_size,
        duration=video.duration,
        thumbnail_url=video.thumbnail_url,
        video_url=video_url,
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

    # Delete file from storage
    storage = get_video_storage()
    storage.delete_file(video.file_path)

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

    storage = get_video_storage()
    result = []

    for video in videos:
        video_url = storage.get_url(video.file_path)

        result.append(VideoResponse(
            id=video.id,
            session_id=video.session_id,
            user_id=video.user_id,
            user_name=current_user.name,
            filename=video.filename,
            file_size=video.file_size,
            duration=video.duration,
            thumbnail_url=video.thumbnail_url,
            video_url=video_url,
            offset_seconds=video.offset_seconds,
            title=video.title,
            description=video.description,
            is_public=video.is_public,
            created_at=video.created_at
        ))

    return result
