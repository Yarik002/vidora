"""Integration tests against the real stack services (Postgres, Redis, MinIO) from compose.

* database `vidora_test` is recreated once per run and migrated with Alembic (the same path as prod);
* Redis DB 1 is flushed once per run;
* the app is called in-process through ASGITransport; storage requests go to http://minio:9000
  with the Host header the URL was signed for (in prod Caddy does exactly that).
"""

import asyncio
import os
import subprocess
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    FileKind,
    Role,
    Thumbnail,
    User,
    Video,
    VideoFile,
    VideoStatus,
    Visibility,
)

BASE_URL = "https://testserver"
PASSWORD = "Secret-pass-123"


def _recreate_database() -> None:
    s = get_settings()
    assert s.postgres_db.endswith("_test"), "refusing to run tests against a non-test database"

    async def run() -> None:
        conn = await asyncpg.connect(
            host=s.postgres_host,
            port=s.postgres_port,
            user=s.postgres_user,
            password=s.postgres_password,
            database="postgres",
        )
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{s.postgres_db}" WITH (FORCE)')
            await conn.execute(f'CREATE DATABASE "{s.postgres_db}"')
        finally:
            await conn.close()

    asyncio.run(run())


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    _recreate_database()
    subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=Path(__file__).parent.parent)


@pytest.fixture(scope="session", autouse=True)
async def clean_redis(database: None) -> None:
    await get_redis().flushdb()


@pytest.fixture(autouse=True)
def generous_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most tests register many users from one 'IP'; the rate limit test lowers this itself."""
    s = get_settings()
    monkeypatch.setattr(s, "login_rate_limit", 10_000)
    monkeypatch.setattr(s, "register_rate_limit", 10_000)


async def _new_client() -> httpx.AsyncClient:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)
    # First request gives us the CSRF cookie; the frontend does the same.
    await client.get("/api/v1/health")
    client.headers["X-CSRF-Token"] = client.cookies.get("vid_csrf") or ""
    return client


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    c = await _new_client()
    yield c
    await c.aclose()


class Users:
    """Factory of logged-in clients: `alice = await users.new()`."""

    def __init__(self) -> None:
        self.clients: list[httpx.AsyncClient] = []

    async def new(self, role: Role = Role.USER, prefix: str = "u") -> httpx.AsyncClient:
        c = await _new_client()
        self.clients.append(c)
        name = f"{prefix}{uuid.uuid4().hex[:10]}"
        r = await c.post(
            "/api/v1/auth/register",
            json={"email": f"{name}@example.com", "username": name, "password": PASSWORD},
        )
        assert r.status_code == 201, r.text
        me = r.json()
        c.me = me  # type: ignore[attr-defined]
        if role != Role.USER:
            async with SessionLocal() as session:
                user = await session.get(User, uuid.UUID(me["id"]))
                assert user is not None
                user.role = role
                await session.commit()
        return c


@pytest.fixture
async def users() -> AsyncIterator[Users]:
    factory = Users()
    yield factory
    for c in factory.clients:
        await c.aclose()


async def make_ready_video(
    owner: httpx.AsyncClient, visibility: Visibility = Visibility.PUBLIC, title: str = "Test video"
) -> uuid.UUID:
    """A ready video straight in the DB (fast). Upload + ffmpeg is covered by test_upload_processing."""
    async with SessionLocal() as session:
        channel_id = uuid.UUID(owner.me["channel"]["id"])  # type: ignore[attr-defined]
        video = Video(
            channel_id=channel_id,
            title=title,
            description="desc",
            visibility=visibility,
            status=VideoStatus.READY,
            duration_seconds=3.0,
        )
        session.add(video)
        await session.flush()
        video.published_at = video.created_at
        s = get_settings()
        session.add(
            VideoFile(
                video_id=video.id,
                kind=FileKind.RENDITION,
                quality="360p",
                bucket=s.bucket_media,
                object_key=f"videos/{video.id}/360p.mp4",
                mime_type="video/mp4",
                size_bytes=1,
                height=360,
            )
        )
        session.add(
            Thumbnail(
                video_id=video.id,
                bucket=s.bucket_media,
                object_key=f"videos/{video.id}/thumb.jpg",
                width=1280,
                height=720,
                is_primary=True,
            )
        )
        await session.commit()
        return video.id


async def video_from_db(video_id: uuid.UUID) -> Video:
    async with SessionLocal() as session:
        video = await session.scalar(select(Video).where(Video.id == video_id))
        assert video is not None
        return video


def storage_request_target(public_url: str) -> tuple[str, str]:
    """/storage/bucket/key?sig -> (http://minio:9000/bucket/key?sig, signed host)."""
    parts = urlsplit(public_url)
    path = parts.path.removeprefix(get_settings().storage_public_prefix)
    return f"{get_settings().s3_endpoint}{path}?{parts.query}", urlsplit(BASE_URL).netloc


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """3-second 320x240 clip with audio, generated by ffmpeg (no third-party content)."""
    path = tmp_path_factory.mktemp("media") / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=25:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )
    return path


os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """All async tests share the session event loop: the app keeps global DB/Redis pools
    (as in production), and those must not be used across different loops."""
    session_loop = pytest.mark.asyncio(loop_scope="session")
    for item in items:
        if asyncio.iscoroutinefunction(getattr(item, "function", None)):
            item.add_marker(session_loop, append=False)
