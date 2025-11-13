import sys
from datetime import datetime
from app.db.models import init_db, User, Club, SessionLocal
from app.auth import hash_password, create_access_token

# Initialize database
init_db()

# Get a database session
db = SessionLocal()

try:
    # Test data
    email = "testdebug@example.com"
    password = "testpass123"
    name = "Test Debug User"
    club_code = "TEST"

    print(f"Testing registration for {email}...")

    # Check if user exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        print(f"User already exists, deleting...")
        db.delete(existing_user)
        db.commit()

    # Get or create club
    club = db.query(Club).filter(Club.code == club_code.upper()).first()
    if not club:
        print(f"Club {club_code} not found, creating...")
        club = Club(
            name=f"{club_code.upper()} Sailing Club",
            code=club_code.upper(),
            description="Auto-created club",
            location="",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(club)
        db.commit()
        db.refresh(club)
        print(f"Club created with ID {club.id}")
    else:
        print(f"Found existing club with ID {club.id}")

    # Hash password
    print("Hashing password...")
    password_hash = hash_password(password)
    print(f"Password hashed successfully")

    # Create user
    print("Creating user...")
    new_user = User(
        email=email,
        name=name,
        password_hash=password_hash,
        club_id=club.id,
        role="sailor",
        sail_number=None,
        created_at=datetime.utcnow(),
        is_active=True
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    print(f"SUCCESS! User created with ID {new_user.id}")

    # Generate token
    access_token = create_access_token(
        data={
            "user_id": new_user.id,
            "email": new_user.email,
            "club_id": new_user.club_id,
            "role": new_user.role
        }
    )

    print(f"Token created: {access_token[:50]}...")

except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
