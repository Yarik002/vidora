import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import ApiModel


class CommentAuthor(ApiModel):
    id: uuid.UUID
    username: str
    channel_handle: str
    channel_title: str
    avatar_color: str


class CommentOut(ApiModel):
    id: uuid.UUID
    video_id: uuid.UUID
    parent_id: uuid.UUID | None
    body: str | None  # None when deleted
    author: CommentAuthor | None
    likes_count: int
    replies_count: int
    created_at: datetime
    edited: bool
    is_deleted: bool
    is_video_owner: bool  # author is the channel owner (highlighted like on YouTube)
    my_reaction: int = 0
    can_edit: bool = False
    can_delete: bool = False


class CommentIn(ApiModel):
    body: str = Field(min_length=1, max_length=5000)
    parent_id: uuid.UUID | None = None

    @field_validator("body")
    @classmethod
    def strip_body(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("comment is empty")
        return v


class CommentUpdate(ApiModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def strip_body(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("comment is empty")
        return v


class CommentReactionIn(ApiModel):
    value: Literal[0, 1]
