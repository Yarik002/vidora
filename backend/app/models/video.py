import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col, str_enum, updated_at_col, uuid_pk
from app.models.enums import FileKind, JobStatus, ModerationState, UploadStatus, VideoStatus, Visibility
from app.models.user import Channel


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = uuid_pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    visibility: Mapped[Visibility] = mapped_column(
        str_enum(Visibility, "visibility"), nullable=False, server_default=Visibility.PUBLIC.value
    )
    status: Mapped[VideoStatus] = mapped_column(
        str_enum(VideoStatus, "video_status"), nullable=False, server_default=VideoStatus.UPLOADING.value
    )
    moderation_state: Mapped[ModerationState] = mapped_column(
        str_enum(ModerationState, "moderation_state"),
        nullable=False,
        server_default=ModerationState.ACTIVE.value,
    )
    processing_error: Mapped[str | None] = mapped_column(String(500))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    # Denormalized counters: updated in the same transaction as the source rows,
    # so the feed never runs COUNT(*) over reactions/comments/views.
    views_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    likes_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    dislikes_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    comments_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    # Full-text search: generated column, title weighs more than description.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('russian', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('russian', coalesce(description, '')), 'B')",
            persisted=True,
        ),
    )

    channel: Mapped[Channel] = relationship(lazy="raise")
    files: Mapped[list["VideoFile"]] = relationship(
        back_populates="video", lazy="raise", passive_deletes=True
    )
    thumbnails: Mapped[list["Thumbnail"]] = relationship(
        back_populates="video", lazy="raise", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            "views_count >= 0 AND likes_count >= 0 AND dislikes_count >= 0 AND comments_count >= 0",
            name="counters_non_negative",
        ),
        CheckConstraint("char_length(title) >= 1", name="title_not_empty"),
        # Feed: public, ready, active videos by date. Partial index = only rows the feed can show.
        Index(
            "ix_videos_feed",
            text("published_at DESC"),
            postgresql_where=text(
                "status = 'ready' AND visibility = 'public' AND moderation_state = 'active'"
            ),
        ),
        Index("ix_videos_channel_created", "channel_id", text("created_at DESC")),
        Index("ix_videos_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_videos_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "ix_videos_moderation_hidden",
            "moderation_state",
            postgresql_where=text("moderation_state = 'hidden'"),
        ),
    )


class VideoFile(Base):
    """Physical objects in S3: the original upload and transcoded renditions (720p, 360p)."""

    __tablename__ = "video_files"

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[FileKind] = mapped_column(str_enum(FileKind, "file_kind"), nullable=False)
    quality: Mapped[str] = mapped_column(String(16), nullable=False)  # "original", "720p", "360p"
    bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    bitrate: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_col()

    video: Mapped[Video] = relationship(back_populates="files", lazy="raise")

    __table_args__ = (
        UniqueConstraint("video_id", "quality", name="uq_video_files_video_quality"),
        UniqueConstraint("bucket", "object_key", name="uq_video_files_object"),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
    )


class Thumbnail(Base):
    __tablename__ = "thumbnails"

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primary: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = created_at_col()

    video: Mapped[Video] = relationship(back_populates="thumbnails", lazy="raise")

    __table_args__ = (
        # At most one primary thumbnail per video.
        Index("uq_thumbnails_primary", "video_id", unique=True, postgresql_where=text("is_primary")),
    )


class UploadSession(Base):
    """S3 multipart upload in progress: the browser uploads parts directly to storage."""

    __tablename__ = "upload_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    s3_upload_id: Mapped[str] = mapped_column(String(255), nullable=False)
    bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    part_size: Mapped[int] = mapped_column(Integer, nullable=False)
    parts_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[UploadStatus] = mapped_column(
        str_enum(UploadStatus, "upload_status"), nullable=False, server_default=UploadStatus.PENDING.value
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("declared_size > 0", name="size_positive"),
        CheckConstraint("parts_count BETWEEN 1 AND 10000", name="parts_range"),
        Index("ix_upload_sessions_pending", "expires_at", postgresql_where=text("status = 'pending'")),
    )


class ProcessingJob(Base):
    """History of processing attempts (worker runs), useful for debugging failed videos."""

    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus, "job_status"), nullable=False, server_default=JobStatus.QUEUED.value
    )
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    error: Mapped[str | None] = mapped_column(String(1000))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_processing_jobs_video_id", "video_id"),)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)

    __table_args__ = (CheckConstraint("char_length(name) BETWEEN 1 AND 40", name="name_length"),)


class VideoTag(Base):
    __tablename__ = "video_tags"

    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("video_id", "tag_id"),
        Index("ix_video_tags_tag_id", "tag_id"),
    )


class VideoAccessGrant(Base):
    """Who may watch a private video besides its owner."""

    __tablename__ = "video_access_grants"

    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        PrimaryKeyConstraint("video_id", "user_id"),
        Index("ix_video_access_grants_user_id", "user_id"),
    )
