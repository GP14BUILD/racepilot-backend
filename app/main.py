from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db.models import init_db, Base, engine
from .routes import auth, sessions, telemetry, analytics, ai, courses
from sqlalchemy import inspect

app = FastAPI(title="RacePilot API", version="0.1.0")

# Enable CORS for dashboard and mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for mobile app support
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/")
def root():
    return {
        "message": "RacePilot API is running",
        "version": "0.1.0",
        "status": "healthy"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "racepilot-backend"}

@app.post("/migrate")
def run_migration():
    """Run database migration to create AI feature tables."""
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # Create all tables
        Base.metadata.create_all(bind=engine)

        # Check which tables were created
        new_tables = set(inspector.get_table_names()) - set(existing_tables)

        return {
            "success": True,
            "message": "Migration completed successfully",
            "tables_created": list(new_tables),
            "total_tables": len(inspector.get_table_names())
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/create-test-club")
def create_test_club():
    """Create TEST club for development."""
    from sqlalchemy import text
    from datetime import datetime
    from .db.models import SessionLocal

    db = SessionLocal()
    try:
        # Check if TEST club exists
        result = db.execute(text("SELECT id FROM clubs WHERE code = 'TEST'"))
        existing = result.fetchone()

        if existing:
            return {"success": True, "message": "TEST club already exists", "club_id": existing[0]}

        # Create TEST club
        db.execute(text("""
            INSERT INTO clubs (name, code, subscription_tier, is_active)
            VALUES ('Test Sailing Club', 'TEST', 'free', 1)
        """))
        db.commit()

        result = db.execute(text("SELECT id FROM clubs WHERE code = 'TEST'"))
        club_id = result.fetchone()[0]

        return {"success": True, "message": "TEST club created", "club_id": club_id}
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(courses.router, prefix="/courses", tags=["courses"])

# ✅ AI endpoints
app.include_router(ai.router, prefix="/ai", tags=["ai"])
