# schemas/document.py
from pydantic import BaseModel, HttpUrl
from typing import Optional
from uuid import UUID

class DocumentInput(BaseModel):
    name: str
    source_type: str  # 'file', 'url', 'text'
    source_info: dict | None = None
    content: str | None = None

class DocumentCreateMulti(BaseModel):
    thread_id: int
    documents: list[DocumentInput]

class DocumentOut(BaseModel):
    id: int
    thread_id: int
    name: str
    source_type: str
    source_info: dict | None = None
    content: str | None = None

    class Config:
        orm_mode = True
