import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, public_host
from app.db.session import get_session
from app.models import User, WatchHistory
from app.repositories import videos as videos_repo
from app.schemas.auth import ChannelBrief
from app.schemas.channel import PlaylistOut, StudioVideo
from app.schemas.common import Page
from app.schemas.video import VideoCard
from app.services import channel_service, playlist_service
from app.services.presenters import card_page, channel_brief, thumbnail_url

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/subscriptions", response_model=list[ChannelBrief])
async def my_subscriptions(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[ChannelBrief]:
    return await channel_service.subscriptions_of(session, user)


@router.get("/feed/subscriptions", response_model=Page[VideoCard], summary="New videos from subscriptions")
async def subscriptions_feed(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=24, ge=1, le=60),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[VideoCard]:
    rows = await videos_repo.list_subscriptions_feed(session, user.id, offset, limit)
    return card_page(public_host(request), rows, offset, limit)


@router.get("/history", response_model=Page[VideoCard])
async def history(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=24, ge=1, le=60),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[VideoCard]:
    rows = await videos_repo.history_of(session, user, offset, limit)
    return card_page(public_host(request), rows, offset, limit)


@router.delete("/history", status_code=204, response_class=Response, summary="Clear watch history")
async def clear_history(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> Response:
    await session.execute(delete(WatchHistory).where(WatchHistory.user_id == user.id))
    await session.commit()
    return Response(status_code=204)


@router.get("/liked", response_model=Page[VideoCard])
async def liked(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=24, ge=1, le=60),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[VideoCard]:
    rows = await videos_repo.liked_by(session, user, offset, limit)
    return card_page(public_host(request), rows, offset, limit)


@router.get("/videos", response_model=Page[StudioVideo], summary="Studio: all own videos in any state")
async def my_videos(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[StudioVideo]:
    host = public_host(request)
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


@router.get("/playlists", response_model=list[PlaylistOut])
async def my_playlists(
    request: Request,
    video_id: uuid.UUID | None = Query(default=None, description="mark playlists that contain this video"),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PlaylistOut]:
    return await playlist_service.list_mine(session, user, public_host(request), video_id)
