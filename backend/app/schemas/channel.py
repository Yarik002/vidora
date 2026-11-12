import uuid
from datetime import datetime

from pydantic import Field

from app.models.enums import ModerationState, Visibility
from app.schemas.auth import ChannelBrief
from app.schemas.common import ApiModel
from app.schemas.video import VideoCard


class ChannelDetail(ChannelBrief):
    description: str
    created_at: datetime
    videos_count: int
    is_subscribed: bool = False
    is_owner: bool = False


class ChannelUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    avatar_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class SubscriptionOut(ApiModel):
    subscribed: bool
    subscribers_count: int


class StudioVideo(VideoCard):
    likes_count: int
    comments_count: int
    moderation_state: ModerationState
    processing_error: str | None


class PlaylistOut(ApiModel):
    id: uuid.UUID
    title: str
    description: str
    visibility: Visibility
    items_count: int
    thumbnail_url: str | None
    channel: ChannelBrief
    updated_at: datetime
    contains_video: bool | None = None


class PlaylistDetail(PlaylistOut):
    videos: list[VideoCard]
    is_owner: bool


class PlaylistCreate(ApiModel):
    title: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=5000)
    visibility: Visibility = Visibility.PUBLIC


class PlaylistUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=5000)
    visibility: Visibility | None = None


class PlaylistAdd(ApiModel):
    video_id: uuid.UUID
