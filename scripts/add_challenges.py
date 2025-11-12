"""
Migration script to add challenges and challenge_attempts tables.
Run this once to update the database schema for Ghost Boat Racing feature.
"""

import os
import sys

# Add parent directory to path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from app.db.models import engine

def migrate():
    """Add challenges tables"""

    with engine.connect() as conn:
        print("Adding challenges tables...")

        # Check if tables already exist
        try:
            result = conn.execute(text("SELECT id FROM challenges LIMIT 1"))
            print("Challenges tables already exist")
            return
        except Exception:
            pass  # Tables don't exist, proceed with migration

        try:
            # Create challenges table
            conn.execute(text("""
                CREATE TABLE challenges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creator_id INTEGER NOT NULL,
                    session_id INTEGER NOT NULL,
                    club_id INTEGER,
                    title VARCHAR NOT NULL,
                    description VARCHAR,
                    difficulty VARCHAR DEFAULT 'medium',
                    is_public BOOLEAN DEFAULT 0,
                    expires_at DATETIME,
                    boat_class VARCHAR,
                    min_wind_speed FLOAT,
                    max_wind_speed FLOAT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    attempt_count INTEGER DEFAULT 0,
                    best_time FLOAT,
                    FOREIGN KEY (creator_id) REFERENCES users(id),
                    FOREIGN KEY (session_id) REFERENCES sessions(id),
                    FOREIGN KEY (club_id) REFERENCES clubs(id)
                )
            """))
            print("Created challenges table")

            # Create indexes
            conn.execute(text("CREATE INDEX ix_challenges_creator_id ON challenges(creator_id)"))
            conn.execute(text("CREATE INDEX ix_challenges_session_id ON challenges(session_id)"))
            conn.execute(text("CREATE INDEX ix_challenges_club_id ON challenges(club_id)"))
            conn.execute(text("CREATE INDEX ix_challenges_created_at ON challenges(created_at)"))
            print("Created challenges indexes")

            # Create challenge_attempts table
            conn.execute(text("""
                CREATE TABLE challenge_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    challenge_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    session_id INTEGER NOT NULL,
                    time_difference FLOAT NOT NULL,
                    max_lead FLOAT,
                    max_deficit FLOAT,
                    result VARCHAR NOT NULL,
                    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    xp_earned INTEGER DEFAULT 0,
                    FOREIGN KEY (challenge_id) REFERENCES challenges(id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """))
            print("Created challenge_attempts table")

            # Create indexes
            conn.execute(text("CREATE INDEX ix_challenge_attempts_challenge_id ON challenge_attempts(challenge_id)"))
            conn.execute(text("CREATE INDEX ix_challenge_attempts_user_id ON challenge_attempts(user_id)"))
            conn.execute(text("CREATE INDEX ix_challenge_attempts_session_id ON challenge_attempts(session_id)"))
            conn.execute(text("CREATE INDEX ix_challenge_attempts_submitted_at ON challenge_attempts(submitted_at)"))
            print("Created challenge_attempts indexes")

            conn.commit()
            print("\nMigration completed successfully!")

        except Exception as e:
            conn.rollback()
            print(f"\nMigration failed: {e}")
            raise

if __name__ == "__main__":
    migrate()
