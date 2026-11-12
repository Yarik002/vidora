import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import NotFound
from app.models import Channel, Playlist, PlaylistItem, Thumbnail, User, Video, Visibility
from app.repositories import videos as videos_repo
from app.schemas.auth import ChannelBrief
from app.schemas.channel import PlaylistCreate, PlaylistDetail, PlaylistOut, PlaylistUpdate
from app.services.access import get_viewable_video, is_staff, viewable_condition
from app.services.presenters import thumbnail_url, video_card


def _first_thumb_key():
    """Thumbnail of the first public video in the playlist (cover image)."""
    v = aliased(Video)
    return (
        select(Thumbnail.object_key)
        .join(PlaylistItem, PlaylistItem.video_id == Thumbnail.video_id)
        .join(v, v.id == PlaylistItem.video_id)
        .where(
            PlaylistItem.playlist_id == Playlist.id,
            Thumbnail.is_primary.is_(True),
            v.status == "ready",
            v.visibility == "public",
            v.moderation_state == "active",
        )
        .order_by(PlaylistItem.position)
        .limit(1)
        .correlate(Playlist)
        .scalar_subquery()
    )


def _out(
    host: str, p: Playlist, channel: Channel, thumb: str | None, contains: bool | None = None
) -> PlaylistOut:
    return PlaylistOut(
        id=p.id,
        title=p.title,
        description=p.description,
        visibility=p.visibility,
        items_count=p.items_count,
        thumbnail_url=thumbnail_url(host, thumb),
        channel=ChannelBrief.model_validate(channel),
        updated_at=p.updated_at,
        contains_video=contains,
    )


def _can_see(p: Playlist, user: User | None) -> bool:
    if p.visibility != Visibility.PRIVATE:
        return True
    return user is not None and (user.channel.id == p.channel_id or is_staff(user))


async def _get_own(session: AsyncSession, playlist_id: uuid.UUID, user: User) -> Playlist:
    p = await session.get(Playlist, playlist_id)
    if p is None or p.channel_id != user.channel.id:
        raise NotFound("Playlist not found", code="playlist_not_found")
    return p


async def create(session: AsyncSession, user: User, data: PlaylistCreate, host: str) -> PlaylistOut:
    p = Playlist(channel_id=user.channel.id, **data.model_dump())
    session.add(p)
    await session.commit()
    await session.refresh(p)
    channel = await session.get(Channel, p.channel_id)
    assert channel is not None
    return _out(host, p, channel, None)


async def list_for_channel(
    session: AsyncSession, channel_id: uuid.UUID, user: User | None, host: str
) -> list[PlaylistOut]:
    own = user is not None and user.channel.id == channel_id
    stmt = (
        select(Playlist, Channel, _first_thumb_key())
        .join(Channel, Channel.id == Playlist.channel_id)
        .where(Playlist.channel_id == channel_id)
        .order_by(Playlist.updated_at.desc())
    )
    if not own:
        stmt = stmt.where(Playlist.visibility == Visibility.PUBLIC)
    return [_out(host, p, c, t) for p, c, t in (await session.execute(stmt)).all()]


async def list_mine(
    session: AsyncSession, user: User, host: str, video_id: uuid.UUID | None
) -> list[PlaylistOut]:
    contains = (
        select(func.count())
        .select_from(PlaylistItem)
        .where(PlaylistItem.playlist_id == Playlist.id, PlaylistItem.video_id == video_id)
        .correlate(Playlist)
        .scalar_subquery()
        if video_id
        else None
    )
    cols = [Playlist, Channel, _first_thumb_key()] + ([contains] if contains is not None else [])
    stmt = (
        select(*cols)
        .join(Channel, Channel.id == Playlist.channel_id)
        .where(Playlist.channel_id == user.channel.id)
        .order_by(Playlist.updated_at.desc())
    )
    result = []
    for row in (await session.execute(stmt)).all():
        flag = bool(row[3]) if video_id else None
        result.append(_out(host, row[0], row[1], row[2], flag))
    return result


async def detail(
    session: AsyncSession, playlist_id: uuid.UUID, user: User | None, host: str
) -> PlaylistDetail:
    row = (
        await session.execute(
            select(Playlist, Channel, _first_thumb_key())
            .join(Channel, Channel.id == Playlist.channel_id)
            .where(Playlist.id == playlist_id)
        )
    ).first()
    if row is None or not _can_see(row[0], user):
        raise NotFound("Playlist not found", code="playlist_not_found")
    p, channel, thumb = row
    stmt = (
        videos_repo.card_query()
        .join(PlaylistItem, PlaylistItem.video_id == Video.id)
        .where(PlaylistItem.playlist_id == p.id, viewable_condition(user))
        .order_by(PlaylistItem.position)
    )
    videos = [video_card(host, v, k) for v, k in (await session.execute(stmt)).unique().all()]
    base = _out(host, p, channel, thumb)
    return PlaylistDetail(
        **base.model_dump(), videos=videos, is_owner=user is not None and user.channel.id == p.channel_id
    )


async def update_playlist(
    session: AsyncSession, playlist_id: uuid.UUID, user: User, data: PlaylistUpdate, host: str
) -> PlaylistDetail:
    p = await _get_own(session, playlist_id, user)
    for name, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(p, name, value)
    await session.commit()
    return await detail(session, p.id, user, host)


async def delete_playlist(session: AsyncSession, playlist_id: uuid.UUID, user: User) -> None:
    p = await _get_own(session, playlist_id, user)
    await session.delete(p)
    await session.commit()


async def add_video(session: AsyncSession, playlist_id: uuid.UUID, user: User, video_id: uuid.UUID) -> None:
    p = await _get_own(session, playlist_id, user)
    await get_viewable_video(session, video_id, user)  # can't save what you can't watch
    next_pos = await session.scalar(
        select(func.coalesce(func.max(PlaylistItem.position) + 1, 0)).where(PlaylistItem.playlist_id == p.id)
    )
    result = await session.execute(
        insert(PlaylistItem)
        .values(playlist_id=p.id, video_id=video_id, position=next_pos)
        .on_conflict_do_nothing()
        .returning(PlaylistItem.id)
    )
    if result.first() is not None:
        await session.execute(
            update(Playlist)
            .where(Playlist.id == p.id)
            .values(items_count=Playlist.items_count + 1, updated_at=func.now())
        )
    await session.commit()


async def remove_video(
    session: AsyncSession, playlist_id: uuid.UUID, user: User, video_id: uuid.UUID
) -> None:
    p = await _get_own(session, playlist_id, user)
    result = await session.execute(
        delete(PlaylistItem)
        .where(PlaylistItem.playlist_id == p.id, PlaylistItem.video_id == video_id)
        .returning(PlaylistItem.id)
    )
    if result.first() is not None:
        await session.execute(
            update(Playlist)
            .where(Playlist.id == p.id)
            .values(items_count=Playlist.items_count - 1, updated_at=func.now())
        )
    await session.commit()
