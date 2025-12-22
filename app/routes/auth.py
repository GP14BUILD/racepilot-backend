"""
Authentication endpoints for RacePilot.
Handles user registration, login, profile management, and boat management.
"""

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, validator
import re

from app.db.models import User, Club, Boat, PasswordResetToken
from app.auth import (
    get_db,
    get_current_user,
    authenticate_user,
    create_access_token,
    hash_password,
    Token,
    can_edit_user,
    require_role,
)
from app.email_service import send_password_reset_email, send_welcome_email
import secrets
import asyncio

router = APIRouter()


# Pydantic models for requests/responses
class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str
    club_code: str
    sail_number: Optional[str] = None
    role: Optional[str] = "sailor"

    @validator('email')
    def valid_email(cls, v):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v):
            raise ValueError('Invalid email address')
        return v.lower()

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v

    @validator('role')
    def valid_role(cls, v):
        if v not in ['sailor', 'coach', 'club_admin', 'admin']:
            raise ValueError('Role must be sailor, coach, club_admin, or admin')
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    club_id: Optional[int]
    club_name: Optional[str] = None
    role: str
    sail_number: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    sail_number: Optional[str] = None
    password: Optional[str] = None

    @validator('password')
    def password_strength(cls, v):
        if v and len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class BoatRequest(BaseModel):
    name: Optional[str] = None
    klass: Optional[str] = None
    sail_number: str
    is_default: bool = False


class BoatResponse(BaseModel):
    id: int
    user_id: int
    name: Optional[str]
    klass: Optional[str]
    sail_number: str
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Endpoints
@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new user.

    Requires a valid club code. Creates a new user account with hashed password.
    Sends welcome email and returns an access token for immediate login.
    """
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Get or create club
    club = db.query(Club).filter(Club.code == request.club_code.upper()).first()
    if not club:
        # Auto-create club if it doesn't exist
        club = Club(
            name=f"{request.club_code.upper()} Sailing Club",
            code=request.club_code.upper(),
            description="Auto-created club",
            location="",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(club)
        db.commit()
        db.refresh(club)

    if not club.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This club is not currently accepting new members"
        )

    # Create new user
    new_user = User(
        email=request.email,
        name=request.name,
        password_hash=hash_password(request.password),
        club_id=club.id,
        role=request.role,
        sail_number=request.sail_number,
        created_at=datetime.utcnow(),
        is_active=True
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Generate access token
    access_token = create_access_token(
        data={
            "user_id": new_user.id,
            "email": new_user.email,
            "club_id": new_user.club_id,
            "role": new_user.role
        }
    )

    # Send welcome email (non-blocking)
    try:
        await send_welcome_email(
            email=new_user.email,
            name=new_user.name,
            club_name=club.name
        )
    except Exception as e:
        # Log the error but don't fail registration
        print(f"Failed to send welcome email to {new_user.email}: {e}")

    return {
        "message": "Registration successful",
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "name": new_user.name,
            "club_id": new_user.club_id,
            "club_name": club.name,
            "role": new_user.role
        },
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/login", response_model=dict)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Login with email and password.

    Returns an access token on successful authentication.
    """
    user = authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last login time
    user.last_login = datetime.utcnow()
    db.commit()

    # Get club info
    club = db.query(Club).filter(Club.id == user.club_id).first()

    # Generate access token
    access_token = create_access_token(
        data={
            "user_id": user.id,
            "email": user.email,
            "club_id": user.club_id,
            "role": user.role
        }
    )

    return {
        "message": "Login successful",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "club_id": user.club_id,
            "club_name": club.name if club else None,
            "role": user.role,
            "sail_number": user.sail_number
        },
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=UserResponse)
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's profile information.
    """
    club = db.query(Club).filter(Club.id == current_user.club_id).first()

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        club_id=current_user.club_id,
        club_name=club.name if club else None,
        role=current_user.role,
        sail_number=current_user.sail_number,
        created_at=current_user.created_at,
        last_login=current_user.last_login
    )


@router.put("/me", response_model=UserResponse)
def update_my_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's profile.

    Users can update their own name, sail number, and password.
    """
    if request.name:
        current_user.name = request.name

    if request.sail_number is not None:
        current_user.sail_number = request.sail_number

    if request.password:
        current_user.password_hash = hash_password(request.password)

    db.commit()
    db.refresh(current_user)

    club = db.query(Club).filter(Club.id == current_user.club_id).first()

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        club_id=current_user.club_id,
        club_name=club.name if club else None,
        role=current_user.role,
        sail_number=current_user.sail_number,
        created_at=current_user.created_at,
        last_login=current_user.last_login
    )


