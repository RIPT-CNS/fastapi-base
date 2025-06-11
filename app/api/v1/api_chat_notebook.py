from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.model_message import Message
from app.services.srv_chat_notebook import chat_with_thread, get_chat_history  # bạn đã có
from app.schemas.sche_message import MessageRequest

router = APIRouter(prefix="/chat_notebook")

@router.post("/chat_with_source", response_model=dict)
async def chat_endpoint(req: MessageRequest, db: Session = Depends(get_db)):
    try:
        # Lấy lịch sử trò chuyện từ DB.
        history: List[Message] = get_chat_history(db, thread_id=req.thread_id)
        print(history)

        # Gọi RAG chat + lưu message
        response = await chat_with_thread(
            db=db,
            thread_id=req.thread_id,
            user_id=req.user_id,
            query=req.message,
            history=history
        )
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
