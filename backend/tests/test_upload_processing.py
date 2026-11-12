"""Upload -> storage -> worker pipeline -> playback, with real MinIO and real ffmpeg."""

import math
import uuid
from pathlib import Path

import httpx

from app.models import FileKind, VideoStatus
from app.worker.tasks import process_video
from tests.conftest import Users, storage_request_target, video_from_db


async def _upload(owner: httpx.AsyncClient, path: Path, declared_size: int | None = None, **meta) -> dict:
    data = path.read_bytes()
    size = declared_size or len(data)
    r = await owner.post(
        "/api/v1/uploads",
        json={"filename": path.name, "size_bytes": size, "content_type": "video/mp4", **meta},
    )
    assert r.status_code == 201, r.text
    upload = r.json()
    assert len(upload["parts"]) == math.ceil(size / upload["part_size"])
    parts = []
    async with httpx.AsyncClient(timeout=60) as raw:
        for part in upload["parts"]:
            n = part["part_number"]
            chunk = data[(n - 1) * upload["part_size"] : n * upload["part_size"]]
            url, host = storage_request_target(part["url"])
            put = await raw.put(url, content=chunk, headers={"Host": host})
            assert put.status_code == 200, put.text
            parts.append({"part_number": n, "etag": put.headers["etag"]})
    upload["completed_parts"] = parts
    return upload


