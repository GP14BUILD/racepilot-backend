from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db.models import init_db, Base, engine
from .routes import auth, sessions, telemetry, analytics, ai, courses
from sqlalchemy import inspect

app = FastAPI(title="RacePilot API", version="0.1.0")

# Enable CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your Vercel domain
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

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(courses.router, prefix="/courses", tags=["courses"])

# ✅ AI endpoints
app.include_router(ai.router, prefix="/ai", tags=["ai"])
