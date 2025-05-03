from typing import Optional

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "Bearer"


class TokenPayload(BaseModel):
    user_id: Optional[int] = None
