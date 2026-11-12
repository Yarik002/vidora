import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, current_user_optional, public_host
from app.db.session import get_session
from app.models import User
from app.schemas.channel import PlaylistAdd, PlaylistCreate, PlaylistDetail, PlaylistOut, PlaylistUpdate
from app.services import playlist_service

router = APIRouter(prefix="/playlists", tags=["playlists"])


@router.post("", response_model=PlaylistOut, status_code=201)
async def create_playlist(
    data: PlaylistCreate,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PlaylistOut:
    return await playlist_service.create(session, user, data, public_host(request))


@router.get("/{playlist_id}", response_model=PlaylistDetail, summary="Playlist with the videos you may watch")
async def get_playlist(
    playlist_id: uuid.UUID,
    request: Request,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> PlaylistDetail:
    return await playlist_service.detail(session, playlist_id, user, public_host(request))


@router.patch("/{playlist_id}", response_model=PlaylistDetail)
async def update_playlist(
    playlist_id: uuid.UUID,
    data: PlaylistUpdate,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PlaylistDetail:
    return await playlist_service.update_playlist(session, playlist_id, user, data, public_host(request))


@router.delete("/{playlist_id}", status_code=204, response_class=Response)
async def delete_playlist(
    playlist_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> Response:
    await playlist_service.delete_playlist(session, playlist_id, user)
    return Response(status_code=204)


@router.post("/{playlist_id}/videos", status_code=204, response_class=Response)
async def add_video(
    playlist_id: uuid.UUID,
    data: PlaylistAdd,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await playlist_service.add_video(session, playlist_id, user, data.video_id)
    return Response(status_code=204)


@router.delete("/{playlist_id}/videos/{video_id}", status_code=204, response_class=Response)
async def remove_video(
    playlist_id: uuid.UUID,
    video_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await playlist_service.remove_video(session, playlist_id, user, video_id)
    return Response(status_code=204)
