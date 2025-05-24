from sqlalchemy import Column, String, Boolean, Float
from sqlalchemy.dialects.postgresql import ARRAY

from app.models.model_base import BareBaseModel


class User(BareBaseModel):
    
    __tablename__ = "users"
    
    sso_sub = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    dob = Column(Float, index=True)
    gender = Column(String, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    full_name = Column(String, index=True)
    phone = Column(String, index=True)
    address = Column(String, index=True)
    identity_card = Column(String, index=True)
    identity_card_date = Column(Float, index=True)
    identity_card_place = Column(String, index=True)
    is_active = Column(Boolean, default=True)
    last_login = Column(Float)
    hashed_password = Column(String(255))
    roles = Column(ARRAY(String), default=list)
