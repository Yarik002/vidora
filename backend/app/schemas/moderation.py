import uuid
from datetime import datetime

from pydantic import Field, model_validator

from app.models.enums import ModerationState, ReportReason, ReportStatus, Role
from app.schemas.common import ApiModel
from app.schemas.video import VideoCard


class ReportIn(ApiModel):
    video_id: uuid.UUID | None = None
    comment_id: uuid.UUID | None = None
    reason: ReportReason
    details: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def exactly_one_target(self) -> "ReportIn":
        if (self.video_id is None) == (self.comment_id is None):
            raise ValueError("specify exactly one of video_id or comment_id")
        return self


class ReportCreated(ApiModel):
    id: uuid.UUID
    status: ReportStatus


class ReportedComment(ApiModel):
    id: uuid.UUID
    body: str | None
    author: str | None
    video_id: uuid.UUID


class ReportOut(ApiModel):
    id: uuid.UUID
    reason: ReportReason
    details: str
    status: ReportStatus
    created_at: datetime
    reporter: str | None
    video: VideoCard | None
    video_moderation_state: ModerationState | None
    comment: ReportedComment | None
    reports_on_target: int


class ModerationDecision(ApiModel):
    reason: str = Field(default="", max_length=500)
    report_id: uuid.UUID | None = None


class ModerationActionOut(ApiModel):
    id: uuid.UUID
    action: str
    moderator: str | None
    reason: str
    created_at: datetime
    video_id: uuid.UUID | None
    video_title: str | None
    comment_id: uuid.UUID | None
    target_user: str | None


class AdminUserOut(ApiModel):
    id: uuid.UUID
    username: str
    email: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    videos_count: int


class AdminUserUpdate(ApiModel):
    role: Role | None = None
    is_active: bool | None = None
    reason: str = Field(default="", max_length=500)
