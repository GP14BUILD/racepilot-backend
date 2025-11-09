"""
Migration script to add AI feature tables to the database.

This script adds 8 new tables:
- maneuvers
- performance_baselines
- performance_anomalies
- fleet_comparisons
- vmg_optimizations
- coaching_recommendations
- wind_shifts
- wind_patterns
"""

import sys
import os

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.models import engine, Base, Maneuver, PerformanceBaseline, PerformanceAnomaly, FleetComparison, VMGOptimization, CoachingRecommendation, WindShift, WindPattern
from sqlalchemy import inspect

def check_table_exists(table_name):
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def migrate_ai_tables():
    """Create AI feature tables if they don't exist."""
    print("Starting AI Features Database Migration")
    print("=" * 60)

    # List of new tables and their models
    new_tables = [
        ('maneuvers', Maneuver),
        ('performance_baselines', PerformanceBaseline),
        ('performance_anomalies', PerformanceAnomaly),
        ('fleet_comparisons', FleetComparison),
        ('vmg_optimizations', VMGOptimization),
        ('coaching_recommendations', CoachingRecommendation),
        ('wind_shifts', WindShift),
        ('wind_patterns', WindPattern),
    ]

    # Check which tables already exist
    tables_to_create = []
    tables_existing = []

    for table_name, model in new_tables:
        if check_table_exists(table_name):
            tables_existing.append(table_name)
            print(f"[OK] Table '{table_name}' already exists")
        else:
            tables_to_create.append((table_name, model))
            print(f"[NEW] Table '{table_name}' will be created")

    print("\n" + "=" * 60)

    if not tables_to_create:
        print("[SUCCESS] All AI feature tables already exist. No migration needed.")
        return

    # Create new tables
    print(f"\nCreating {len(tables_to_create)} new tables...")
    print("-" * 60)

    try:
        # Create all new tables
        Base.metadata.create_all(bind=engine)

        print("\n[SUCCESS] Migration completed successfully!")
        print("\nCreated tables:")
        for table_name, _ in tables_to_create:
            print(f"  * {table_name}")

        if tables_existing:
            print(f"\nExisting tables (unchanged):")
            for table_name in tables_existing:
                print(f"  * {table_name}")

        print("\n" + "=" * 60)
        print("AI Features are ready to use!")

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate_ai_tables()
