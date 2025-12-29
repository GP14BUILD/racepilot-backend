"""
API routes for boat class management.

Endpoints:
- GET /boat-classes - List all boat classes (pre-populated + custom)
- GET /boat-classes/{id} - Get specific boat class details
- POST /boat-classes - Create custom boat class (authenticated)
- PUT /boat-classes/{id} - Update custom boat class (owner only)
- DELETE /boat-classes/{id} - Delete custom boat class (owner only)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession
from typing import List

from app.db.models import BoatClass, User
from app.schemas import BoatClassCreate, BoatClassOut
from app.auth import get_current_user
from app.db.models import SessionLocal

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("", response_model=List[BoatClassOut])
def list_boat_classes(
    db: DbSession = Depends(get_db)
):
    """
    List all boat classes (both pre-populated and custom).

    Returns boat classes sorted by Portsmouth Yardstick rating (fastest first).
    Pre-populated classes appear before custom classes.
    """
    boat_classes = db.query(BoatClass).order_by(
        BoatClass.is_custom.asc(),  # Pre-populated first
        BoatClass.portsmouth_yardstick.asc()  # Then by speed (lowest PY = fastest)
    ).all()

    return boat_classes

@router.get("/{boat_class_id}", response_model=BoatClassOut)
def get_boat_class(
    boat_class_id: int,
    db: DbSession = Depends(get_db)
):
    """Get detailed information for a specific boat class."""
    boat_class = db.query(BoatClass).filter(BoatClass.id == boat_class_id).first()

    if not boat_class:
        raise HTTPException(status_code=404, detail="Boat class not found")

    return boat_class

@router.post("", response_model=BoatClassOut)
def create_boat_class(
    boat_class_data: BoatClassCreate,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db)
):
    """
    Create a custom boat class.

    Users can create custom boat classes for boats not in the pre-populated database.
    Custom classes can include full performance specifications or just basic info.
    """
    # Check if boat class name already exists
    existing = db.query(BoatClass).filter(BoatClass.name == boat_class_data.name).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Boat class '{boat_class_data.name}' already exists"
        )

    # Create new boat class
    new_boat_class = BoatClass(
        **boat_class_data.model_dump(),
        is_custom=True,
        created_by_user_id=current_user.id
    )

    db.add(new_boat_class)
    db.commit()
    db.refresh(new_boat_class)

    return new_boat_class

@router.put("/{boat_class_id}", response_model=BoatClassOut)
def update_boat_class(
    boat_class_id: int,
    updates: BoatClassCreate,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db)
):
    """
    Update a custom boat class.

    Only the user who created the custom boat class can update it.
    Pre-populated boat classes cannot be edited.
    """
    boat_class = db.query(BoatClass).filter(BoatClass.id == boat_class_id).first()

    if not boat_class:
        raise HTTPException(status_code=404, detail="Boat class not found")

    # Only custom boat classes can be edited
    if not boat_class.is_custom:
        raise HTTPException(
            status_code=403,
            detail="Pre-populated boat classes cannot be edited. Create a custom class instead."
        )

    # Only the creator can edit their custom boat class (or admin)
    if boat_class.created_by_user_id != current_user.id and current_user.role != 'admin':
        raise HTTPException(
            status_code=403,
            detail="You can only edit boat classes you created"
        )

    # Update fields
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(boat_class, field, value)

    db.commit()
    db.refresh(boat_class)

    return boat_class

@router.delete("/{boat_class_id}")
def delete_boat_class(
    boat_class_id: int,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db)
):
    """
    Delete a custom boat class.

    Only the user who created the custom boat class can delete it.
    Pre-populated boat classes cannot be deleted.
    Boat class must not be in use by any boats.
    """
    boat_class = db.query(BoatClass).filter(BoatClass.id == boat_class_id).first()

    if not boat_class:
        raise HTTPException(status_code=404, detail="Boat class not found")

    # Only custom boat classes can be deleted
    if not boat_class.is_custom:
        raise HTTPException(
            status_code=403,
            detail="Pre-populated boat classes cannot be deleted"
        )

    # Only the creator can delete their custom boat class (or admin)
    if boat_class.created_by_user_id != current_user.id and current_user.role != 'admin':
        raise HTTPException(
            status_code=403,
            detail="You can only delete boat classes you created"
        )

    # Check if any boats are using this boat class
    if boat_class.boats:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete boat class. {len(boat_class.boats)} boat(s) are using this class."
        )

    db.delete(boat_class)
    db.commit()

    return {"message": "Boat class deleted successfully"}
