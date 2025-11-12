"""
Migration script to add videos table.
Run this once to add video upload functionality to RacePilot.
"""

import os
import sys

# Add parent directory to path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from app.db.models import engine

def migrate():
    """Add videos table"""

    with engine.connect() as conn:
        print("Adding videos table...")

        # Check if table already exists
        try:
            result = conn.execute(text("SELECT id FROM videos LIMIT 1"))
            print("Videos table already exists")
            return
        except Exception:
            pass  # Table doesn't exist, proceed with migration

        try:
            # Create videos table
            conn.execute(text("""
                CREATE TABLE videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    club_id INTEGER,
                    filename VARCHAR NOT NULL,
                    file_path VARCHAR NOT NULL,
                    file_size INTEGER NOT NULL,
                    duration FLOAT,
                    thumbnail_url VARCHAR,
                    video_url VARCHAR,
                    offset_seconds FLOAT DEFAULT 0.0,
                    title VARCHAR,
                    description VARCHAR,
                    is_public BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (club_id) REFERENCES clubs(id)
                )
            """))
            print("Created videos table")

            # Create indexes
            conn.execute(text("CREATE INDEX ix_videos_session_id ON videos(session_id)"))
            conn.execute(text("CREATE INDEX ix_videos_user_id ON videos(user_id)"))
            conn.execute(text("CREATE INDEX ix_videos_club_id ON videos(club_id)"))
            conn.execute(text("CREATE INDEX ix_videos_created_at ON videos(created_at)"))
            print("Created videos indexes")

            conn.commit()
            print("\nMigration completed successfully!")

        except Exception as e:
            conn.rollback()
            print(f"\nMigration failed: {e}")
            raise

if __name__ == "__main__":
    migrate()
