import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_info, current_user, current_user_optional, public_host
from app.db.session import get_session
from app.models import User
from app.repositories import videos as videos_repo
from app.schemas.common import Message, Page
from app.schemas.video import (
    AccessGrantIn,
    AccessGrantOut,
    ReactionIn,
    ReactionOut,
    VideoCard,
    VideoDetail,
    VideoStatusOut,
    VideoUpdate,
)
from app.services import video_service
from app.services.access import get_viewable_video
from app.services.presenters import card_page

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("", response_model=Page[VideoCard], summary="Home feed: public videos, newest first")
async def feed(
    request: Request,
    tag: str | None = Query(default=None, max_length=40),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=24, ge=1, le=60),
    session: AsyncSession = Depends(get_session),
) -> Page[VideoCard]:
    rows = await videos_repo.list_feed(session, offset, limit, tag)
    return card_page(public_host(request), rows, offset, limit)


@router.get("/tags", response_model=list[str], summary="Popular tags for the chips bar")
async def popular_tags(session: AsyncSession = Depends(get_session)) -> list[str]:
    return await videos_repo.popular_tags(session, 15)


@router.get("/{video_id}", response_model=VideoDetail)
async def get_video(
    video_id: uuid.UUID,
    request: Request,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> VideoDetail:
    return await video_service.get_detail(session, video_id, user, public_host(request))


@router.get("/{video_id}/status", response_model=VideoStatusOut, summary="Processing status (owner)")
async def video_status(
    video_id: uuid.UUID,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> VideoStatusOut:
    return await video_service.get_status(session, video_id, user, public_host(request))


@router.patch("/{video_id}", response_model=VideoDetail)
async def update_video(
    video_id: uuid.UUID,
    data: VideoUpdate,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> VideoDetail:
    return await video_service.update_video(session, video_id, user, data, public_host(request))


@router.delete("/{video_id}", response_model=Message)
async def delete_video(
    video_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> Message:
    await video_service.delete_video(session, video_id, user)
    return Message()


@router.get(
    "/{video_id}/stream",
    status_code=302,
    response_class=RedirectResponse,
    summary="Playback: access check, then 302 to a short-lived signed storage URL",
)
async def stream(
    video_id: uuid.UUID,
    request: Request,
    quality: Literal["720p", "360p"] | None = None,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    url = await video_service.stream_url(session, video_id, user, quality, public_host(request))
    # Not cacheable: the next request must pass the access check again.
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})


@router.post("/{video_id}/view", summary="Count a view (deduplicated) and update watch history")
async def view(
    video_id: uuid.UUID,
    request: Request,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    info = client_info(request)
    views = await video_service.register_view(session, video_id, user, info.ip, info.user_agent)
    return {"views_count": views}


@router.put("/{video_id}/reaction", response_model=ReactionOut)
async def react(
    video_id: uuid.UUID,
    data: ReactionIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ReactionOut:
    return await video_service.react(session, video_id, user, data.value)


@router.get("/{video_id}/related", response_model=Page[VideoCard])
async def related(
    video_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=20, ge=1, le=40),
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> Page[VideoCard]:
    video = await get_viewable_video(session, video_id, user)
    rows = await videos_repo.related(session, video, limit)
    return card_page(public_host(request), rows, 0, limit)


@router.get(
    "/{video_id}/access", response_model=list[AccessGrantOut], summary="Who can watch a private video"
)
async def list_access(
    video_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[AccessGrantOut]:
    return await video_service.list_grants(session, video_id, user)


@router.post("/{video_id}/access", response_model=AccessGrantOut, status_code=201)
async def grant_access(
    video_id: uuid.UUID,
    data: AccessGrantIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> AccessGrantOut:
    return await video_service.add_grant(session, video_id, user, data.username)


@router.delete("/{video_id}/access/{user_id}", status_code=204, response_class=Response)
async def revoke_access(
    video_id: uuid.UUID,
    user_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await video_service.remove_grant(session, video_id, user, user_id)
    return Response(status_code=204)
