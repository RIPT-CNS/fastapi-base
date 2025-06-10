from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from app.models.model_base import BareBaseModel

class VectorSession(BareBaseModel):
    __tablename__ = "vector_session"

    thread_id = Column(PG_UUID(as_uuid=True), ForeignKey("thread.id"), nullable=False, unique=True)
    vector_path = Column(String, nullable=False)  # Đường dẫn tới FAISS index đã lưu
    embed_model = Column(String, nullable=True)   # Ghi lại model đã dùng (nếu cần)

    thread = relationship("Thread", back_populates="vector_session")
