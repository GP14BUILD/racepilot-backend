"""
Authentication and authorization utilities for RacePilot.
Handles JWT tokens, password hashing, and user permissions.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.models import SessionLocal, User

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-CHANGE-IN-PRODUCTION")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token scheme
security = HTTPBearer()


# Pydantic models for tokens
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    club_id: Optional[int] = None
    role: Optional[str] = None


# Password utilities
def hash_password(password: str) -> str:
    """Hash a plain text password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


# JWT token utilities
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Dictionary containing user information (user_id, email, club_id, role)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> TokenData:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string

    Returns:
        TokenData object with user information

    Raises:
        HTTPException: If token is invalid or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        email: str = payload.get("email")
        club_id: int = payload.get("club_id")
        role: str = payload.get("role")

        if user_id is None or email is None:
            raise credentials_exception

        token_data = TokenData(
            user_id=user_id,
            email=email,
            club_id=club_id,
            role=role
        )
        return token_data

    except JWTError:
        raise credentials_exception


# Database dependency
def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Authentication dependency
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from the JWT token.

    Args:
        credentials: HTTP Authorization header with Bearer token
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials
    token_data = decode_access_token(token)

    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    return user


# Role-based authorization
def require_role(*allowed_roles: str):
    """
    Dependency factory for role-based authorization.

    Usage:
        @app.get("/coach-only")
        def coach_endpoint(user: User = Depends(require_role("coach", "admin"))):
            ...

    Args:
        *allowed_roles: List of allowed roles (e.g., "sailor", "coach", "admin")

    Returns:
        Dependency function that validates user role
    """
    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}"
            )
        return user

    return role_checker


# User authentication
def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Authenticate a user by email and password.

    Args:
        db: Database session
        email: User's email
        password: Plain text password

    Returns:
        User object if authentication successful, None otherwise
    """
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


# Club-based data filtering
def get_user_club_filter(user: User, target_club_id: Optional[int] = None):
    """
    Get the appropriate club_id filter for database queries.

    Admins can access their own club's data (or a specific club if specified).
    Coaches can only access their club's data.
    Sailors can only access their club's data.

    Args:
        user: Current user
        target_club_id: Optional specific club to filter (admin only)

    Returns:
        club_id to filter by

    Raises:
        HTTPException: If user tries to access unauthorized club
    """
    # Admins can optionally view other clubs (for super admin scenarios)
    if user.role == "admin" and target_club_id:
        # For now, admins can only see their own club
        # In future, could add super_admin role for cross-club access
        if target_club_id != user.club_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access other club's data"
            )
        return target_club_id

    # All other users can only see their own club's data
    return user.club_id


def can_edit_user(current_user: User, target_user: User) -> bool:
    """
    Check if current user can edit another user's data.

    Rules:
    - Users can edit their own data
    - Admins can edit users in their club
    - Coaches cannot edit other users

    Args:
        current_user: The user attempting the edit
        target_user: The user being edited

    Returns:
        True if edit is allowed, False otherwise
    """
    # Users can edit themselves
    if current_user.id == target_user.id:
        return True

    # Admins can edit users in their club
    if current_user.role == "admin" and current_user.club_id == target_user.club_id:
        return True

    return False


def can_view_session(current_user: User, session_club_id: int, session_user_id: int) -> bool:
    """
    Check if current user can view a specific session.

    Rules:
    - Users can view their own sessions
    - Coaches can view all sessions in their club
    - Admins can view all sessions in their club

    Args:
        current_user: The user attempting to view
        session_club_id: The club_id of the session
        session_user_id: The user_id who created the session

    Returns:
        True if viewing is allowed, False otherwise
    """
    # Must be in same club
    if current_user.club_id != session_club_id:
        return False

    # Users can view their own sessions
    if current_user.id == session_user_id:
        return True

    # Coaches and admins can view all sessions in their club
    if current_user.role in ["coach", "admin"]:
        return True

    return False


# Subscription-based authorization
def get_user_subscription_features(user: User, db: Session) -> dict:
    """
    Get the subscription features available to a user.

    Returns dict with:
    - subscribed: bool
    - plan: str
    - max_sessions: int (-1 for unlimited)
    - ai_coaching: bool
    - fleet_replay: bool
    - wind_analysis: bool
    """
    from app.db.models import Subscription

    # Check for active subscription
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user.id,
        Subscription.status == "active"
    ).first()

    if subscription and subscription.plan in ["pro_monthly", "club_monthly"]:
        # Pro or Club subscription - unlimited features
        return {
            "subscribed": True,
            "plan": subscription.plan,
            "max_sessions": -1,  # Unlimited
            "ai_coaching": True,
            "fleet_replay": True,
            "wind_analysis": True
        }

    # Free tier - limited features
    return {
        "subscribed": False,
        "plan": "free",
        "max_sessions": 5,
        "ai_coaching": False,
        "fleet_replay": False,
        "wind_analysis": False
    }


def require_subscription(feature: str = None):
    """
    Dependency to require an active subscription.

    Usage:
        @app.get("/premium-feature")
        def premium_endpoint(user: User = Depends(require_subscription())):
            ...

    Or for specific features:
        @app.get("/ai-coaching")
        def ai_endpoint(user: User = Depends(require_subscription("ai_coaching"))):
            ...
    """
    def subscription_checker(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        features = get_user_subscription_features(user, db)

        if not features["subscribed"]:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Active subscription required. Please upgrade to Pro or Club tier."
            )

        # Check specific feature if requested
        if feature and not features.get(feature, False):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"This feature requires a subscription. Feature: {feature}"
            )

        return user

    return subscription_checker


def check_session_limit(user: User, db: Session):
    """
    Check if user has exceeded their monthly session limit.
    Raises HTTPException if limit exceeded.

    NOTE: Session limits temporarily disabled for development/testing
    """
    from app.db.models import Session as DbSession
    from datetime import datetime, timedelta

    # TEMPORARY: Bypass session limit during development
    return

    features = get_user_subscription_features(user, db)

    # Unlimited sessions for subscribed users
    if features["max_sessions"] == -1:
        return

    # Count sessions this month
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    session_count = db.query(DbSession).filter(
        DbSession.user_id == user.id,
        DbSession.created_at >= month_start
    ).count()

    if session_count >= features["max_sessions"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Monthly session limit reached ({features['max_sessions']} sessions). Please upgrade to Pro for unlimited sessions."
        )
