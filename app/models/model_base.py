from datetime import datetime

from sqlalchemy import Column, Integer, Float
from sqlalchemy.ext.declarative import as_declarative, declared_attr


@as_declarative()
class Base:
    __abstract__ = True
    __name__: str

    # Generate __tablename__ automatically
    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower()


class BareBaseModel(Base):
    __abstract__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(Float, default=datetime.now().timestamp)
    updated_at = Column(
        Float, default=datetime.now().timestamp, onupdate=datetime.now().timestamp
    )
