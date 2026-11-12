"""Read-only video lists: home feed, channel videos, search, related, subscriptions, history,
liked videos and the studio. Routers call these; SQL lives in repositories/videos.py."""

import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, WatchHistory
from app.repositories import videos as videos_repo
from app.schemas.channel import StudioVideo
from app.schemas.common import Page
from app.schemas.video import VideoCard
from app.services.access import get_viewable_video
from app.services.presenters import card_page, channel_brief, thumbnail_url


async def home(session: AsyncSession, host: str, offset: int, limit: int, tag: str | None) -> Page[VideoCard]:
    return card_page(host, await videos_repo.list_feed(session, offset, limit, tag), offset, limit)


async def popular_tags(session: AsyncSession) -> list[str]:
    return await videos_repo.popular_tags(session, 15)


async def channel_videos(
    session: AsyncSession, host: str, channel_id: uuid.UUID, sort: str, offset: int, limit: int
) -> Page[VideoCard]:
    rows = await videos_repo.list_channel(session, channel_id, offset, limit, sort)
    return card_page(host, rows, offset, limit)


async def search(session: AsyncSession, host: str, q: str, offset: int, limit: int) -> Page[VideoCard]:
    return card_page(host, await videos_repo.search(session, q, offset, limit), offset, limit)


async def related(
    session: AsyncSession, host: str, video_id: uuid.UUID, user: User | None, limit: int
) -> Page[VideoCard]:
    video = await get_viewable_video(session, video_id, user)
    return card_page(host, await videos_repo.related(session, video, limit), 0, limit)


async def subscriptions(
    session: AsyncSession, host: str, user: User, offset: int, limit: int
) -> Page[VideoCard]:
    rows = await videos_repo.list_subscriptions_feed(session, user.id, offset, limit)
    return card_page(host, rows, offset, limit)


async def history(session: AsyncSession, host: str, user: User, offset: int, limit: int) -> Page[VideoCard]:
    return card_page(host, await videos_repo.history_of(session, user, offset, limit), offset, limit)


async def clear_history(session: AsyncSession, user: User) -> None:
    await session.execute(delete(WatchHistory).where(WatchHistory.user_id == user.id))
    await session.commit()


async def liked(session: AsyncSession, host: str, user: User, offset: int, limit: int) -> Page[VideoCard]:
    return card_page(host, await videos_repo.liked_by(session, user, offset, limit), offset, limit)


async def studio(session: AsyncSession, host: str, user: User, offset: int, limit: int) -> Page[StudioVideo]:
    rows = await videos_repo.list_for_owner(session, user.channel.id, offset, limit)
    items = [
        StudioVideo(
            id=v.id,
            title=v.title,
            duration_seconds=v.duration_seconds,
            views_count=v.views_count,
            published_at=v.published_at,
            created_at=v.created_at,
            visibility=v.visibility,
            status=v.status,
            thumbnail_url=thumbnail_url(host, key),
            channel=channel_brief(v.channel),
            likes_count=v.likes_count,
            comments_count=v.comments_count,
            moderation_state=v.moderation_state,
            processing_error=v.processing_error,
        )
        for v, key in rows[:limit]
    ]
    return Page[StudioVideo](items=items, has_more=len(rows) > limit, offset=offset, limit=limit)
