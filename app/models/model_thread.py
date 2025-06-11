import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.model_base import Base, BareBaseModel

class Thread(BareBaseModel):
    __tablename__ = "thread"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=True)
    status = Column(String, nullable=True)

    user = relationship("User", back_populates="threads")
    messages = relationship("Message", back_populates="thread")
    documents = relationship("Document", back_populates="thread")
    vector_session = relationship("VectorSession", uselist=False, back_populates="thread")