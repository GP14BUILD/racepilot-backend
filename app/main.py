from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db.models import init_db
from .routes import auth, sessions, telemetry, analytics, ai, courses

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

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(courses.router, prefix="/courses", tags=["courses"])

# ✅ AI endpoints
app.include_router(ai.router, prefix="/ai", tags=["ai"])
