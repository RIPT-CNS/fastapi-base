import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from app.models.model_base import Base, BareBaseModel

class Document(BareBaseModel):
    __tablename__ = "document"

    thread_id = Column(PG_UUID(as_uuid=True), ForeignKey("thread.id"), nullable=False)
    name = Column(String, nullable=False)  # Tên file hoặc tiêu đề
    source_type = Column(String, nullable=False)  # 'pdf', 'docx', 'url', 'text', ...
    source_info = Column(JSON, nullable=True)  # Lưu path, url, metadata
    content = Column(Text, nullable=True)  # Nội dung văn bản đầy đủ (tùy chọn)
    
    thread = relationship("Thread", back_populates="documents")
