"""
Migration script to add privacy settings to clubs table.
Run this once to update the database schema.
"""

import os
import sys

# Add parent directory to path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from app.db.models import engine

def migrate():
    """Add privacy settings columns to clubs table"""

    with engine.connect() as conn:
        print("Adding privacy settings columns to clubs table...")

        # Check if columns already exist
        try:
            result = conn.execute(text("SELECT privacy_level FROM clubs LIMIT 1"))
            print("Privacy columns already exist")
            return
        except Exception:
            pass  # Columns don't exist, proceed with migration

        try:
            # Add privacy_level column
            conn.execute(text("""
                ALTER TABLE clubs
                ADD COLUMN privacy_level VARCHAR DEFAULT 'club_only'
            """))
            print("Added privacy_level column")

            # Add share_to_global column
            conn.execute(text("""
                ALTER TABLE clubs
                ADD COLUMN share_to_global BOOLEAN DEFAULT FALSE
            """))
            print("Added share_to_global column")

            # Add allow_anonymous_sharing column
            conn.execute(text("""
                ALTER TABLE clubs
                ADD COLUMN allow_anonymous_sharing BOOLEAN DEFAULT TRUE
            """))
            print("Added allow_anonymous_sharing column")

            # Add description column (if not exists)
            try:
                conn.execute(text("""
                    ALTER TABLE clubs
                    ADD COLUMN description VARCHAR
                """))
                print("Added description column")
            except Exception:
                print("  (description column already exists)")

            # Add location column (if not exists)
            try:
                conn.execute(text("""
                    ALTER TABLE clubs
                    ADD COLUMN location VARCHAR
                """))
                print("Added location column")
            except Exception:
                print("  (location column already exists)")

            # Add website column (if not exists)
            try:
                conn.execute(text("""
                    ALTER TABLE clubs
                    ADD COLUMN website VARCHAR
                """))
                print("Added website column")
            except Exception:
                print("  (website column already exists)")

            conn.commit()
            print("\nMigration completed successfully!")

        except Exception as e:
            conn.rollback()
            print(f"\nMigration failed: {e}")
            raise

if __name__ == "__main__":
    migrate()