async def _process(video_id: str) -> str:
    """Run the arq task function the same way the worker does (job_try=1)."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models import ProcessingJob

    async with SessionLocal() as session:
        job_id = await session.scalar(
            select(ProcessingJob.id).where(ProcessingJob.video_id == uuid.UUID(video_id))
        )
    return await process_video({"job_try": 1}, video_id, str(job_id))


async def test_full_upload_processing_and_playback(users: Users, sample_video: Path) -> None:
    alice = await users.new()
    upload = await _upload(alice, sample_video, title="Моё первое видео", tags=["test", "ffmpeg"])
    video_id = upload["video_id"]

    r = await alice.post(
        f"/api/v1/uploads/{upload['upload_id']}/complete", json={"parts": upload["completed_parts"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "uploaded"

    assert await _process(video_id) == "ready"
    video = await video_from_db(uuid.UUID(video_id))
    assert video.status == VideoStatus.READY
    assert 2.5 < (video.duration_seconds or 0) < 3.5
    assert video.published_at is not None

    detail = (await alice.get(f"/api/v1/videos/{video_id}")).json()
    assert detail["title"] == "Моё первое видео"
    assert detail["qualities"] == ["240p"]  # source is 240p: never upscaled
    assert detail["thumbnail_url"].startswith("/storage/")
    assert sorted(detail["tags"]) == ["ffmpeg", "test"]

    # Playback: API answers 302 to a signed storage URL, storage supports Range (seeking).
    r = await alice.get(f"/api/v1/videos/{video_id}/stream", follow_redirects=False)
    assert r.status_code == 302 and r.headers["cache-control"] == "no-store"
    url, host = storage_request_target(r.headers["location"])
    async with httpx.AsyncClient() as raw:
        ranged = await raw.get(url, headers={"Host": host, "Range": "bytes=0-1023"})
        assert ranged.status_code == 206
        assert len(ranged.content) == 1024
        assert ranged.headers["content-type"] == "video/mp4"
        # MP4 with faststart: 'moov' atom is near the beginning, so playback starts immediately.
        head = (await raw.get(url, headers={"Host": host, "Range": "bytes=0-65535"})).content
        assert b"moov" in head
        # The signature is bound to the exact object: tampering with the key fails.
        tampered = url.replace("/videos/", "/videoz/", 1)
        assert (await raw.get(tampered, headers={"Host": host})).status_code in (403, 404)

    # The feed shows the new public video.
    feed = (await alice.get("/api/v1/videos")).json()["items"]
    assert any(v["id"] == video_id for v in feed)


async def test_not_a_video_is_rejected_by_content_not_extension(users: Users, tmp_path: Path) -> None:
    alice = await users.new()
    fake = tmp_path / "totally_a_video.mp4"
    fake.write_bytes(b"this is plain text pretending to be a video " * 100)
    upload = await _upload(alice, fake)
    r = await alice.post(
        f"/api/v1/uploads/{upload['upload_id']}/complete", json={"parts": upload["completed_parts"]}
    )
    assert r.status_code == 200
    assert await _process(upload["video_id"]) == "failed"
    video = await video_from_db(uuid.UUID(upload["video_id"]))
    assert video.status == VideoStatus.FAILED
    assert video.processing_error
    # A failed video is not visible to others and not playable.
    bob = await users.new()
    assert (await bob.get(f"/api/v1/videos/{upload['video_id']}")).status_code == 404


async def test_declared_size_mismatch_is_rejected(users: Users, sample_video: Path) -> None:
    alice = await users.new()
    real = sample_video.stat().st_size
    upload = await _upload(alice, sample_video, declared_size=real + 10)  # lie about the size
    r = await alice.post(
        f"/api/v1/uploads/{upload['upload_id']}/complete", json={"parts": upload["completed_parts"]}
    )
    assert r.status_code == 413
    assert (await video_from_db(uuid.UUID(upload["video_id"]))).status == VideoStatus.FAILED


async def test_upload_size_limit(users: Users) -> None:
    alice = await users.new()
    r = await alice.post(
        "/api/v1/uploads",
        json={"filename": "huge.mp4", "size_bytes": 50 * 1024**3, "content_type": "video/mp4"},
    )
    assert r.status_code == 413 and r.json()["error"]["code"] == "upload_too_large"


async def test_foreign_upload_cannot_be_completed(users: Users, sample_video: Path) -> None:
    alice, mallory = await users.new(), await users.new()
    upload = await _upload(alice, sample_video)
    r = await mallory.post(
        f"/api/v1/uploads/{upload['upload_id']}/complete", json={"parts": upload["completed_parts"]}
    )
    assert r.status_code == 404
    r = await mallory.delete(f"/api/v1/uploads/{upload['upload_id']}")
    assert r.status_code == 404


async def test_upload_requires_auth(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/uploads", json={"filename": "a.mp4", "size_bytes": 10})
    assert r.status_code == 401


async def test_storage_rejects_unsigned_access(sample_video: Path) -> None:
    """Buckets are private: without a signature MinIO answers 403."""
    from app.core.config import get_settings

    s = get_settings()
    async with httpx.AsyncClient() as raw:
        r = await raw.get(f"{s.s3_endpoint}/{s.bucket_media}/videos/anything/360p.mp4")
        assert r.status_code == 403
        r = await raw.get(f"{s.s3_endpoint}/{s.bucket_media}?list-type=2")
        assert r.status_code == 403


async def test_original_file_is_recorded(users: Users, sample_video: Path) -> None:
    alice = await users.new()
    upload = await _upload(alice, sample_video)
    await alice.post(
        f"/api/v1/uploads/{upload['upload_id']}/complete", json={"parts": upload["completed_parts"]}
    )
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models import VideoFile

    async with SessionLocal() as session:
        files = (
            await session.scalars(
                select(VideoFile).where(VideoFile.video_id == uuid.UUID(upload["video_id"]))
            )
        ).all()
    assert [f.kind for f in files] == [FileKind.ORIGINAL]
    assert files[0].size_bytes == sample_video.stat().st_size


async def test_complete_can_be_retried_after_storage_assembled_the_object(
    users: Users, sample_video: Path
) -> None:
    """Regression (code review): if S3 completed the multipart but our transaction failed,
    a retry used to fail forever with NoSuchUpload."""
    from app.core.config import get_settings
    from app.services import storage

    alice = await users.new()
    upload = await _upload(alice, sample_video)
    s = get_settings()
    # simulate "storage already assembled it, our side did not record it"
    parts = [{"PartNumber": p["part_number"], "ETag": p["etag"]} for p in upload["completed_parts"]]
    from app.db.session import SessionLocal
    from app.models import UploadSession

    async with SessionLocal() as session:
        row = await session.get(UploadSession, uuid.UUID(upload["upload_id"]))
        await storage.complete_multipart(s.bucket_raw, row.object_key, row.s3_upload_id, parts)
    r = await alice.post(
        f"/api/v1/uploads/{upload['upload_id']}/complete", json={"parts": upload["completed_parts"]}
    )
    assert r.status_code == 200 and r.json()["status"] == "uploaded"


async def test_active_uploads_are_limited(users: Users) -> None:
    from app.services.upload_service import MAX_ACTIVE_UPLOADS

    alice = await users.new()
    body = {"filename": "a.mp4", "size_bytes": 1000, "content_type": "video/mp4"}
    codes = [
        (await alice.post("/api/v1/uploads", json=body)).status_code for _ in range(MAX_ACTIVE_UPLOADS + 1)
    ]
    assert codes == [201] * MAX_ACTIVE_UPLOADS + [429]
