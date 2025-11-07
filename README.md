# RacePilot Backend (MVP)

FastAPI backend implementing sessions, telemetry ingest, and core tactical analytics
(VMG target, layline estimate, start-line bias & time-to-line). Uses SQLite for quick local runs.
A Postgres/PostGIS docker-compose is included but optional for the MVP.

## Quick Start (Local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API: http://127.0.0.1:8000/docs

## Generate demo data and run a sample session

```bash
python scripts/generate_demo_data.py
```

This will post a mock session + telemetry to the running API and print analytics.

## Optional: Docker

```bash
docker build -t racepilot-backend .
docker run -p 8000:8000 racepilot-backend
```

(For Postgres/PostGIS, see `docker-compose.yml` and adapt `DATABASE_URL`).
