import uuid
from collections.abc import Sequence

from sqlalchemy import Select, and_, case, delete, func, literal, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import (
    Subscription,
    Tag,
    Thumbnail,
    Video,
    VideoFile,
    VideoReaction,
    VideoTag,
    WatchHistory,
)
from app.services.access import listed_condition, viewable_condition

# One row of a list = (Video with channel, primary thumbnail key)
CardRow = tuple[Video, str | None]


def _thumb_key():
    return (
        select(Thumbnail.object_key)
        .where(Thumbnail.video_id == Video.id, Thumbnail.is_primary.is_(True))
        .correlate(Video)
        .scalar_subquery()
        .label("thumb_key")
    )


def card_query() -> Select:
    return select(Video, _thumb_key()).options(joinedload(Video.channel))


async def _rows(session: AsyncSession, stmt: Select) -> list[CardRow]:
    return [(r[0], r[1]) for r in (await session.execute(stmt)).unique().all()]


async def get_with_channel(session: AsyncSession, video_id: uuid.UUID) -> CardRow | None:
    rows = await _rows(session, card_query().where(Video.id == video_id))
    return rows[0] if rows else None


async def list_feed(session: AsyncSession, offset: int, limit: int, tag: str | None = None) -> list[CardRow]:
    stmt = card_query().where(listed_condition())
    if tag:
        stmt = stmt.where(
            Video.id.in_(
                select(VideoTag.video_id).join(Tag, Tag.id == VideoTag.tag_id).where(Tag.name == tag)
            )
        )
    stmt = stmt.order_by(Video.published_at.desc(), Video.id).offset(offset).limit(limit + 1)
    return await _rows(session, stmt)


async def list_channel(
    session: AsyncSession,
    channel_id: uuid.UUID,
    offset: int,
    limit: int,
    sort: str = "new",
    include_all: bool = False,
) -> list[CardRow]:
    stmt = card_query().where(Video.channel_id == channel_id)
    if not include_all:
        stmt = stmt.where(listed_condition())
    order = {"popular": Video.views_count.desc(), "old": Video.created_at.asc()}.get(
        sort, Video.created_at.desc()
    )
    stmt = stmt.order_by(order, Video.id).offset(offset).limit(limit + 1)
    return await _rows(session, stmt)


async def list_subscriptions_feed(
    session: AsyncSession, user_id: uuid.UUID, offset: int, limit: int
) -> list[CardRow]:
    stmt = (
        card_query()
        .where(
            listed_condition(),
            Video.channel_id.in_(
                select(Subscription.channel_id).where(Subscription.subscriber_id == user_id)
            ),
        )
        .order_by(Video.published_at.desc(), Video.id)
        .offset(offset)
        .limit(limit + 1)
    )
    return await _rows(session, stmt)


async def search(session: AsyncSession, q: str, offset: int, limit: int) -> list[CardRow]:
    """Full-text search (russian stemming) + trigram word similarity for typos and partial words.

    `q <% title` (word_similarity) compares the query with the best matching *part* of the title,
    unlike `%` which compares with the whole title and misses typos in long titles. Both the
    tsvector and the trigram conditions are served by GIN indexes.
    """
    # Default 0.6 is too strict for one-letter typos in short Russian words; scoped to this transaction.
    await session.execute(text("SET LOCAL pg_trgm.word_similarity_threshold = 0.4"))
    tsq = func.websearch_to_tsquery("russian", q)
    similarity = func.word_similarity(q, Video.title)
    rank = func.ts_rank_cd(Video.search_vector, tsq) + similarity
    stmt = (
        card_query()
        .where(
            listed_condition(),
            or_(
                Video.search_vector.op("@@")(tsq),
                literal(q).op("<%")(Video.title),
                Video.title.ilike(f"%{_escape_like(q)}%"),
            ),
        )
        .order_by(rank.desc(), Video.views_count.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    return await _rows(session, stmt)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def related(session: AsyncSession, video: Video, limit: int) -> list[CardRow]:
    """Same tags or same channel first, then popular videos."""
    tag_ids = select(VideoTag.tag_id).where(VideoTag.video_id == video.id)
    shared_tags = (
        select(func.count())
        .select_from(VideoTag)
        .where(VideoTag.video_id == Video.id, VideoTag.tag_id.in_(tag_ids))
        .correlate(Video)
        .scalar_subquery()
    )
    score = shared_tags * 3 + case((Video.channel_id == video.channel_id, 2), else_=0)
    stmt = (
        card_query()
        .where(listed_condition(), Video.id != video.id)
        .order_by(score.desc(), Video.views_count.desc(), Video.published_at.desc())
        .limit(limit)
    )
    return await _rows(session, stmt)


async def list_for_owner(
    session: AsyncSession, channel_id: uuid.UUID, offset: int, limit: int
) -> list[CardRow]:
    return await list_channel(session, channel_id, offset, limit, include_all=True)


async def liked_by(session: AsyncSession, user, offset: int, limit: int) -> list[CardRow]:
    stmt = (
        card_query()
        .join(VideoReaction, and_(VideoReaction.video_id == Video.id, VideoReaction.user_id == user.id))
        .where(VideoReaction.value == 1, viewable_condition(user))
        .order_by(VideoReaction.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    return await _rows(session, stmt)


async def history_of(session: AsyncSession, user, offset: int, limit: int) -> list[CardRow]:
    stmt = (
        card_query()
        .join(WatchHistory, and_(WatchHistory.video_id == Video.id, WatchHistory.user_id == user.id))
        .where(viewable_condition(user))
        .order_by(WatchHistory.watched_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    return await _rows(session, stmt)


async def tags_of(session: AsyncSession, video_id: uuid.UUID) -> list[str]:
    rows = await session.scalars(
        select(Tag.name)
        .join(VideoTag, VideoTag.tag_id == Tag.id)
        .where(VideoTag.video_id == video_id)
        .order_by(Tag.name)
    )
    return list(rows)


async def set_tags(session: AsyncSession, video_id: uuid.UUID, names: Sequence[str]) -> None:
    from sqlalchemy.dialects.postgresql import insert

    await session.execute(delete(VideoTag).where(VideoTag.video_id == video_id))
    if not names:
        return
    await session.execute(insert(Tag).values([{"name": n} for n in names]).on_conflict_do_nothing())
    tag_ids = (await session.scalars(select(Tag.id).where(Tag.name.in_(list(names))))).all()
    await session.execute(insert(VideoTag).values([{"video_id": video_id, "tag_id": t} for t in tag_ids]))


async def popular_tags(session: AsyncSession, limit: int) -> list[str]:
    stmt = (
        select(Tag.name)
        .join(VideoTag, VideoTag.tag_id == Tag.id)
        .join(Video, Video.id == VideoTag.video_id)
        .where(listed_condition())
        .group_by(Tag.name)
        .order_by(func.count().desc(), Tag.name)
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def files_of(session: AsyncSession, video_id: uuid.UUID) -> list[VideoFile]:
    return list(await session.scalars(select(VideoFile).where(VideoFile.video_id == video_id)))


async def my_reaction(session: AsyncSession, user_id: uuid.UUID, video_id: uuid.UUID) -> int:
    value = await session.scalar(
        select(VideoReaction.value).where(
            VideoReaction.user_id == user_id, VideoReaction.video_id == video_id
        )
    )
    return value or 0
