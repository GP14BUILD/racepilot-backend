import requests, json, random
from datetime import datetime, timedelta, timezone
import math

BASE = "http://127.0.0.1:8000"
print("Creating user...")
u = requests.post(f"{BASE}/auth/register", json={"email":"kevin@example.com","name":"Kevin","password":"secret"}).json()
uid = u.get("id",1)
print("User:", u)

print("Creating session...")
start = datetime.now(timezone.utc)
s = requests.post(f"{BASE}/sessions", json={"user_id": uid, "boat_id": 1, "title":"Demo Race", "start_ts": start.isoformat()}).json()
sid = s["id"]
print("Session:", s)

# Generate a small loop of points near Cowes, UK
lat, lon = 50.763, -1.297
points = []
for i in range(120):
    t = start + timedelta(seconds=i)
    hdg = (220 + i*0.5) % 360
    sog = 6.5 + 0.2*math.sin(i/10)
    awa = 30 + 10*math.sin(i/15)
    aws = 12 + 1.5*math.cos(i/20)
    # move roughly south-west
    dms = sog * 0.514444
    lat += (dms * math.cos(math.radians(hdg))) / 111320
    lon += (dms * math.sin(math.radians(hdg))) / (111320*math.cos(math.radians(lat)))
    points.append({
        "ts": t.isoformat(),
        "lat": lat, "lon": lon,
        "sog": sog, "cog": hdg,
        "awa": awa, "aws": aws, "hdg": hdg,
        "tws": 12.0, "twa": 40.0
    })

print("Posting telemetry...")
r = requests.post(f"{BASE}/telemetry/ingest", json={"session_id": sid, "points": points})
print("Ingest response:", r.json())

print("Uploading polar... (insert directly into DB not implemented via API for MVP)")
print("Place polars/demo_polar.json into DB manually for advanced use; using demo id=1 assumptions.")

print("Compute start-line bias...")
bias = requests.post(f"{BASE}/analytics/start-line/bias", json={
    "pin_lat": 50.761, "pin_lon": -1.30,
    "com_lat": 50.762, "com_lon": -1.295,
    "twd": 230
}).json()
print("Bias:", bias)

print("Compute TTL...")
ttl = requests.post(f"{BASE}/analytics/start-line/ttl", json={"sog":6.2, "distance_m":150}).json()
print("TTL:", ttl)

print("Compute laylines (requires polar id=1)...")
lay = requests.post(f"{BASE}/analytics/laylines", json={
    "session_id": sid,
    "mark_lat": 50.75, "mark_lon": -1.28,
    "twd": 230, "tws": 12, "polar_id": 1
}).json()
print("Laylines:", lay)
