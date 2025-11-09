"""
Migration script to add multi-club architecture to existing RacePilot database.

This script:
1. Adds new columns to existing tables
2. Creates a default "Legacy" club for existing data
3. Migrates existing users, boats, and sessions to the default club
4. Adds password hashes for existing users (default password: "changeme123")
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text, inspect
from app.db.models import engine, SessionLocal, Base
from passlib.context import CryptContext
from datetime import datetime

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def column_exists(table_name: str, column_name: str, inspector) -> bool:
    """Check if a column exists in a table."""
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def table_exists(table_name: str, inspector) -> bool:
    """Check if a table exists."""
    return table_name in inspector.get_table_names()

def migrate():
    """Run the migration."""
    print("Starting multi-club migration...")

    db = SessionLocal()
    inspector = inspect(engine)

    try:
        # Step 1: Create clubs table if it doesn't exist
        print("\n[1/8] Creating clubs table...")
        if not table_exists('clubs', inspector):
            db.execute(text("""
                CREATE TABLE clubs (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    code VARCHAR UNIQUE NOT NULL,
                    subscription_tier VARCHAR DEFAULT 'free',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    settings JSON,
                    is_active BOOLEAN DEFAULT 1
                )
            """))
            db.commit()
            print("[OK] Created clubs table")
        else:
            print("[OK] Clubs table already exists")

        # Step 2: Create default "Legacy" club for existing data
        print("\n[2/8] Creating default Legacy club...")
        result = db.execute(text("SELECT id FROM clubs WHERE code = 'LEGACY'"))
        legacy_club = result.fetchone()

        if not legacy_club:
            db.execute(text("""
                INSERT INTO clubs (name, code, subscription_tier, created_at, is_active)
                VALUES ('Legacy Club', 'LEGACY', 'free', :now, 1)
            """), {"now": datetime.utcnow()})
            db.commit()

            result = db.execute(text("SELECT id FROM clubs WHERE code = 'LEGACY'"))
            legacy_club_id = result.fetchone()[0]
            print(f"[OK] Created Legacy club with ID: {legacy_club_id}")
        else:
            legacy_club_id = legacy_club[0]
            print(f"[OK] Legacy club already exists with ID: {legacy_club_id}")

        # Step 3: Update users table
        print("\n[3/8] Updating users table...")
        if not column_exists('users', 'club_id', inspector):
            db.execute(text("ALTER TABLE users ADD COLUMN club_id INTEGER"))
            print("  - Added club_id column")

        if not column_exists('users', 'role', inspector):
            db.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'sailor'"))
            print("  - Added role column")

        if not column_exists('users', 'sail_number', inspector):
            db.execute(text("ALTER TABLE users ADD COLUMN sail_number VARCHAR"))
            print("  - Added sail_number column")

        if not column_exists('users', 'created_at', inspector):
            db.execute(text("ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            print("  - Added created_at column")

        if not column_exists('users', 'last_login', inspector):
            db.execute(text("ALTER TABLE users ADD COLUMN last_login TIMESTAMP"))
            print("  - Added last_login column")

        if not column_exists('users', 'is_active', inspector):
            db.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
            print("  - Added is_active column")

        # Migrate existing users to Legacy club
        db.execute(text("""
            UPDATE users
            SET club_id = :club_id,
                role = 'sailor',
                is_active = 1,
                created_at = COALESCE(created_at, :now)
            WHERE club_id IS NULL
        """), {"club_id": legacy_club_id, "now": datetime.utcnow()})
        db.commit()
        print("[OK] Updated users table and migrated existing users")

        # Step 4: Add default passwords to users without them
        print("\n[4/8] Adding default passwords to existing users...")

        # Check if password_hash column exists, if not it means no users need migration
        if column_exists('users', 'password_hash', inspector):
            result = db.execute(text("SELECT COUNT(*) FROM users WHERE password_hash IS NULL OR password_hash = ''"))
            users_without_password = result.fetchone()[0]

            if users_without_password > 0:
                try:
                    default_hash = pwd_context.hash("changeme123")
                    db.execute(text("""
                        UPDATE users
                        SET password_hash = :hash
                        WHERE password_hash IS NULL OR password_hash = ''
                    """), {"hash": default_hash})
                    db.commit()
                    print(f"[OK] Added default password 'changeme123' to {users_without_password} users")
                except Exception as e:
                    print(f"[WARN] Could not hash default password: {e}")
                    print(f"[WARN] {users_without_password} users will need passwords set manually")
            else:
                print("[OK] All users already have passwords")
        else:
            print("[OK] Password hash column doesn't exist, skipping")

        # Step 5: Update boats table
        print("\n[5/8] Updating boats table...")

        # Rename owner_id to user_id if needed
        if column_exists('boats', 'owner_id', inspector) and not column_exists('boats', 'user_id', inspector):
            db.execute(text("ALTER TABLE boats RENAME COLUMN owner_id TO user_id"))
            print("  - Renamed owner_id to user_id")

        if not column_exists('boats', 'created_at', inspector):
            db.execute(text("ALTER TABLE boats ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            db.execute(text("UPDATE boats SET created_at = :now WHERE created_at IS NULL"), {"now": datetime.utcnow()})
            print("  - Added created_at column")

        if not column_exists('boats', 'is_default', inspector):
            db.execute(text("ALTER TABLE boats ADD COLUMN is_default BOOLEAN DEFAULT 0"))
            print("  - Added is_default column")

        db.commit()
        print("[OK] Updated boats table")

        # Step 6: Update sessions table
        print("\n[6/8] Updating sessions table...")

        if not column_exists('sessions', 'club_id', inspector):
            db.execute(text("ALTER TABLE sessions ADD COLUMN club_id INTEGER"))
            print("  - Added club_id column")

        if not column_exists('sessions', 'notes', inspector):
            db.execute(text("ALTER TABLE sessions ADD COLUMN notes TEXT"))
            print("  - Added notes column")

        # Migrate existing sessions to Legacy club
        db.execute(text("""
            UPDATE sessions
            SET club_id = :club_id
            WHERE club_id IS NULL
        """), {"club_id": legacy_club_id})
        db.commit()
        print("[OK] Updated sessions table and migrated existing sessions")

        # Step 7: Update AI feature tables with club_id
        print("\n[7/8] Updating AI feature tables...")

        ai_tables = [
            'maneuvers',
            'performance_baselines',
            'performance_anomalies',
            'fleet_comparisons',
            'vmg_optimizations',
            'coaching_recommendations',
            'wind_shifts',
            'wind_patterns'
        ]

        for table_name in ai_tables:
            if table_exists(table_name, inspector):
                if not column_exists(table_name, 'club_id', inspector):
                    db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN club_id INTEGER"))
                    # Migrate existing records to Legacy club
                    db.execute(text(f"""
                        UPDATE {table_name}
                        SET club_id = :club_id
                        WHERE club_id IS NULL
                    """), {"club_id": legacy_club_id})
                    print(f"  - Updated {table_name}")

        db.commit()
        print("[OK] Updated all AI feature tables")

        # Step 8: Create indexes for performance
        print("\n[8/8] Creating indexes...")

        try:
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_users_club_id ON users(club_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_sessions_club_id ON sessions(club_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_clubs_code ON clubs(code)"))
            db.commit()
            print("[OK] Created performance indexes")
        except Exception as e:
            print(f"  Note: Some indexes may already exist: {e}")

        print("\n" + "="*60)
        print("Migration completed successfully!")
        print("="*60)
        print(f"\nDefault club created: 'Legacy Club' (code: LEGACY)")
        print(f"All existing data has been migrated to this club.")
        print(f"\nDefault password for existing users: 'changeme123'")
        print(f"Users should change this password on first login.")

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("RacePilot Multi-Club Migration")
    print("="*60)
    print("\nThis will modify your database schema.")
    print("Please ensure you have a backup before proceeding.")
    print("\nPress Enter to continue or Ctrl+C to cancel...")

    try:
        input()
        migrate()
    except KeyboardInterrupt:
        print("\n\nMigration cancelled by user.")
        sys.exit(0)
