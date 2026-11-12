import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.models import Comment, CommentReaction, User, Video
from app.repositories import comments as comments_repo
from app.schemas.comment import CommentAuthor, CommentIn, CommentOut, CommentUpdate
from app.schemas.common import Page
from app.services.access import get_viewable_video, is_owner, is_staff

DELETED_BODY = "[deleted]"


def _present(c: Comment, video: Video, user: User | None, my: dict[uuid.UUID, int]) -> CommentOut:
    deleted = c.deleted_at is not None
    author = None
    if not deleted:
        ch = c.author.channel
        author = CommentAuthor(
            id=c.author.id,
            username=c.author.username,
            channel_handle=ch.handle,
            channel_title=ch.title,
            avatar_color=ch.avatar_color,
        )
    mine = user is not None and c.author_id == user.id
    return CommentOut(
        id=c.id,
        video_id=c.video_id,
        parent_id=c.parent_id,
        body=None if deleted else c.body,
        author=author,
        likes_count=c.likes_count,
        replies_count=c.replies_count,
        created_at=c.created_at,
        edited=c.edited_at is not None,
        is_deleted=deleted,
        is_video_owner=not deleted and c.author.channel.id == video.channel_id,
        my_reaction=my.get(c.id, 0),
        can_edit=mine and not deleted,
        can_delete=not deleted and (mine or is_owner(user, video) or is_staff(user)),
    )


async def _page(
    session: AsyncSession, video: Video, user: User | None, rows: list[Comment], offset: int, limit: int
) -> Page[CommentOut]:
    rows_page = rows[:limit]
    my = await comments_repo.my_reactions(session, user.id, [c.id for c in rows_page]) if user else {}
    return Page[CommentOut](
        items=[_present(c, video, user, my) for c in rows_page],
        has_more=len(rows) > limit,
        offset=offset,
        limit=limit,
    )


async def list_comments(
    session: AsyncSession, video_id: uuid.UUID, user: User | None, sort: str, offset: int, limit: int
) -> Page[CommentOut]:
    video = await get_viewable_video(session, video_id, user)
    rows = await comments_repo.list_top(session, video.id, sort, offset, limit)
    return await _page(session, video, user, rows, offset, limit)


async def list_replies(
    session: AsyncSession, comment_id: uuid.UUID, user: User | None, offset: int, limit: int
) -> Page[CommentOut]:
    parent = await _get_visible_comment(session, comment_id, user)
    video = await session.get(Video, parent.video_id)
    assert video is not None
    rows = await comments_repo.list_replies(session, parent.id, offset, limit)
    return await _page(session, video, user, rows, offset, limit)


async def _get_visible_comment(session: AsyncSession, comment_id: uuid.UUID, user: User | None) -> Comment:
    comment = await comments_repo.get(session, comment_id)
    if comment is None:
        raise NotFound("Comment not found", code="comment_not_found")
    await get_viewable_video(session, comment.video_id, user)  # comments inherit the video's access rules
    return comment


async def create(session: AsyncSession, video_id: uuid.UUID, user: User, data: CommentIn) -> CommentOut:
    video = await get_viewable_video(session, video_id, user)
    parent_id = None
    if data.parent_id is not None:
        # Lock the parent: a concurrent hard delete must not race with this reply.
        parent = await session.get(Comment, data.parent_id, with_for_update=True)
        if parent is None or parent.video_id != video.id or parent.deleted_at is not None:
            raise NotFound("Parent comment not found", code="comment_not_found")
        # One level of nesting like YouTube: a reply to a reply goes to the same thread.
        parent_id = parent.parent_id or parent.id
    comment = Comment(video_id=video.id, author_id=user.id, parent_id=parent_id, body=data.body)
    session.add(comment)
    await session.flush()
    await session.execute(
        update(Video).where(Video.id == video.id).values(comments_count=Video.comments_count + 1)
    )
    if parent_id is not None:
        await session.execute(
            update(Comment).where(Comment.id == parent_id).values(replies_count=Comment.replies_count + 1)
        )
    await session.commit()
    fresh = await comments_repo.get(session, comment.id)
    assert fresh is not None
    return _present(fresh, video, user, {})


async def edit(session: AsyncSession, comment_id: uuid.UUID, user: User, data: CommentUpdate) -> CommentOut:
    comment = await _get_visible_comment(session, comment_id, user)
    if comment.author_id != user.id or comment.deleted_at is not None:
        raise NotFound("Comment not found", code="comment_not_found")
    comment.body = data.body
    comment.edited_at = datetime.now(UTC)
    await session.commit()
    fresh = await comments_repo.get(session, comment.id)
    video = await session.get(Video, comment.video_id)
    assert fresh is not None and video is not None
    return _present(fresh, video, user, {})


async def remove(session: AsyncSession, comment_id: uuid.UUID, user: User) -> Comment:
    """Author, video owner or staff. A comment with replies is soft-deleted to keep the thread."""
    comment = await _get_visible_comment(session, comment_id, user)
    # Re-read under a row lock: replies_count decides soft vs hard delete.
    await session.execute(select(Comment.id).where(Comment.id == comment.id).with_for_update())
    await session.refresh(comment, attribute_names=["replies_count", "deleted_at", "parent_id"])
    video = await session.get(Video, comment.video_id)
    assert video is not None
    if comment.deleted_at is not None or not (
        comment.author_id == user.id or is_owner(user, video) or is_staff(user)
    ):
        raise NotFound("Comment not found", code="comment_not_found")
    await delete_comment_row(session, comment)
    await session.commit()
    return comment


async def delete_comment_row(session: AsyncSession, comment: Comment) -> None:
    """Shared with moderation. Keeps counters consistent."""
    removed = 1
    if comment.parent_id is None and comment.replies_count > 0:
        comment.deleted_at = datetime.now(UTC)
        comment.body = DELETED_BODY
    else:
        await session.execute(delete(Comment).where(Comment.id == comment.id))
        if comment.parent_id is not None:
            await session.execute(
                update(Comment)
                .where(Comment.id == comment.parent_id)
                .values(replies_count=Comment.replies_count - 1)
            )
    await session.execute(
        update(Video)
        .where(Video.id == comment.video_id)
        .values(comments_count=Video.comments_count - removed)
    )


async def react(session: AsyncSession, comment_id: uuid.UUID, user: User, value: int) -> dict:
    comment = await _get_visible_comment(session, comment_id, user)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"creact:{user.id}:{comment.id}"}
    )
    old = (
        await session.scalar(
            select(CommentReaction.value).where(
                CommentReaction.user_id == user.id, CommentReaction.comment_id == comment.id
            )
        )
        or 0
    )
    if value == 0:
        await session.execute(
            delete(CommentReaction).where(
                CommentReaction.user_id == user.id, CommentReaction.comment_id == comment.id
            )
        )
    else:
        await session.execute(
            insert(CommentReaction)
            .values(user_id=user.id, comment_id=comment.id, value=value)
            .on_conflict_do_update(
                index_elements=[CommentReaction.user_id, CommentReaction.comment_id], set_={"value": value}
            )
        )
    delta = int(value == 1) - int(old == 1)
    likes = await session.scalar(
        update(Comment)
        .where(Comment.id == comment.id)
        .values(likes_count=Comment.likes_count + delta)
        .returning(Comment.likes_count)
    )
    await session.commit()
    return {"likes_count": likes, "my_reaction": value}
