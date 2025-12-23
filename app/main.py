from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db.models import init_db, Base, engine
from sqlalchemy import inspect

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv('.env.local')
    load_dotenv()
except ImportError:
    # dotenv not installed, environment variables must be set manually
    pass

# Import routes individually with error handling
try:
    from .routes import auth
    AUTH_AVAILABLE = True
except Exception as e:
    print(f"Failed to import auth routes: {e}")
    auth = None
    AUTH_AVAILABLE = False

try:
    from .routes import sessions
    SESSIONS_AVAILABLE = True
except Exception as e:
    print(f"Failed to import sessions routes: {e}")
    sessions = None
    SESSIONS_AVAILABLE = False

try:
    from .routes import telemetry
    TELEMETRY_AVAILABLE = True
except Exception as e:
    print(f"Failed to import telemetry routes: {e}")
    telemetry = None
    TELEMETRY_AVAILABLE = False

try:
    from .routes import analytics
    ANALYTICS_AVAILABLE = True
except Exception as e:
    print(f"Failed to import analytics routes: {e}")
    analytics = None
    ANALYTICS_AVAILABLE = False

try:
    from .routes import ai
    AI_AVAILABLE = True
except Exception as e:
    print(f"Failed to import ai routes: {e}")
    ai = None
    AI_AVAILABLE = False

try:
    from .routes import courses
    COURSES_AVAILABLE = True
except Exception as e:
    print(f"Failed to import courses routes: {e}")
    courses = None
    COURSES_AVAILABLE = False

try:
    from .routes import clubs
    CLUBS_AVAILABLE = True
except Exception as e:
    print(f"Failed to import clubs routes: {e}")
    clubs = None
    CLUBS_AVAILABLE = False

try:
    from .routes import challenges
    CHALLENGES_AVAILABLE = True
except Exception as e:
    print(f"Failed to import challenges routes: {e}")
    challenges = None
    CHALLENGES_AVAILABLE = False

try:
    from .routes import videos
    VIDEOS_AVAILABLE = True
except Exception as e:
    print(f"Failed to import videos routes: {e}")
    videos = None
    VIDEOS_AVAILABLE = False

try:
    from .routes import payments
    PAYMENTS_AVAILABLE = True
except Exception as e:
    print(f"Failed to import payments routes: {e}")
    payments = None
    PAYMENTS_AVAILABLE = False

app = FastAPI(title="RacePilot API", version="0.1.1")

# Enable CORS for dashboard and mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Local development
        "http://localhost:3000",  # Alternative local port
        "https://racepilot-dashboard-production.up.railway.app",  # Production Railway
        "https://racepilot-dashboard.vercel.app",  # Production Vercel (backup)
        "https://racepilot-dashboard-k8upa8p5h-kevins-projects-5141f84d.vercel.app",  # Preview
        "https://*.vercel.app",  # All Vercel preview deployments
        "*"  # Mobile app support (consider restricting this later)
    ],
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
        "version": "0.1.1",
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


@app.post("/setup-admin")
def setup_admin():
    """
    Create admin user for RacePilot.

    Creates Kevin Donnelly as admin user with predefined credentials.
    This is a one-time setup endpoint.
    """
    from .db.models import SessionLocal, User, Club
    from .auth import hash_password
    from datetime import datetime

    db = SessionLocal()
    try:
        # Check if admin already exists
        existing_user = db.query(User).filter(User.email == "kevindonnelly@race-pilot.app").first()

        if existing_user:
            # Update role to admin and reset password
            existing_user.role = "admin"
            existing_user.password_hash = hash_password("worldwide123")
            db.commit()
            return {
                "success": True,
                "message": "Admin user updated (role: admin, password: worldwide123)",
                "user": {
                    "email": existing_user.email,
                    "name": existing_user.name,
                    "role": existing_user.role,
                    "club_id": existing_user.club_id
                }
            }

        # Find first club (or create one if none exist)
        club = db.query(Club).first()
        if not club:
            # Create a default club if none exists
            club = Club(
                name="CLUB Sailing Club",
                code="CLUB",
                subscription_tier="pro",
                is_active=True
            )
            db.add(club)
            db.commit()
            db.refresh(club)

        # Create admin user
        admin_user = User(
            email="kevindonnelly@race-pilot.app",
            name="Kevin Donnelly",
            password_hash=hash_password("worldwide123"),
            club_id=club.id,
            role="admin",
            is_active=True,
            created_at=datetime.utcnow()
        )

        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        return {
            "success": True,
            "message": "Admin user created successfully",
            "user": {
                "email": admin_user.email,
                "name": admin_user.name,
                "role": admin_user.role,
                "club_id": admin_user.club_id,
                "club_name": club.name
            }
        }

    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        db.close()