# Boat management endpoints
@router.post("/boats", response_model=BoatResponse, status_code=status.HTTP_201_CREATED)
def create_boat(
    request: BoatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new boat for the current user.

    If this is marked as default, all other boats will be unmarked as default.
    """
    # If this boat is marked as default, unmark all others
    if request.is_default:
        db.query(Boat).filter(Boat.user_id == current_user.id).update({"is_default": False})

    new_boat = Boat(
        user_id=current_user.id,
        name=request.name,
        klass=request.klass,
        sail_number=request.sail_number,
        is_default=request.is_default,
        created_at=datetime.utcnow()
    )

    db.add(new_boat)
    db.commit()
    db.refresh(new_boat)

    return BoatResponse(
        id=new_boat.id,
        user_id=new_boat.user_id,
        name=new_boat.name,
        klass=new_boat.klass,
        sail_number=new_boat.sail_number,
        is_default=new_boat.is_default,
        created_at=new_boat.created_at
    )


@router.get("/boats", response_model=List[BoatResponse])
def get_my_boats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all boats owned by the current user.
    """
    boats = db.query(Boat).filter(Boat.user_id == current_user.id).all()

    return [
        BoatResponse(
            id=boat.id,
            user_id=boat.user_id,
            name=boat.name,
            klass=boat.klass,
            sail_number=boat.sail_number,
            is_default=boat.is_default,
            created_at=boat.created_at
        )
        for boat in boats
    ]


@router.get("/boats/{boat_id}", response_model=BoatResponse)
def get_boat(
    boat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific boat by ID.

    Users can only access their own boats.
    """
    boat = db.query(Boat).filter(
        Boat.id == boat_id,
        Boat.user_id == current_user.id
    ).first()

    if not boat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Boat not found"
        )

    return BoatResponse(
        id=boat.id,
        user_id=boat.user_id,
        name=boat.name,
        klass=boat.klass,
        sail_number=boat.sail_number,
        is_default=boat.is_default,
        created_at=boat.created_at
    )


@router.put("/boats/{boat_id}", response_model=BoatResponse)
def update_boat(
    boat_id: int,
    request: BoatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a boat.

    Users can only update their own boats.
    """
    boat = db.query(Boat).filter(
        Boat.id == boat_id,
        Boat.user_id == current_user.id
    ).first()

    if not boat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Boat not found"
        )

    # If this boat is being marked as default, unmark all others
    if request.is_default and not boat.is_default:
        db.query(Boat).filter(
            Boat.user_id == current_user.id,
            Boat.id != boat_id
        ).update({"is_default": False})

    boat.name = request.name
    boat.klass = request.klass
    boat.sail_number = request.sail_number
    boat.is_default = request.is_default

    db.commit()
    db.refresh(boat)

    return BoatResponse(
        id=boat.id,
        user_id=boat.user_id,
        name=boat.name,
        klass=boat.klass,
        sail_number=boat.sail_number,
        is_default=boat.is_default,
        created_at=boat.created_at
    )


@router.delete("/boats/{boat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_boat(
    boat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a boat.

    Users can only delete their own boats.
    """
    boat = db.query(Boat).filter(
        Boat.id == boat_id,
        Boat.user_id == current_user.id
    ).first()

    if not boat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Boat not found"
        )

    db.delete(boat)
    db.commit()

    return None


# Password reset endpoints
class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @validator('new_password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Request a password reset email.

    Generates a secure token and sends an email with reset link.
    Token expires in 1 hour.
    """
    # Find user by email
    user = db.query(User).filter(User.email == request.email.lower()).first()

    # Always return success message to prevent email enumeration
    if not user:
        return {
            "message": "If that email address is registered, a password reset link has been sent."
        }

    # Generate secure random token
    reset_token = secrets.token_urlsafe(32)

    # Delete any existing reset tokens for this user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id
    ).delete()

    # Create new reset token (expires in 1 hour)
    token_record = PasswordResetToken(
        user_id=user.id,
        token=reset_token,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        created_at=datetime.utcnow()
    )

    db.add(token_record)
    db.commit()

    # Send password reset email
    try:
        await send_password_reset_email(user.email, reset_token)
    except Exception as e:
        print(f"Failed to send password reset email: {e}")
        # Don't raise error - still return success to prevent enumeration

    return {
        "message": "If that email address is registered, a password reset link has been sent."
    }


@router.post("/reset-password")
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Reset password using a valid token.

    Token must not be expired or previously used.
    """
    # Find token record
    token_record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == request.token
    ).first()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    # Check if token is expired
    if datetime.utcnow() > token_record.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired. Please request a new one."
        )

    # Check if token was already used
    if token_record.used_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has already been used. Please request a new one."
        )

    # Get user
    user = db.query(User).filter(User.id == token_record.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Update password
    user.password_hash = hash_password(request.new_password)

    # Mark token as used
    token_record.used_at = datetime.utcnow()

    db.commit()

    return {
        "message": "Password has been reset successfully. You can now login with your new password."
    }


# Admin endpoints
class AdminUserResponse(BaseModel):
    id: int
    email: str
    name: str
    club_id: Optional[int]
    club_name: Optional[str] = None
    role: str
    sail_number: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/admin/users", response_model=List[AdminUserResponse])
def get_all_users(
    current_user: User = Depends(require_role("admin", "club_admin")),
    db: Session = Depends(get_db)
):
    """
    Get all users (admin only).

    Admin can see all users in their club.
    Super admin (if implemented) could see all users across all clubs.
    """
    # For now, admins can only see users in their own club
    users = db.query(User).filter(
        User.club_id == current_user.club_id
    ).order_by(User.created_at.desc()).all()

    result = []
    for user in users:
        club = db.query(Club).filter(Club.id == user.club_id).first()
        result.append(AdminUserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            club_id=user.club_id,
            club_name=club.name if club else None,
            role=user.role,
            sail_number=user.sail_number,
            created_at=user.created_at,
            last_login=user.last_login,
            is_active=user.is_active
        ))

    return result
