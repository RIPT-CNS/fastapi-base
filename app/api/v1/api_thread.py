from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import uuid4
from app.models.model_thread import Thread
from app.models.model_vector_session import VectorSession
from app.core.database import get_db
from app.schemas.sche_thread import ThreadCreate, ThreadOut
from pathlib import Path

router = APIRouter(prefix=f"/thread")

@router.post("/create", response_model=ThreadOut)
def create_thread(data: ThreadCreate, db: Session = Depends(get_db)):
    # Tạo thread mới
    new_thread = Thread(
        user_id=data.user_id,
        title=data.title,
        status="active"  # bạn có thể tùy chỉnh status theo nhu cầu
    )
    db.add(new_thread)
    
    db.commit()
    db.refresh(new_thread)
    return new_thread