@app.get("/backup-database")
def backup_database():
    """
    Backup all database tables to JSON.

    Returns all users, clubs, sessions, and other data in JSON format
    that can be restored later if database is reset.
    """
    from .db.models import SessionLocal, User, Club

    db = SessionLocal()
    try:
        # Get all clubs
        clubs = db.query(Club).all()
        clubs_data = [
            {
                "id": club.id,
                "name": club.name,
                "code": club.code,
                "subscription_tier": club.subscription_tier,
                "is_active": club.is_active,
                "privacy_level": club.privacy_level,
                "share_to_global": club.share_to_global,
                "allow_anonymous_sharing": club.allow_anonymous_sharing,
                "description": club.description,
                "location": club.location,
                "website": club.website,
                "created_at": club.created_at.isoformat() if club.created_at else None
            }
            for club in clubs
        ]

        # Get all users (excluding password hashes for security)
        users = db.query(User).all()
        users_data = [
            {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "club_id": user.club_id,
                "role": user.role,
                "sail_number": user.sail_number,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None
            }
            for user in users
        ]

        return {
            "success": True,
            "backup_date": datetime.utcnow().isoformat(),
            "counts": {
                "clubs": len(clubs_data),
                "users": len(users_data)
            },
            "data": {
                "clubs": clubs_data,
                "users": users_data
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        db.close()


@app.post("/restore-database")
def restore_database(backup_data: dict):
    """
    Restore database from backup JSON.

    WARNING: This will clear existing data and restore from backup.
    Only use this after setting up PostgreSQL.
    """
    from .db.models import SessionLocal, User, Club
    from .auth import hash_password

    db = SessionLocal()
    try:
        data = backup_data.get("data", {})

        # Restore clubs
        clubs_restored = 0
        for club_data in data.get("clubs", []):
            existing = db.query(Club).filter(Club.code == club_data["code"]).first()
            if not existing:
                club = Club(
                    name=club_data["name"],
                    code=club_data["code"],
                    subscription_tier=club_data.get("subscription_tier", "free"),
                    is_active=club_data.get("is_active", True),
                    privacy_level=club_data.get("privacy_level", "club_only"),
                    share_to_global=club_data.get("share_to_global", False),
                    allow_anonymous_sharing=club_data.get("allow_anonymous_sharing", True),
                    description=club_data.get("description"),
                    location=club_data.get("location"),
                    website=club_data.get("website")
                )
                db.add(club)
                clubs_restored += 1

        db.commit()

        # Restore users (with default password that must be reset)
        users_restored = 0
        for user_data in data.get("users", []):
            existing = db.query(User).filter(User.email == user_data["email"]).first()
            if not existing:
                user = User(
                    email=user_data["email"],
                    name=user_data["name"],
                    password_hash=hash_password("resetme123"),  # Default password
                    club_id=user_data.get("club_id"),
                    role=user_data.get("role", "sailor"),
                    sail_number=user_data.get("sail_number"),
                    is_active=user_data.get("is_active", True)
                )
                db.add(user)
                users_restored += 1

        db.commit()

        return {
            "success": True,
            "message": "Database restored from backup",
            "restored": {
                "clubs": clubs_restored,
                "users": users_restored
            },
            "note": "All restored users have password 'resetme123' - they should reset via forgot password"
        }

    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        db.close()


# Include routers that loaded successfully
if AUTH_AVAILABLE and auth:
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    print("[OK] Auth routes loaded")

if SESSIONS_AVAILABLE and sessions:
    app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
    print("[OK] Sessions routes loaded")

if TELEMETRY_AVAILABLE and telemetry:
    app.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
    print("[OK] Telemetry routes loaded")

if ANALYTICS_AVAILABLE and analytics:
    app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
    print("[OK] Analytics routes loaded")

if COURSES_AVAILABLE and courses:
    app.include_router(courses.router, prefix="/courses", tags=["courses"])
    print("[OK] Courses routes loaded")

if AI_AVAILABLE and ai:
    app.include_router(ai.router, prefix="/ai", tags=["ai"])
    print("[OK] AI routes loaded")

if CLUBS_AVAILABLE and clubs:
    app.include_router(clubs.router, prefix="/clubs", tags=["clubs"])
    print("[OK] Clubs routes loaded")

if CHALLENGES_AVAILABLE and challenges:
    app.include_router(challenges.router, tags=["challenges"])
    print("[OK] Challenges routes loaded")

if VIDEOS_AVAILABLE and videos:
    app.include_router(videos.router, tags=["videos"])
    print("[OK] Videos routes loaded")

if PAYMENTS_AVAILABLE and payments:
    app.include_router(payments.router)
    print("[OK] Payments routes loaded")
