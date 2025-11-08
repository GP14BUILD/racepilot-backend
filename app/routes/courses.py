from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db.models import SessionLocal, RaceCourse, RaceMark, StartLine
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Schemas
class RaceMarkCreate(BaseModel):
    name: str
    lat: float
    lon: float
    mark_type: str
    color: Optional[str] = '#FF6B6B'
    sequence: int
    shape: Optional[str] = 'circle'

class RaceMarkResponse(RaceMarkCreate):
    id: int
    course_id: int

class RaceCourseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    created_by: int
    config_json: Optional[dict] = {}
    marks: List[RaceMarkCreate]

class RaceCourseResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_by: int
    created_at: datetime
    config_json: dict
    marks: List[RaceMarkResponse]

class StartLineCreate(BaseModel):
    course_id: int
    pin_lat: float
    pin_lon: float
    boat_lat: float
    boat_lon: float

class StartLineResponse(StartLineCreate):
    id: int
    line_heading: float
    favored_end: Optional[str]
    bias_degrees: Optional[float]

# Routes
@router.post("/courses", response_model=RaceCourseResponse)
def create_race_course(course: RaceCourseCreate, db: Session = Depends(get_db)):
    """Create a new race course with marks"""
    db_course = RaceCourse(
        name=course.name,
        description=course.description,
        created_by=course.created_by,
        created_at=datetime.now(),
        config_json=course.config_json or {}
    )
    db.add(db_course)
    db.flush()  # Get the course ID

    # Add marks
    for mark_data in course.marks:
        db_mark = RaceMark(
            course_id=db_course.id,
            name=mark_data.name,
            lat=mark_data.lat,
            lon=mark_data.lon,
            mark_type=mark_data.mark_type,
            color=mark_data.color,
            sequence=mark_data.sequence,
            shape=mark_data.shape
        )
        db.add(db_mark)

    db.commit()
    db.refresh(db_course)

    # Fetch marks
    marks = db.query(RaceMark).filter(RaceMark.course_id == db_course.id).all()

    return {
        "id": db_course.id,
        "name": db_course.name,
        "description": db_course.description,
        "created_by": db_course.created_by,
        "created_at": db_course.created_at,
        "config_json": db_course.config_json,
        "marks": [{
            "id": m.id,
            "course_id": m.course_id,
            "name": m.name,
            "lat": m.lat,
            "lon": m.lon,
            "mark_type": m.mark_type,
            "color": m.color,
            "sequence": m.sequence,
            "shape": m.shape
        } for m in marks]
    }

@router.get("/courses", response_model=List[RaceCourseResponse])
def get_race_courses(db: Session = Depends(get_db)):
    """Get all race courses"""
    courses = db.query(RaceCourse).all()
    result = []
    for course in courses:
        marks = db.query(RaceMark).filter(RaceMark.course_id == course.id).all()
        result.append({
            "id": course.id,
            "name": course.name,
            "description": course.description,
            "created_by": course.created_by,
            "created_at": course.created_at,
            "config_json": course.config_json,
            "marks": [{
                "id": m.id,
                "course_id": m.course_id,
                "name": m.name,
                "lat": m.lat,
                "lon": m.lon,
                "mark_type": m.mark_type,
                "color": m.color,
                "sequence": m.sequence,
                "shape": m.shape
            } for m in marks]
        })
    return result

@router.get("/courses/{course_id}", response_model=RaceCourseResponse)
def get_race_course(course_id: int, db: Session = Depends(get_db)):
    """Get a specific race course with all marks"""
    course = db.query(RaceCourse).filter(RaceCourse.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    marks = db.query(RaceMark).filter(RaceMark.course_id == course_id).all()
    return {
        "id": course.id,
        "name": course.name,
        "description": course.description,
        "created_by": course.created_by,
        "created_at": course.created_at,
        "config_json": course.config_json,
        "marks": [{
            "id": m.id,
            "course_id": m.course_id,
            "name": m.name,
            "lat": m.lat,
            "lon": m.lon,
            "mark_type": m.mark_type,
            "color": m.color,
            "sequence": m.sequence,
            "shape": m.shape
        } for m in marks]
    }

@router.post("/start-lines", response_model=StartLineResponse)
def create_start_line(start_line: StartLineCreate, db: Session = Depends(get_db)):
    """Create a start line with bias calculation"""
    import math

    # Calculate line heading
    lat1, lon1 = math.radians(start_line.pin_lat), math.radians(start_line.pin_lon)
    lat2, lon2 = math.radians(start_line.boat_lat), math.radians(start_line.boat_lon)

    d_lon = lon2 - lon1
    x = math.sin(d_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    bearing = math.degrees(math.atan2(x, y))
    line_heading = (bearing + 360) % 360

    db_start_line = StartLine(
        course_id=start_line.course_id,
        pin_lat=start_line.pin_lat,
        pin_lon=start_line.pin_lon,
        boat_lat=start_line.boat_lat,
        boat_lon=start_line.boat_lon,
        line_heading=line_heading
    )
    db.add(db_start_line)
    db.commit()
    db.refresh(db_start_line)

    return db_start_line

@router.get("/start-lines/{course_id}", response_model=StartLineResponse)
def get_start_line(course_id: int, db: Session = Depends(get_db)):
    """Get start line for a course"""
    start_line = db.query(StartLine).filter(StartLine.course_id == course_id).first()
    if not start_line:
        raise HTTPException(status_code=404, detail="Start line not found")
    return start_line
