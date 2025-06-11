from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import uuid4
from app.models.model_thread import Thread
from app.models.model_vector_session import VectorSession
from app.core.database import get_db
from app.schemas.sche_vector_session import VectorSessionCreate, VectorSessionOut
from pathlib import Path
from fastapi import HTTPException

router = APIRouter(prefix=f"/vectorstore")

@router.post("/create", response_model=VectorSessionOut)
def create_vector_session(data: VectorSessionCreate, db: Session = Depends(get_db)):
    # Tạo thư mục lưu vectorstore
    vectorstore_path = Path(data.vector_path) / str(data.thread_id)
    vectorstore_path.mkdir(parents=True, exist_ok=True)
    # Kiểm tra thread tồn tại
    thread = db.query(Thread).filter(Thread.id == data.thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    # Ghi thông tin vectorstore
    vector_session = VectorSession(
        thread_id=data.thread_id,
        vector_path=str(vectorstore_path),
        embed_model=data.embed_model
    )
    db.add(vector_session)

    db.commit()
    db.refresh(vector_session)
    return vector_session
