from typing import Optional, List
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from app.utils.enums import SenderType

class MessageRequest(BaseModel):
    message: str
    user_id: Optional[int] = None
    thread_id: Optional[int] = None

class MessageResponse(BaseModel):
    id: int
    thread_id: int
    sender: SenderType
    content: Optional[str]
    meta_info: Optional[dict]
    created_at: datetime

    class Config:
        orm_mode = True
