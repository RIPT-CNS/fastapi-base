from pydantic import BaseModel
from uuid import UUID

class ThreadCreate(BaseModel):
    user_id: int
    title: str

class ThreadOut(BaseModel):
    id: int
    title: str
    status: str

    class Config:
        orm_mode = True
