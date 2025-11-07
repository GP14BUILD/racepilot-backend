from fastapi import FastAPI
from .db.models import init_db
from .routes import auth, sessions, telemetry, analytics, ai

app = FastAPI(title="RacePilot API", version="0.1.0")

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])

# ✅ AI endpoints
app.include_router(ai.router, prefix="/ai", tags=["ai"])
