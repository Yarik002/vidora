"""Direct-to-storage uploads (S3 multipart with presigned part URLs).

1. POST /uploads          -> video row (status=uploading) + multipart upload + presigned URL per part
2. browser PUTs parts     -> /storage/... (Caddy -> MinIO), 16 MB per request max, real progress
3. POST /uploads/{id}/complete -> S3 complete, real size checked, status=uploaded, job queued
4. worker                 -> ffprobe validation, transcoding, thumbnail, status=ready|failed
The API never streams video bytes, so a slow upload doesn't hold an API worker.
"""

import contextlib
import math
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound
from app.core.queue import enqueue_processing
from app.models import (
    FileKind,
    ProcessingJob,
    UploadSession,
    UploadStatus,
    User,
    Video,
    VideoFile,
    VideoStatus,
)
from app.repositories import videos as videos_repo
from app.schemas.video import UploadComplete, UploadCreate, UploadOut, UploadPart
from app.services import storage
from app.services.audit import audit


class UploadTooLarge(AppError):
    status_code = 413
    code = "upload_too_large"
    default_message = "File is too large"


async def create_upload(session: AsyncSession, user: User, data: UploadCreate, host: str) -> UploadOut:
    s = get_settings()
    if data.size_bytes > s.max_upload_bytes:
        raise UploadTooLarge(f"Max upload size is {s.max_upload_mb} MB")

    part_size = s.upload_part_bytes
    parts_count = max(1, math.ceil(data.size_bytes / part_size))
    title = (data.title or PurePosixPath(data.filename).stem or "Без названия")[:100]

    video = Video(
        channel_id=user.channel.id,
        title=title,
        description=data.description,
        visibility=data.visibility,
        status=VideoStatus.UPLOADING,
    )
    session.add(video)
    await session.flush()
    if data.tags:
        await videos_repo.set_tags(session, video.id, data.tags)

    # The key never contains user input: no path traversal, no overwriting someone else's object.
    key = f"uploads/{video.id}/original"
    upload_id = await storage.create_multipart(s.bucket_raw, key, "application/octet-stream")
    expires_at = datetime.now(UTC) + timedelta(seconds=s.upload_url_ttl_sec)
    upload = UploadSession(
        video_id=video.id,
        user_id=user.id,
        s3_upload_id=upload_id,
        bucket=s.bucket_raw,
        object_key=key,
        filename=data.filename[:255],
        declared_size=data.size_bytes,
        part_size=part_size,
        parts_count=parts_count,
        expires_at=expires_at,
    )
    session.add(upload)
    await session.commit()

    parts = [
        UploadPart(
            part_number=n,
            url=storage.presign_upload_part(host, s.bucket_raw, key, upload_id, n, s.upload_url_ttl_sec),
        )
        for n in range(1, parts_count + 1)
    ]
    return UploadOut(
        upload_id=upload.id, video_id=video.id, part_size=part_size, parts=parts, expires_at=expires_at
    )


async def _get_own_pending(session: AsyncSession, user: User, upload_id: uuid.UUID) -> UploadSession:
    upload = await session.scalar(
        select(UploadSession).where(UploadSession.id == upload_id).with_for_update()
    )
    if upload is None or upload.user_id != user.id:
        raise NotFound("Upload not found", code="upload_not_found")
    if upload.status != UploadStatus.PENDING:
        raise Conflict("Upload is already finished", code="upload_finished")
    if upload.expires_at <= datetime.now(UTC):
        raise Conflict("Upload expired, start again", code="upload_expired")
    return upload


async def complete_upload(
    session: AsyncSession, user: User, upload_id: uuid.UUID, data: UploadComplete
) -> Video:
    s = get_settings()
    upload = await _get_own_pending(session, user, upload_id)
    numbers = sorted(p.part_number for p in data.parts)
    if numbers != list(range(1, upload.parts_count + 1)):
        raise AppError("Parts list does not match the upload", code="parts_mismatch")

    parts = [
        {"PartNumber": p.part_number, "ETag": p.etag} for p in sorted(data.parts, key=lambda p: p.part_number)
    ]
    try:
        await storage.complete_multipart(upload.bucket, upload.object_key, upload.s3_upload_id, parts)
    except Exception as exc:  # wrong ETag, missing part, ...
        raise AppError(
            "Storage rejected the upload, some parts are missing", code="upload_incomplete"
        ) from exc

    video = await session.get(Video, upload.video_id)
    assert video is not None
    real_size = await storage.object_size(upload.bucket, upload.object_key)
    # Defence in depth: Caddy caps every part, here we check the assembled object.
    if real_size > s.max_upload_bytes or real_size != upload.declared_size:
        await storage.delete_prefix(upload.bucket, f"uploads/{video.id}/")
        upload.status = UploadStatus.ABORTED
        video.status = VideoStatus.FAILED
        video.processing_error = "Размер файла не совпал с заявленным"
        await session.commit()
        raise UploadTooLarge("Uploaded size does not match the declared size")

    upload.status = UploadStatus.COMPLETED
    upload.completed_at = datetime.now(UTC)
    video.status = VideoStatus.UPLOADED
    session.add(
        VideoFile(
            video_id=video.id,
            kind=FileKind.ORIGINAL,
            quality="original",
            bucket=upload.bucket,
            object_key=upload.object_key,
            mime_type="application/octet-stream",
            size_bytes=real_size,
        )
    )
    job = ProcessingJob(video_id=video.id)
    session.add(job)
    audit(
        session, "video.uploaded", actor_id=user.id, entity_type="video", entity_id=video.id, size=real_size
    )
    await session.commit()
    await enqueue_processing(str(video.id), str(job.id))
    return video


async def abort_upload(session: AsyncSession, user: User, upload_id: uuid.UUID) -> None:
    upload = await _get_own_pending(session, user, upload_id)
    with contextlib.suppress(Exception):  # already gone in storage is fine
        await storage.abort_multipart(upload.bucket, upload.object_key, upload.s3_upload_id)
    upload.status = UploadStatus.ABORTED
    video = await session.get(Video, upload.video_id)
    if video is not None:
        await session.delete(video)
    await session.commit()
