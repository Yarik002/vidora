import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.models.enums import ModerationState, VideoStatus, Visibility
from app.schemas.auth import ChannelBrief
from app.schemas.common import ApiModel


class VideoCard(ApiModel):
    id: uuid.UUID
    title: str
    duration_seconds: float | None
    views_count: int
    published_at: datetime | None
    created_at: datetime
    visibility: Visibility
    status: VideoStatus
    thumbnail_url: str | None
    channel: ChannelBrief


class VideoDetail(VideoCard):
    description: str
    likes_count: int
    dislikes_count: int
    comments_count: int
    moderation_state: ModerationState
    processing_error: str | None
    tags: list[str]
    qualities: list[str]
    my_reaction: int = 0
    is_subscribed: bool = False
    is_owner: bool = False


def _clean_tags(tags: list[str] | None) -> list[str] | None:
    if tags is None:
        return None
    seen: dict[str, str] = {}
    for raw in tags:
        tag = raw.strip().lstrip("#")[:30]
        if tag and tag.lower() not in seen:
            seen[tag.lower()] = tag
    return list(seen.values())[:15]


class VideoUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    visibility: Visibility | None = None
    tags: list[str] | None = Field(default=None, max_length=30)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: list[str] | None) -> list[str] | None:
        return _clean_tags(v)


class UploadCreate(ApiModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    content_type: str = Field(default="application/octet-stream", max_length=100)
    title: str | None = Field(default=None, max_length=100)
    description: str = Field(default="", max_length=5000)
    visibility: Visibility = Visibility.PUBLIC
    tags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: list[str]) -> list[str]:
        return _clean_tags(v) or []


class UploadPart(ApiModel):
    part_number: int
    url: str


class UploadOut(ApiModel):
    upload_id: uuid.UUID
    video_id: uuid.UUID
    part_size: int
    parts: list[UploadPart]
    expires_at: datetime


class CompletedPart(ApiModel):
    part_number: int = Field(ge=1, le=10000)
    etag: str = Field(min_length=1, max_length=100)


class UploadComplete(ApiModel):
    parts: list[CompletedPart] = Field(min_length=1, max_length=10000)


class VideoStatusOut(ApiModel):
    id: uuid.UUID
    status: VideoStatus
    processing_error: str | None
    duration_seconds: float | None
    thumbnail_url: str | None


class ReactionIn(ApiModel):
    value: Literal[-1, 0, 1] = Field(description="1 like, -1 dislike, 0 remove")


class ReactionOut(ApiModel):
    likes_count: int
    dislikes_count: int
    my_reaction: int


class AccessGrantIn(ApiModel):
    username: str = Field(min_length=3, max_length=30)


class AccessGrantOut(ApiModel):
    user_id: uuid.UUID
    username: str
    created_at: datetime
