from pydantic import BaseModel


class AuthResult(BaseModel):
    token: str | None = None
