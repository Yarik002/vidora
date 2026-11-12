import hashlib
import uuid

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, Forbidden, NotFound
from app.core.redis import first_seen
from app.models import (
    FileKind,
    Role,
    Subscription,
    User,
    Video,
    VideoAccessGrant,
    VideoReaction,
    VideoStatus,
    VideoView,
    WatchHistory,
)
from app.repositories import users as users_repo
from app.repositories import videos as videos_repo
from app.schemas.video import AccessGrantOut, ReactionOut, VideoDetail, VideoStatusOut, VideoUpdate
from app.services import storage
from app.services.access import get_viewable_video, is_owner
from app.services.audit import audit
from app.services.presenters import channel_brief, thumbnail_url

VIEW_DEDUP_SECONDS = 30 * 60


async def get_detail(session: AsyncSession, video_id: uuid.UUID, user: User | None, host: str) -> VideoDetail:
    await get_viewable_video(session, video_id, user)  # access check first
    row = await videos_repo.get_with_channel(session, video_id)
    assert row is not None
    video, thumb_key = row
    files = await videos_repo.files_of(session, video_id)
    qualities = sorted(
        (f.quality for f in files if f.kind == FileKind.RENDITION),
        key=lambda q: int(q.rstrip("p")),
        reverse=True,
    )
    my_reaction, subscribed = 0, False
    if user is not None:
        my_reaction = await videos_repo.my_reaction(session, user.id, video_id)
        subscribed = bool(
            await session.scalar(
                select(Subscription.channel_id).where(
                    Subscription.subscriber_id == user.id, Subscription.channel_id == video.channel_id
                )
            )
        )
    return VideoDetail(
        id=video.id,
        title=video.title,
        description=video.description,
        duration_seconds=video.duration_seconds,
        views_count=video.views_count,
        likes_count=video.likes_count,
        dislikes_count=video.dislikes_count,
        comments_count=video.comments_count,
        published_at=video.published_at,
        created_at=video.created_at,
        visibility=video.visibility,
        status=video.status,
        moderation_state=video.moderation_state,
        processing_error=video.processing_error,
        thumbnail_url=thumbnail_url(host, thumb_key),
        channel=channel_brief(video.channel),
        tags=await videos_repo.tags_of(session, video_id),
        qualities=qualities,
        my_reaction=my_reaction,
        is_subscribed=subscribed,
        is_owner=is_owner(user, video),
    )


async def get_status(session: AsyncSession, video_id: uuid.UUID, user: User, host: str) -> VideoStatusOut:
    video = await _get_own_or_admin(session, video_id, user)
    row = await videos_repo.get_with_channel(session, video.id)
    thumb = row[1] if row else None
    return VideoStatusOut(
        id=video.id,
        status=video.status,
        processing_error=video.processing_error,
        duration_seconds=video.duration_seconds,
        thumbnail_url=thumbnail_url(host, thumb),
    )


async def _get_own_or_admin(session: AsyncSession, video_id: uuid.UUID, user: User) -> Video:
    """Edit/delete rights: only the owner or an admin. Others get 404 (IDOR-safe)."""
    video = await session.get(Video, video_id)
    if video is None:
        raise NotFound("Video not found", code="video_not_found")
    if not is_owner(user, video) and user.role != Role.ADMIN:
        if user.role == Role.MODERATOR:
            raise Forbidden("Moderators hide videos via the moderation panel")
        raise NotFound("Video not found", code="video_not_found")
    return video


async def update_video(
    session: AsyncSession, video_id: uuid.UUID, user: User, data: VideoUpdate, host: str
) -> VideoDetail:
    video = await _get_own_or_admin(session, video_id, user)
    fields = data.model_dump(exclude_unset=True, exclude={"tags"})
    for name, value in fields.items():
        if value is not None:
            setattr(video, name, value)
    if data.tags is not None:
        await videos_repo.set_tags(session, video.id, data.tags)
    await session.commit()
    return await get_detail(session, video.id, user, host)


async def delete_video(session: AsyncSession, video_id: uuid.UUID, user: User) -> None:
    video = await _get_own_or_admin(session, video_id, user)
    s = get_settings()
    audit(
        session, "video.delete", actor_id=user.id, entity_type="video", entity_id=video.id, title=video.title
    )
    await session.delete(video)
    await session.commit()
    # Storage cleanup after the DB commit: a crash here leaves orphan objects, never broken rows.
    await storage.delete_prefix(s.bucket_raw, f"uploads/{video_id}/")
    await storage.delete_prefix(s.bucket_media, f"videos/{video_id}/")


async def stream_url(
    session: AsyncSession, video_id: uuid.UUID, user: User | None, quality: str | None, host: str
) -> str:
    """Access is checked here; the file itself is served by MinIO via a short-lived signed URL
    (Range requests and seeking are handled by storage, not by Python)."""
    video = await get_viewable_video(session, video_id, user)
    if video.status != VideoStatus.READY:
        raise AppError("Video is not ready yet", code="video_not_ready")
    files = [f for f in await videos_repo.files_of(session, video_id) if f.kind == FileKind.RENDITION]
    if not files:
        raise NotFound("No playable files", code="no_renditions")
    files.sort(key=lambda f: f.height or 0, reverse=True)
    chosen = next((f for f in files if f.quality == quality), files[0])
    s = get_settings()
    ttl = s.playback_url_ttl_sec + int(video.duration_seconds or 0)
    return storage.presign_get(host, chosen.bucket, chosen.object_key, ttl, content_type="video/mp4")


