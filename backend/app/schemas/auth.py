import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.models.enums import Role
from app.schemas.common import ApiModel

USERNAME_PATTERN = r"^[A-Za-z0-9_.-]{3,30}$"


class RegisterIn(ApiModel):
    email: EmailStr
    username: str = Field(pattern=USERNAME_PATTERN, description="3-30 chars: letters, digits, _ . -")
    password: str = Field(min_length=8, max_length=128)
    channel_title: str | None = Field(default=None, max_length=100)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if v.isdigit() or v.isalpha():
            raise ValueError("password must contain both letters and digits or symbols")
        return v


class LoginIn(ApiModel):
    login: str = Field(min_length=1, max_length=254, description="email or username")
    password: str = Field(min_length=1, max_length=128)


class TokenOut(ApiModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret


class ChannelBrief(ApiModel):
    id: uuid.UUID
    handle: str
    title: str
    avatar_color: str
    subscribers_count: int = 0


class MeOut(ApiModel):
    id: uuid.UUID
    email: str
    username: str
    role: Role
    created_at: datetime
    channel: ChannelBrief
