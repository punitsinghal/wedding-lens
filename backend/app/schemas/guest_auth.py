from pydantic import BaseModel


class GuestAuthRequest(BaseModel):
    code: str


class GuestTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
