"""
Create an admin user for RacePilot.
This script creates a new admin user in the database.

Usage:
    python scripts/create_admin.py <email> <password> <name> [club_id]

Example:
    python scripts/create_admin.py kevindonnelly@race-pilot.app worldwide123 "Kevin Donnelly"
"""

import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.models import SessionLocal, User, Club
from app.auth import hash_password
from datetime import datetime


def create_admin_user(email: str, password: str, name: str, club_id: int = None):
    """Create a new admin user"""

    db = SessionLocal()

    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"❌ User with email {email} already exists!")
            print(f"   Current role: {existing_user.role}")

            # Offer to promote existing user to admin
            if existing_user.role != "admin":
                print(f"\n🔄 Promoting {existing_user.name} to admin...")
                existing_user.role = "admin"
                db.commit()
                print(f"✅ Successfully promoted {existing_user.name} to admin role!")
                print(f"   Email: {existing_user.email}")
                print(f"   Club ID: {existing_user.club_id}")
            else:
                print(f"✅ User is already an admin")

            return existing_user

        # Determine club_id
        if club_id is None:
            # Try to find the first club (or you can specify a default)
            club = db.query(Club).first()
            if club:
                club_id = club.id
                print(f"ℹ️  No club specified, using: {club.name} (ID: {club.id})")
            else:
                print("❌ No clubs found in database. Please create a club first.")
                return None
        else:
            # Verify club exists
            club = db.query(Club).filter(Club.id == club_id).first()
            if not club:
                print(f"❌ Club with ID {club_id} not found!")
                return None
            print(f"ℹ️  Using club: {club.name} (ID: {club.id})")

        # Create new admin user
        admin_user = User(
            email=email,
            name=name,
            password_hash=hash_password(password),
            club_id=club_id,
            role="admin",
            is_active=True,
            created_at=datetime.utcnow()
        )

        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print(f"\n✅ Successfully created admin user!")
        print(f"   Name: {admin_user.name}")
        print(f"   Email: {admin_user.email}")
        print(f"   Role: {admin_user.role}")
        print(f"   Club ID: {admin_user.club_id}")
        print(f"\n🎉 You can now login at https://race-pilot.app/login")

        return admin_user

    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        db.rollback()
        return None
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python scripts/create_admin.py <email> <password> <name> [club_id]")
        print("\nExample:")
        print('  python scripts/create_admin.py kevindonnelly@race-pilot.app worldwide123 "Kevin Donnelly"')
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]
    name = sys.argv[3]
    club_id = int(sys.argv[4]) if len(sys.argv) > 4 else None

    create_admin_user(email, password, name, club_id)
