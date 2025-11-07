from app.db.models import SessionLocal, Polar, init_db
import json

def main():
    init_db()
    db = SessionLocal()
    try:
        with open("polars/demo_polar.json") as f:
            data = json.load(f)
        p = Polar(boat_id=1, data_json=data)
        db.add(p)
        db.commit()
        print("Inserted demo polar with id:", p.id)
    finally:
        db.close()

if __name__ == "__main__":
    main()
