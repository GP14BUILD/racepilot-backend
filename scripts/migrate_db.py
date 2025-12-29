"""
Simple database migration script to create all tables.
Run this to initialize or update the database schema.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.models import Base, engine

def migrate():
    """Create all tables defined in models.py"""
    print("Running database migration...")
    print("Creating all tables...")

    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("Successfully created all tables!")

        # List all tables created
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        print(f"\nTotal tables in database: {len(tables)}")
        print("Tables:")
        for table in sorted(tables):
            print(f"  - {table}")

        return True
    except Exception as e:
        print(f"ERROR during migration: {str(e)}")
        return False

if __name__ == "__main__":
    success = migrate()
    if success:
        print("\nMigration complete!")
    else:
        print("\nMigration failed!")
        sys.exit(1)
