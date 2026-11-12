import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, public_host
from app.db.session import get_session
from app.models import User
from app.schemas.auth import ChannelBrief
from app.schemas.channel import PlaylistOut, StudioVideo
from app.schemas.common import Page
from app.schemas.video import VideoCard
from app.services import channel_service, feed_service, playlist_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/subscriptions", response_model=list[ChannelBrief])
async def my_subscriptions(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[ChannelBrief]:
    return await channel_service.subscriptions_of(session, user)


@router.get("/feed/subscriptions", response_model=Page[VideoCard], summary="New videos from subscriptions")
async def subscriptions_feed(
    request: Request,
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=24, ge=1, le=60),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[VideoCard]:
    return await feed_service.subscriptions(session, public_host(request), user, offset, limit)


@router.get("/history", response_model=Page[VideoCard])
async def history(
    request: Request,
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=24, ge=1, le=60),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[VideoCard]:
    return await feed_service.history(session, public_host(request), user, offset, limit)


@router.delete("/history", status_code=204, response_class=Response, summary="Clear watch history")
async def clear_history(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> Response:
    await feed_service.clear_history(session, user)
    return Response(status_code=204)


@router.get("/liked", response_model=Page[VideoCard])
async def liked(
    request: Request,
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=24, ge=1, le=60),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[VideoCard]:
    return await feed_service.liked(session, public_host(request), user, offset, limit)


@router.get("/videos", response_model=Page[StudioVideo], summary="Studio: all own videos in any state")
async def my_videos(
    request: Request,
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[StudioVideo]:
    return await feed_service.studio(session, public_host(request), user, offset, limit)


@router.get("/playlists", response_model=list[PlaylistOut])
async def my_playlists(
    request: Request,
    video_id: uuid.UUID | None = Query(default=None, description="mark playlists that contain this video"),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PlaylistOut]:
    return await playlist_service.list_mine(session, user, public_host(request), video_id)
