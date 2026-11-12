import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, public_host
from app.db.session import get_session
from app.models import User
from app.schemas.video import UploadComplete, UploadCreate, UploadOut, VideoStatusOut
from app.services import upload_service

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post(
    "",
    response_model=UploadOut,
    status_code=201,
    summary="Start an upload: returns presigned URLs, one per 10 MB part",
)
async def create_upload(
    data: UploadCreate,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> UploadOut:
    return await upload_service.create_upload(session, user, data, public_host(request))


@router.post(
    "/{upload_id}/complete",
    response_model=VideoStatusOut,
    summary="Finish an upload: assemble parts, check size, queue processing",
)
async def complete_upload(
    upload_id: uuid.UUID,
    data: UploadComplete,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> VideoStatusOut:
    video = await upload_service.complete_upload(session, user, upload_id, data)
    return VideoStatusOut(
        id=video.id,
        status=video.status,
        processing_error=video.processing_error,
        duration_seconds=video.duration_seconds,
        thumbnail_url=None,
    )


@router.delete("/{upload_id}", status_code=204, response_class=Response, summary="Cancel an upload")
async def abort_upload(
    upload_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> Response:
    await upload_service.abort_upload(session, user, upload_id)
    return Response(status_code=204)
