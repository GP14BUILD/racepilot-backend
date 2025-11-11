"""
Club management endpoints for RacePilot.
Handles club creation, updates, and admin operations.
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.models import User, Club
from app.auth import get_db, get_current_user

router = APIRouter(prefix="/clubs", tags=["Clubs"])


# Pydantic models
class ClubRequest(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    location: Optional[str] = None
    website: Optional[str] = None
    is_active: bool = True
    privacy_level: Optional[str] = 'club_only'  # 'public', 'club_only', 'private'
    share_to_global: Optional[bool] = False
    allow_anonymous_sharing: Optional[bool] = True


class ClubResponse(BaseModel):
    id: int
    name: str
    code: str
    description: Optional[str]
    location: Optional[str]
    website: Optional[str]
    is_active: bool
    created_at: datetime
    member_count: int = 0
    privacy_level: Optional[str] = 'club_only'
    share_to_global: Optional[bool] = False
    allow_anonymous_sharing: Optional[bool] = True

    class Config:
        from_attributes = True


class ClubMemberResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    sail_number: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class UpdateUserRoleRequest(BaseModel):
    role: str


# Helper functions
def is_admin(user: User) -> bool:
    """Check if user is an admin or club admin"""
    return user.role in ['admin', 'club_admin']


def is_super_admin(user: User) -> bool:
    """Check if user is a super admin (can manage all clubs)"""
    return user.role == 'admin'


def is_club_admin(user: User, club_id: int) -> bool:
    """Check if user is admin of the specified club"""
    return user.role == 'admin' or (user.role == 'club_admin' and user.club_id == club_id)


# Endpoints
@router.get("/", response_model=List[ClubResponse])
def list_clubs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    include_inactive: bool = False
):
    """
    List all clubs.

    Super admins see all clubs. Club admins see only their club.
    Regular users see only active clubs.
    """
    query = db.query(Club)

    # Filter based on user role
    if not is_super_admin(current_user):
        if is_admin(current_user):
            # Club admins see only their club
            query = query.filter(Club.id == current_user.club_id)
        elif not include_inactive:
            # Regular users see only active clubs
            query = query.filter(Club.is_active == True)

    clubs = query.all()

    # Add member count
    result = []
    for club in clubs:
        member_count = db.query(User).filter(User.club_id == club.id).count()
        club_data = ClubResponse(
            id=club.id,
            name=club.name,
            code=club.code,
            description=club.description,
            location=club.location,
            website=club.website,
            is_active=club.is_active,
            created_at=club.created_at,
            member_count=member_count,
            privacy_level=club.privacy_level or 'club_only',
            share_to_global=club.share_to_global or False,
            allow_anonymous_sharing=club.allow_anonymous_sharing if club.allow_anonymous_sharing is not None else True
        )
        result.append(club_data)

    return result


@router.get("/{club_id}", response_model=ClubResponse)
def get_club(
    club_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get details of a specific club.

    Users can view their own club. Admins can view any club.
    """
    club = db.query(Club).filter(Club.id == club_id).first()

    if not club:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Club not found"
        )

    # Check permissions
    if not is_super_admin(current_user) and current_user.club_id != club_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this club"
        )

    member_count = db.query(User).filter(User.club_id == club.id).count()

    return ClubResponse(
        id=club.id,
        name=club.name,
        code=club.code,
        description=club.description,
        location=club.location,
        website=club.website,
        is_active=club.is_active,
        created_at=club.created_at,
        member_count=member_count,
        privacy_level=club.privacy_level or 'club_only',
        share_to_global=club.share_to_global or False,
        allow_anonymous_sharing=club.allow_anonymous_sharing if club.allow_anonymous_sharing is not None else True
    )


