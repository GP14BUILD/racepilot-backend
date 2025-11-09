"""
Create a test club for development/testing.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.models import SessionLocal, Club
from datetime import datetime

def create_test_club():
    """Create a test club."""
    db = SessionLocal()

    try:
        # Check if TEST club already exists
        result = db.execute(text("SELECT id FROM clubs WHERE code = 'TEST'"))
        existing = result.fetchone()

        if existing:
            print(f"Test club already exists with code: TEST")
            print(f"Club ID: {existing[0]}")
        else:
            # Create test club
            db.execute(text("""
                INSERT INTO clubs (name, code, subscription_tier, created_at, is_active)
                VALUES ('Test Sailing Club', 'TEST', 'free', :now, 1)
            """), {"now": datetime.utcnow()})
            db.commit()

            result = db.execute(text("SELECT id FROM clubs WHERE code = 'TEST'"))
            club_id = result.fetchone()[0]

            print("=" * 60)
            print("Test Club Created Successfully!")
            print("=" * 60)
            print(f"\nClub Name: Test Sailing Club")
            print(f"Club Code: TEST")
            print(f"Club ID: {club_id}")
            print(f"Subscription: free")
            print(f"\nUse this club code when registering in the mobile app!")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_test_club()
