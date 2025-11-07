from fastapi import APIRouter, HTTPException
from ..db.models import SessionLocal, User
from ..schemas import RegisterRequest
from passlib.hash import bcrypt

router = APIRouter()

@router.post("/register")
def register(req: RegisterRequest):
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email==req.email).first():
            raise HTTPException(status_code=400, detail="Email already registered")
        u = User(email=req.email, name=req.name, password_hash=bcrypt.hash(req.password))
        db.add(u); db.commit(); db.refresh(u)
        return {"id": u.id, "email": u.email, "name": u.name}
    finally:
        db.close()
