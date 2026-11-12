import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, current_user_optional, public_host
from app.db.session import get_session
from app.models import User
from app.schemas.channel import ChannelDetail, ChannelUpdate, PlaylistOut, SubscriptionOut
from app.schemas.common import Page
from app.schemas.video import VideoCard
from app.services import channel_service, feed_service, playlist_service

router = APIRouter(prefix="/channels", tags=["channels"])


@router.patch("/me", response_model=ChannelDetail, summary="Edit own channel")
async def update_my_channel(
    data: ChannelUpdate, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> ChannelDetail:
    return await channel_service.update_own(session, user, data)


@router.get("/{handle}", response_model=ChannelDetail)
async def get_channel(
    handle: str,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> ChannelDetail:
    channel = await channel_service.get_by_handle(session, handle)
    return await channel_service.detail(session, channel, user)


@router.get("/{handle}/videos", response_model=Page[VideoCard], summary="Public videos of a channel")
async def channel_videos(
    handle: str,
    request: Request,
    sort: Literal["new", "popular", "old"] = "new",
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=30, ge=1, le=60),
    session: AsyncSession = Depends(get_session),
) -> Page[VideoCard]:
    channel = await channel_service.get_by_handle(session, handle)
    return await feed_service.channel_videos(session, public_host(request), channel.id, sort, offset, limit)


@router.get("/{handle}/playlists", response_model=list[PlaylistOut])
async def channel_playlists(
    handle: str,
    request: Request,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> list[PlaylistOut]:
    channel = await channel_service.get_by_handle(session, handle)
    return await playlist_service.list_for_channel(session, channel.id, user, public_host(request))


@router.put("/{channel_id}/subscription", response_model=SubscriptionOut, summary="Subscribe (idempotent)")
async def subscribe(
    channel_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> SubscriptionOut:
    return await channel_service.set_subscription(session, user, channel_id, True)


@router.delete(
    "/{channel_id}/subscription", response_model=SubscriptionOut, summary="Unsubscribe (idempotent)"
)
async def unsubscribe(
    channel_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> SubscriptionOut:
    return await channel_service.set_subscription(session, user, channel_id, False)
