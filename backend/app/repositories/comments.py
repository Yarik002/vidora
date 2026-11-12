import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Comment, CommentReaction, User


def _base() -> Select:
    return select(Comment).options(joinedload(Comment.author).joinedload(User.channel))


async def get(session: AsyncSession, comment_id: uuid.UUID) -> Comment | None:
    return await session.scalar(_base().where(Comment.id == comment_id))


async def list_top(
    session: AsyncSession, video_id: uuid.UUID, sort: str, offset: int, limit: int
) -> list[Comment]:
    order = (
        (Comment.likes_count.desc(), Comment.replies_count.desc(), Comment.created_at.desc())
        if sort == "top"
        else (Comment.created_at.desc(),)
    )
    stmt = (
        _base()
        .where(Comment.video_id == video_id, Comment.parent_id.is_(None))
        .order_by(*order, Comment.id)
        .offset(offset)
        .limit(limit + 1)
    )
    return list((await session.scalars(stmt)).unique())


async def list_replies(session: AsyncSession, parent_id: uuid.UUID, offset: int, limit: int) -> list[Comment]:
    stmt = (
        _base()
        .where(Comment.parent_id == parent_id)
        .order_by(Comment.created_at.asc(), Comment.id)
        .offset(offset)
        .limit(limit + 1)
    )
    return list((await session.scalars(stmt)).unique())


async def my_reactions(
    session: AsyncSession, user_id: uuid.UUID, comment_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not comment_ids:
        return {}
    rows = await session.execute(
        select(CommentReaction.comment_id, CommentReaction.value).where(
            CommentReaction.user_id == user_id, CommentReaction.comment_id.in_(comment_ids)
        )
    )
    return {r.comment_id: r.value for r in rows}
