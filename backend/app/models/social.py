import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col, str_enum, updated_at_col, uuid_pk
from app.models.enums import ModerationActionType, ReportReason, ReportStatus, Visibility
from app.models.user import User


class Subscription(Base):
    __tablename__ = "subscriptions"

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        PrimaryKeyConstraint("subscriber_id", "channel_id"),
        Index("ix_subscriptions_channel_id", "channel_id"),
    )


class VideoReaction(Base):
    """Like (+1) or dislike (-1). One reaction per user per video (composite PK)."""

    __tablename__ = "video_reactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "video_id"),
        CheckConstraint("value IN (-1, 1)", name="value_like_or_dislike"),
        Index("ix_video_reactions_video_id", "video_id"),
        # "Liked videos" page: user's likes by date.
        Index(
            "ix_video_reactions_user_likes",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("value = 1"),
        ),
    )


class Comment(Base):
    """Comments with one level of replies (as on YouTube): parent_id points to a top-level comment."""

    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    likes_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    replies_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Soft delete keeps the reply thread intact; the body is wiped.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set only by an explicit edit (updated_at also moves on likes/replies counters).
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    author: Mapped[User] = relationship(lazy="raise")

    __table_args__ = (
        CheckConstraint("char_length(body) BETWEEN 1 AND 5000", name="body_length"),
        CheckConstraint("likes_count >= 0 AND replies_count >= 0", name="counters_non_negative"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_self_parent"),
        Index(
            "ix_comments_video_top",
            "video_id",
            text("created_at DESC"),
            postgresql_where=text("parent_id IS NULL"),
        ),
        Index(
            "ix_comments_parent", "parent_id", "created_at", postgresql_where=text("parent_id IS NOT NULL")
        ),
        Index("ix_comments_author_id", "author_id"),
    )


class CommentReaction(Base):
    __tablename__ = "comment_reactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    comment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "comment_id"),
        CheckConstraint("value IN (-1, 1)", name="value_like_or_dislike"),
        Index("ix_comment_reactions_comment_id", "comment_id"),
    )


class VideoView(Base):
    """Raw view events (append-only). Dedup window is enforced in Redis before insert;
    this table is the source for analytics and can be partitioned by month later."""

    __tablename__ = "video_views"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    viewer_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256(ip + UA), not the raw IP
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_video_views_video_created", "video_id", "created_at"),)


class WatchHistory(Base):
    """Last time the user watched a video (one row per user+video), drives the History page."""

    __tablename__ = "watch_history"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    position_seconds: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    watched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "video_id"),
        Index("ix_watch_history_user_watched", "user_id", text("watched_at DESC")),
    )


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[uuid.UUID] = uuid_pk()
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    visibility: Mapped[Visibility] = mapped_column(
        str_enum(Visibility, "playlist_visibility"), nullable=False, server_default=Visibility.PUBLIC.value
    )
    items_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    __table_args__ = (
        CheckConstraint("char_length(title) >= 1", name="title_not_empty"),
        CheckConstraint("items_count >= 0", name="items_non_negative"),
        Index("ix_playlists_channel_id", "channel_id"),
    )


class PlaylistItem(Base):
    __tablename__ = "playlist_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    playlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("playlist_id", "video_id", name="uq_playlist_items_playlist_video"),
        Index("ix_playlist_items_playlist_position", "playlist_id", "position"),
        Index("ix_playlist_items_video_id", "video_id"),
        CheckConstraint("position >= 0", name="position_non_negative"),
    )


class Report(Base):
    """User complaint about a video or a comment (exactly one target)."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    video_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE")
    )
    comment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE")
    )
    reason: Mapped[ReportReason] = mapped_column(str_enum(ReportReason, "report_reason"), nullable=False)
    details: Mapped[str] = mapped_column(String(1000), nullable=False, server_default="")
    status: Mapped[ReportStatus] = mapped_column(
        str_enum(ReportStatus, "report_status"), nullable=False, server_default=ReportStatus.OPEN.value
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("num_nonnulls(video_id, comment_id) = 1", name="exactly_one_target"),
        Index("ix_reports_open", "created_at", postgresql_where=text("status = 'open'")),
        Index("ix_reports_video_id", "video_id"),
        Index("ix_reports_comment_id", "comment_id"),
        # One open report per user per target: no spamming the queue.
        Index(
            "uq_reports_open_per_user_video",
            "reporter_id",
            "video_id",
            unique=True,
            postgresql_where=text("status = 'open' AND video_id IS NOT NULL"),
        ),
        Index(
            "uq_reports_open_per_user_comment",
            "reporter_id",
            "comment_id",
            unique=True,
            postgresql_where=text("status = 'open' AND comment_id IS NOT NULL"),
        ),
    )


class ModerationAction(Base):
    """What a moderator/admin did and why. Never deleted: this is the moderation audit trail."""

    __tablename__ = "moderation_actions"

    id: Mapped[uuid.UUID] = uuid_pk()
    moderator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[ModerationActionType] = mapped_column(
        str_enum(ModerationActionType, "moderation_action_type"), nullable=False
    )
    video_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="SET NULL")
    )
    comment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="SET NULL")
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_moderation_actions_created_at", text("created_at DESC")),
        Index("ix_moderation_actions_video_id", "video_id"),
    )