@router.post("/", response_model=ClubResponse, status_code=status.HTTP_201_CREATED)
def create_club(
    request: ClubRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new club.

    Only super admins can create clubs.
    """
    if not is_super_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can create clubs"
        )

    # Check if code already exists
    existing_club = db.query(Club).filter(Club.code == request.code.upper()).first()
    if existing_club:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Club with code '{request.code}' already exists"
        )

    # Create new club
    new_club = Club(
        name=request.name,
        code=request.code.upper(),
        description=request.description,
        location=request.location,
        website=request.website,
        is_active=request.is_active,
        privacy_level=request.privacy_level or 'club_only',
        share_to_global=request.share_to_global or False,
        allow_anonymous_sharing=request.allow_anonymous_sharing if request.allow_anonymous_sharing is not None else True,
        created_at=datetime.utcnow()
    )

    db.add(new_club)
    db.commit()
    db.refresh(new_club)

    return ClubResponse(
        id=new_club.id,
        name=new_club.name,
        code=new_club.code,
        description=new_club.description,
        location=new_club.location,
        website=new_club.website,
        is_active=new_club.is_active,
        created_at=new_club.created_at,
        member_count=0,
        privacy_level=new_club.privacy_level or 'club_only',
        share_to_global=new_club.share_to_global or False,
        allow_anonymous_sharing=new_club.allow_anonymous_sharing if new_club.allow_anonymous_sharing is not None else True
    )


@router.put("/{club_id}", response_model=ClubResponse)
def update_club(
    club_id: int,
    request: ClubRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a club.

    Club admins can update their own club. Super admins can update any club.
    """
    club = db.query(Club).filter(Club.id == club_id).first()

    if not club:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Club not found"
        )

    # Check permissions
    if not is_club_admin(current_user, club_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this club"
        )

    # Update club details
    club.name = request.name
    club.code = request.code.upper()
    club.description = request.description
    club.location = request.location
    club.website = request.website
    club.is_active = request.is_active
    club.privacy_level = request.privacy_level or 'club_only'
    club.share_to_global = request.share_to_global or False
    club.allow_anonymous_sharing = request.allow_anonymous_sharing if request.allow_anonymous_sharing is not None else True

    db.commit()
    db.refresh(club)

    member_count = db.query(User).filter(User.club_id == club.id).count()

    return ClubResponse(
        id=club.id,
        name=club.name,
        code=club.code,
        description=club.description,
        location=club.location,
        website=club.website,
        is_active=club.is_active,
        created_at=club.created_at,
        member_count=member_count,
        privacy_level=club.privacy_level or 'club_only',
        share_to_global=club.share_to_global or False,
        allow_anonymous_sharing=club.allow_anonymous_sharing if club.allow_anonymous_sharing is not None else True
    )


@router.get("/{club_id}/members", response_model=List[ClubMemberResponse])
def get_club_members(
    club_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all members of a club.

    Club admins can view their club members. Super admins can view any club's members.
    """
    # Check permissions
    if not is_club_admin(current_user, club_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this club's members"
        )

    members = db.query(User).filter(User.club_id == club_id).all()

    return [
        ClubMemberResponse(
            id=member.id,
            email=member.email,
            name=member.name,
            role=member.role,
            sail_number=member.sail_number,
            created_at=member.created_at,
            last_login=member.last_login
        )
        for member in members
    ]


@router.put("/{club_id}/members/{user_id}/role", response_model=ClubMemberResponse)
def update_member_role(
    club_id: int,
    user_id: int,
    request: UpdateUserRoleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a club member's role.

    Club admins can update roles for their club members. Super admins can update anyone.
    Valid roles: sailor, coach, club_admin
    """
    # Check permissions
    if not is_club_admin(current_user, club_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update member roles"
        )

    # Get the user to update
    user = db.query(User).filter(
        User.id == user_id,
        User.club_id == club_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in this club"
        )

    # Validate role
    valid_roles = ['sailor', 'coach', 'club_admin']
    if request.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        )

    # Only super admins can assign super admin role
    if request.role == 'admin' and not is_super_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can assign the admin role"
        )

    # Update role
    user.role = request.role
    db.commit()
    db.refresh(user)

    return ClubMemberResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        sail_number=user.sail_number,
        created_at=user.created_at,
        last_login=user.last_login
    )
