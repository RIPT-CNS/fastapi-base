import uuid
from datetime import datetime

from sqlalchemy import Column, Text, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.model_base import Base, BareBaseModel
from app.utils.enums import SenderType

class Message(BareBaseModel):
    __tablename__ = "message"

    thread_id = Column(PG_UUID(as_uuid=True), ForeignKey("thread.id"), nullable=False)
    sender = Column(Enum(SenderType), nullable=False)
    content = Column(Text, nullable=True)
    meta_info  = Column(JSON, nullable=True)

    thread = relationship("Thread", back_populates="messages")
    feedbacks = relationship("Feedback", back_populates="message")