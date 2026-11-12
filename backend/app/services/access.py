"""Single source of truth for "who may see which video".

Every endpoint that returns a video or anything attached to it (stream, thumbnails, comments,
reactions, playlists) goes through these functions, so the rules cannot drift apart.

Rules:
* staff (moderator, admin) see everything, including hidden and private videos;
* the owner sees all own videos in any state;
* everyone else: only ready + active videos that are public or unlisted,
  or private ones with an explicit grant.
Listings (feed, search, channel page, related) show only public videos.
"""

import uuid

from sqlalchemy import ColumnElement, and_, exists, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.models import ModerationState, Role, User, Video, VideoAccessGrant, VideoStatus, Visibility


def is_staff(user: User | None) -> bool:
    return user is not None and user.role in (Role.MODERATOR, Role.ADMIN)


def is_owner(user: User | None, video: Video) -> bool:
    return user is not None and user.channel is not None and video.channel_id == user.channel.id


async def has_grant(session: AsyncSession, video_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return bool(
        await session.scalar(
            select(exists().where(VideoAccessGrant.video_id == video_id, VideoAccessGrant.user_id == user_id))
        )
    )


async def can_view(session: AsyncSession, video: Video, user: User | None) -> bool:
    if is_staff(user) or is_owner(user, video):
        return True
    if video.status != VideoStatus.READY or video.moderation_state != ModerationState.ACTIVE:
        return False
    if video.visibility in (Visibility.PUBLIC, Visibility.UNLISTED):
        return True
    return user is not None and await has_grant(session, video.id, user.id)


async def get_viewable_video(session: AsyncSession, video_id: uuid.UUID, user: User | None) -> Video:
    """Returns the video or raises 404. 404 (not 403) so private videos don't leak their existence."""
    video = await session.get(Video, video_id)
    if video is None or not await can_view(session, video, user):
        raise NotFound("Video not found", code="video_not_found")
    return video


def listed_condition() -> ColumnElement[bool]:
    """Videos that may appear in public listings."""
    return and_(
        Video.status == VideoStatus.READY,
        Video.visibility == Visibility.PUBLIC,
        Video.moderation_state == ModerationState.ACTIVE,
    )


def viewable_condition(user: User | None) -> ColumnElement[bool]:
    """SQL version of can_view() for lists that may contain non-public videos (playlists, history)."""
    if is_staff(user):
        return true()
    public_part = and_(
        Video.status == VideoStatus.READY,
        Video.moderation_state == ModerationState.ACTIVE,
        Video.visibility.in_([Visibility.PUBLIC, Visibility.UNLISTED]),
    )
    if user is None:
        return public_part
    owner_part = Video.channel_id == user.channel.id if user.channel else false()
    grant_part = and_(
        Video.status == VideoStatus.READY,
        Video.moderation_state == ModerationState.ACTIVE,
        Video.visibility == Visibility.PRIVATE,
        exists().where(VideoAccessGrant.video_id == Video.id, VideoAccessGrant.user_id == user.id),
    )
    return or_(public_part, owner_part, grant_part)
