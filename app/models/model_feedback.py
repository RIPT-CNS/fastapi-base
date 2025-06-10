import uuid
from datetime import datetime

from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.model_base import Base, BareBaseModel

class Feedback(BareBaseModel):
    __tablename__ = "feedback"

    message_id = Column(PG_UUID(as_uuid=True), ForeignKey("message.id"), nullable=False)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)

    message = relationship("Message", back_populates="feedbacks")
    user = relationship("Users", back_populates="feedbacks")