async def register_view(
    session: AsyncSession, video_id: uuid.UUID, user: User | None, ip: str | None, user_agent: str | None
) -> int:
    video = await get_viewable_video(session, video_id, user)
    viewer = str(user.id) if user else hashlib.sha256(f"{ip}|{user_agent}".encode()).hexdigest()
    if user is not None:
        stmt = insert(WatchHistory).values(user_id=user.id, video_id=video.id)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[WatchHistory.user_id, WatchHistory.video_id], set_={"watched_at": func.now()}
            )
        )
    # One view per viewer per 30 minutes (Redis SET NX), like a simplified YouTube counter.
    if await first_seen(f"view:{video.id}:{viewer}", VIEW_DEDUP_SECONDS):
        session.add(
            VideoView(
                video_id=video.id,
                user_id=user.id if user else None,
                viewer_hash=hashlib.sha256(viewer.encode()).hexdigest(),
            )
        )
        await session.execute(
            update(Video).where(Video.id == video.id).values(views_count=Video.views_count + 1)
        )
    await session.commit()
    return int(await session.scalar(select(Video.views_count).where(Video.id == video.id)) or 0)


async def react(session: AsyncSession, video_id: uuid.UUID, user: User, value: int) -> ReactionOut:
    """Like / dislike / remove. Counters change in the same transaction; an advisory lock on
    (user, video) serializes double clicks so counters can't drift."""
    video = await get_viewable_video(session, video_id, user)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"react:{user.id}:{video.id}"}
    )
    old = (
        await session.scalar(
            select(VideoReaction.value).where(
                VideoReaction.user_id == user.id, VideoReaction.video_id == video.id
            )
        )
        or 0
    )
    if value == 0:
        await session.execute(
            delete(VideoReaction).where(VideoReaction.user_id == user.id, VideoReaction.video_id == video.id)
        )
    else:
        stmt = insert(VideoReaction).values(user_id=user.id, video_id=video.id, value=value)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[VideoReaction.user_id, VideoReaction.video_id], set_={"value": value}
            )
        )
    d_likes = int(value == 1) - int(old == 1)
    d_dislikes = int(value == -1) - int(old == -1)
    likes, dislikes = (
        await session.execute(
            update(Video)
            .where(Video.id == video.id)
            .values(likes_count=Video.likes_count + d_likes, dislikes_count=Video.dislikes_count + d_dislikes)
            .returning(Video.likes_count, Video.dislikes_count)
        )
    ).one()
    await session.commit()
    return ReactionOut(likes_count=likes, dislikes_count=dislikes, my_reaction=value)


# --- private video access grants -------------------------------------------------------------


async def list_grants(session: AsyncSession, video_id: uuid.UUID, user: User) -> list[AccessGrantOut]:
    video = await _get_own_or_admin(session, video_id, user)
    rows = await session.execute(
        select(VideoAccessGrant.user_id, User.username, VideoAccessGrant.created_at)
        .join(User, User.id == VideoAccessGrant.user_id)
        .where(VideoAccessGrant.video_id == video.id)
        .order_by(VideoAccessGrant.created_at)
    )
    return [AccessGrantOut(user_id=r.user_id, username=r.username, created_at=r.created_at) for r in rows]


async def add_grant(session: AsyncSession, video_id: uuid.UUID, user: User, username: str) -> AccessGrantOut:
    video = await _get_own_or_admin(session, video_id, user)
    target = await users_repo.get_user_by_username(session, username)
    if target is None:
        raise NotFound("User not found", code="user_not_found")
    stmt = insert(VideoAccessGrant).values(video_id=video.id, user_id=target.id, granted_by=user.id)
    await session.execute(stmt.on_conflict_do_nothing())
    audit(
        session, "video.grant_access", actor_id=user.id, entity_type="video", entity_id=video.id, to=target.id
    )
    await session.commit()
    created = await session.scalar(
        select(VideoAccessGrant.created_at).where(
            VideoAccessGrant.video_id == video.id, VideoAccessGrant.user_id == target.id
        )
    )
    return AccessGrantOut(user_id=target.id, username=target.username, created_at=created)


async def remove_grant(session: AsyncSession, video_id: uuid.UUID, user: User, target_id: uuid.UUID) -> None:
    video = await _get_own_or_admin(session, video_id, user)
    await session.execute(
        delete(VideoAccessGrant).where(
            VideoAccessGrant.video_id == video.id, VideoAccessGrant.user_id == target_id
        )
    )
    audit(
        session,
        "video.revoke_access",
        actor_id=user.id,
        entity_type="video",
        entity_id=video.id,
        to=target_id,
    )
    await session.commit()
