"""Background video processing: uploaded -> processing -> ready | failed."""

import asyncio
import contextlib
import logging
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

from arq import Retry
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    FileKind,
    JobStatus,
    ProcessingJob,
    Thumbnail,
    UploadSession,
    UploadStatus,
    Video,
    VideoFile,
    VideoStatus,
)
from app.services import storage
from app.worker import media

log = logging.getLogger("vidora.worker")
MAX_TRIES = 3


async def _set_failed(video_id: uuid.UUID, job_id: uuid.UUID | None, message: str) -> None:
    async with SessionLocal() as session:
        video = await session.get(Video, video_id)
        if video is not None:
            video.status = VideoStatus.FAILED
            video.processing_error = message[:500]
        if job_id is not None:
            job = await session.get(ProcessingJob, job_id)
            if job is not None:
                job.status = JobStatus.FAILED
                job.error = message[:1000]
                job.finished_at = datetime.now(UTC)
        await session.commit()


async def process_video_now(video_id: uuid.UUID, job_id: uuid.UUID | None = None, attempt: int = 1) -> None:
    """The whole pipeline. Called by the arq task, by the seed script and by tests."""
    s = get_settings()
    async with SessionLocal() as session:
        video = await session.get(Video, video_id)
        if video is None:
            return
        original = await session.scalar(
            select(VideoFile).where(VideoFile.video_id == video_id, VideoFile.kind == FileKind.ORIGINAL)
        )
        if original is None:
            raise media.MediaError("original file is missing")
        video.status = VideoStatus.PROCESSING
        video.processing_error = None
        if job_id is not None:
            job = await session.get(ProcessingJob, job_id)
            if job is not None:
                job.status, job.attempt, job.started_at = JobStatus.RUNNING, attempt, datetime.now(UTC)
        await session.commit()
        bucket, key = original.bucket, original.object_key

    with tempfile.TemporaryDirectory(prefix="vidora-") as tmp:
        src = os.path.join(tmp, "source")
        await asyncio.to_thread(storage.download_file_sync, bucket, key, src)
        info = await media.probe(src, s.max_video_duration_sec)
        log.info(
            "video %s probed: %.1fs %dx%d %s",
            video_id,
            info.duration,
            info.width,
            info.height,
            info.format_name,
        )

        renditions: list[VideoFile] = []
        for height in media.target_heights(info.height):
            out = os.path.join(tmp, f"{height}p.mp4")
            # Generous timeout: veryfast preset is usually several times faster than real time.
            await media.transcode(src, out, height, info.has_audio, timeout=max(300, info.duration * 6))
            width, real_h, bitrate = await media.stream_info(out)
            media_key = f"videos/{video_id}/{height}p.mp4"
            await asyncio.to_thread(storage.upload_file_sync, out, s.bucket_media, media_key, "video/mp4")
            renditions.append(
                VideoFile(
                    video_id=video_id,
                    kind=FileKind.RENDITION,
                    quality=f"{height}p",
                    bucket=s.bucket_media,
                    object_key=media_key,
                    mime_type="video/mp4",
                    size_bytes=os.path.getsize(out),
                    width=width,
                    height=real_h,
                    bitrate=bitrate,
                )
            )

        thumb_path = os.path.join(tmp, "thumb.jpg")
        await media.thumbnail(src, thumb_path, at_seconds=min(info.duration * 0.25, 30))
        thumb_key = f"videos/{video_id}/thumb.jpg"
        await asyncio.to_thread(storage.upload_file_sync, thumb_path, s.bucket_media, thumb_key, "image/jpeg")

    async with SessionLocal() as session:
        video = await session.get(Video, video_id)
        if video is None:  # deleted while processing
            await storage.delete_prefix(s.bucket_media, f"videos/{video_id}/")
            return
        # Re-processing replaces previous outputs.
        await session.execute(
            delete(VideoFile).where(VideoFile.video_id == video_id, VideoFile.kind == FileKind.RENDITION)
        )
        await session.execute(delete(Thumbnail).where(Thumbnail.video_id == video_id))
        session.add_all(renditions)
        session.add(
            Thumbnail(
                video_id=video_id,
                bucket=s.bucket_media,
                object_key=thumb_key,
                width=1280,
                height=720,
                is_primary=True,
            )
        )
        video.duration_seconds = round(info.duration, 2)
        video.status = VideoStatus.READY
        video.published_at = video.published_at or datetime.now(UTC)
        if job_id is not None:
            job = await session.get(ProcessingJob, job_id)
            if job is not None:
                job.status, job.finished_at = JobStatus.SUCCEEDED, datetime.now(UTC)
        await session.commit()
    log.info("video %s is ready (%s)", video_id, ", ".join(r.quality for r in renditions))


async def process_video(ctx: dict, video_id: str, job_id: str) -> str:
    vid, jid = uuid.UUID(video_id), uuid.UUID(job_id)
    attempt = ctx.get("job_try", 1)
    try:
        await process_video_now(vid, jid, attempt)
    except media.MediaError as exc:
        # Bad input: retrying won't help.
        log.warning("video %s rejected: %s", vid, exc)
        await _set_failed(vid, jid, f"Файл не распознан как видео: {exc}")
        return "failed"
    except Exception as exc:
        if attempt < MAX_TRIES:
            log.warning("video %s attempt %d failed, retrying: %r", vid, attempt, exc)
            raise Retry(defer=attempt * 10) from exc
        log.exception("video %s failed after %d attempts", vid, attempt)
        await _set_failed(vid, jid, "Ошибка обработки, попробуйте загрузить ещё раз")
        return "failed"
    return "ready"


async def requeue_stuck(ctx: dict) -> int:
    """Every few minutes: videos that are `uploaded` but never got processed (Redis was down when
    the job should have been queued) are queued again. The job id makes enqueueing idempotent."""
    from app.core.queue import enqueue_processing

    border = datetime.now(UTC) - timedelta(minutes=5)
    async with SessionLocal() as session:
        stuck = (
            await session.execute(
                select(Video.id, ProcessingJob.id)
                .join(ProcessingJob, ProcessingJob.video_id == Video.id)
                .where(
                    Video.status == VideoStatus.UPLOADED,
                    Video.updated_at < border,
                    ProcessingJob.status == JobStatus.QUEUED,
                )
            )
        ).all()
    for video_id, job_id in stuck:
        await enqueue_processing(str(video_id), str(job_id))
    if stuck:
        log.warning("re-queued %d stuck videos", len(stuck))
    return len(stuck)


async def cleanup_stale_uploads(ctx: dict) -> int:
    """Hourly: abort multipart uploads that were never completed and drop their videos."""
    now = datetime.now(UTC)
    cleaned = 0
    async with SessionLocal() as session:
        stale = (
            await session.scalars(
                select(UploadSession).where(
                    UploadSession.status == UploadStatus.PENDING, UploadSession.expires_at < now
                )
            )
        ).all()
        for upload in stale:
            with contextlib.suppress(Exception):  # already aborted or expired in storage
                await storage.abort_multipart(upload.bucket, upload.object_key, upload.s3_upload_id)
            upload.status = UploadStatus.ABORTED
            video = await session.get(Video, upload.video_id)
            if video is not None and video.status == VideoStatus.UPLOADING:
                video.status = VideoStatus.FAILED
                video.processing_error = "Загрузка не была завершена"
            cleaned += 1
        await session.commit()
    if cleaned:
        log.info("aborted %d stale uploads", cleaned)
    return cleaned
