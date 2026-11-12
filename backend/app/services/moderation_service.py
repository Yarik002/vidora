"""Reports, moderation decisions and user administration.

Every decision writes a ModerationAction (who, what, why) and an audit record in the same
transaction as the change itself.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import AppError, Conflict, NotFound
from app.models import (
    Comment,
    ModerationAction,
    ModerationActionType,
    ModerationState,
    Report,
    ReportStatus,
    User,
    Video,
)
from app.repositories import users as users_repo
from app.repositories import videos as videos_repo
from app.schemas.common import Page
from app.schemas.moderation import (
    AdminUserOut,
    AdminUserUpdate,
    ModerationActionOut,
    ReportCreated,
    ReportedComment,
    ReportIn,
    ReportOut,
)
from app.services.access import get_viewable_video
from app.services.audit import audit
from app.services.comment_service import delete_comment_row
from app.services.presenters import card_page, video_card


async def create_report(session: AsyncSession, user: User, data: ReportIn) -> ReportCreated:
    if data.video_id is not None:
        await get_viewable_video(session, data.video_id, user)  # can't report what you can't see
    else:
        comment = await session.get(Comment, data.comment_id)
        if comment is None or comment.deleted_at is not None:
            raise NotFound("Comment not found", code="comment_not_found")
        await get_viewable_video(session, comment.video_id, user)
    report = Report(
        reporter_id=user.id,
        video_id=data.video_id,
        comment_id=data.comment_id,
        reason=data.reason,
        details=data.details.strip(),
    )
    session.add(report)
    try:
        await session.commit()
    except IntegrityError as exc:  # partial unique index: one open report per user per video
        await session.rollback()
        raise Conflict("You have already reported this video", code="already_reported") from exc
    return ReportCreated(id=report.id, status=report.status)


async def list_reports(
    session: AsyncSession, status: ReportStatus, offset: int, limit: int, host: str
) -> Page[ReportOut]:
    reporter = aliased(User)
    comment_author = aliased(User)
    stmt = (
        select(Report, reporter.username, Comment, comment_author.username)
        .outerjoin(reporter, reporter.id == Report.reporter_id)
        .outerjoin(Comment, Comment.id == Report.comment_id)
        .outerjoin(comment_author, comment_author.id == Comment.author_id)
        .where(Report.status == status)
        .order_by(Report.created_at.asc() if status == ReportStatus.OPEN else Report.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    rows = (await session.execute(stmt)).all()
    video_ids = {r[0].video_id for r in rows if r[0].video_id}
    cards = {}
    for vid in video_ids:
        row = await videos_repo.get_with_channel(session, vid)
        if row:
            cards[vid] = row
    # how many open reports each target has (moderators see the most reported first-hand)
    counts: dict[uuid.UUID, int] = {}
    targets = [r[0].video_id or r[0].comment_id for r in rows]
    if targets:
        for col in (Report.video_id, Report.comment_id):
            res = await session.execute(
                select(col, func.count())
                .where(col.in_(targets), Report.status == ReportStatus.OPEN)
                .group_by(col)
            )
            counts.update({k: v for k, v in res.all() if k is not None})

    items = []
    for report, reporter_name, comment, comment_author_name in rows[:limit]:
        card = cards.get(report.video_id) if report.video_id else None
        items.append(
            ReportOut(
                id=report.id,
                reason=report.reason,
                details=report.details,
                status=report.status,
                created_at=report.created_at,
                reporter=reporter_name,
                video=video_card(host, card[0], card[1]) if card else None,
                video_moderation_state=card[0].moderation_state if card else None,
                comment=ReportedComment(
                    id=comment.id,
                    body=None if comment.deleted_at else comment.body,
                    author=comment_author_name,
                    video_id=comment.video_id,
                )
                if comment
                else None,
                reports_on_target=counts.get(report.video_id or report.comment_id, 0),
            )
        )
    return Page[ReportOut](items=items, has_more=len(rows) > limit, offset=offset, limit=limit)


def _record(
    session: AsyncSession,
    moderator: User,
    action: ModerationActionType,
    reason: str,
    *,
    video_id: uuid.UUID | None = None,
    comment_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
) -> None:
    session.add(
        ModerationAction(
            moderator_id=moderator.id,
            action=action,
            reason=reason,
            video_id=video_id,
            comment_id=comment_id,
            target_user_id=target_user_id,
            report_id=report_id,
        )
    )
    audit(
        session,
        f"moderation.{action.value}",
        actor_id=moderator.id,
        entity_type="video" if video_id else "comment" if comment_id else "user",
        entity_id=video_id or comment_id or target_user_id,
        reason=reason,
    )


async def _close_reports(
    session: AsyncSession, moderator: User, status: ReportStatus, *, video_id=None, comment_id=None
) -> None:
    cond = Report.video_id == video_id if video_id else Report.comment_id == comment_id
    await session.execute(
        update(Report)
        .where(cond, Report.status == ReportStatus.OPEN)
        .values(status=status, resolved_by=moderator.id, resolved_at=datetime.now(UTC))
    )


async def set_video_hidden(
    session: AsyncSession, moderator: User, video_id: uuid.UUID, hidden: bool, reason: str, report_id=None
) -> None:
    video = await session.get(Video, video_id)
    if video is None:
        raise NotFound("Video not found", code="video_not_found")
    video.moderation_state = ModerationState.HIDDEN if hidden else ModerationState.ACTIVE
    _record(
        session,
        moderator,
        ModerationActionType.HIDE_VIDEO if hidden else ModerationActionType.RESTORE_VIDEO,
        reason,
        video_id=video.id,
        report_id=report_id,
    )
    if hidden:
        await _close_reports(session, moderator, ReportStatus.RESOLVED, video_id=video.id)
    await session.commit()


async def delete_comment(
    session: AsyncSession, moderator: User, comment_id: uuid.UUID, reason: str, report_id=None
) -> None:
    comment = await session.get(Comment, comment_id)
    if comment is None or comment.deleted_at is not None:
        raise NotFound("Comment not found", code="comment_not_found")
    _record(
        session,
        moderator,
        ModerationActionType.DELETE_COMMENT,
        reason,
        comment_id=comment.id,  # becomes NULL if the row is hard-deleted (FK ON DELETE SET NULL)
        video_id=comment.video_id,
        target_user_id=comment.author_id,
        report_id=report_id,
    )
    await _close_reports(session, moderator, ReportStatus.RESOLVED, comment_id=comment.id)
    await delete_comment_row(session, comment)
    await session.commit()


async def dismiss_report(session: AsyncSession, moderator: User, report_id: uuid.UUID, reason: str) -> None:
    report = await session.get(Report, report_id)
    if report is None:
        raise NotFound("Report not found", code="report_not_found")
    if report.status != ReportStatus.OPEN:
        raise Conflict("Report is already closed", code="report_closed")
    report.status = ReportStatus.DISMISSED
    report.resolved_by = moderator.id
    report.resolved_at = datetime.now(UTC)
    _record(
        session,
        moderator,
        ModerationActionType.DISMISS_REPORT,
        reason,
        report_id=report.id,
        video_id=report.video_id,
    )
    await session.commit()


async def hidden_videos(session: AsyncSession, offset: int, limit: int, host: str):
    stmt = (
        videos_repo.card_query()
        .where(Video.moderation_state == ModerationState.HIDDEN)
        .order_by(Video.updated_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    rows = [(r[0], r[1]) for r in (await session.execute(stmt)).unique().all()]
    return card_page(host, rows, offset, limit)


async def list_actions(session: AsyncSession, offset: int, limit: int) -> Page[ModerationActionOut]:
    moderator = aliased(User)
    target = aliased(User)
    stmt = (
        select(ModerationAction, moderator.username, Video.title, target.username)
        .outerjoin(moderator, moderator.id == ModerationAction.moderator_id)
        .outerjoin(Video, Video.id == ModerationAction.video_id)
        .outerjoin(target, target.id == ModerationAction.target_user_id)
        .order_by(ModerationAction.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        ModerationActionOut(
            id=a.id,
            action=a.action.value,
            moderator=mod,
            reason=a.reason,
            created_at=a.created_at,
            video_id=a.video_id,
            video_title=title,
            comment_id=a.comment_id,
            target_user=tgt,
        )
        for a, mod, title, tgt in rows[:limit]
    ]
    return Page[ModerationActionOut](items=items, has_more=len(rows) > limit, offset=offset, limit=limit)


# --- admin: users ------------------------------------------------------------------------------


async def list_users(session: AsyncSession, q: str | None, offset: int, limit: int) -> Page[AdminUserOut]:
    from app.models import Channel

    videos_count = (
        select(func.count())
        .select_from(Video)
        .join(Channel, Channel.id == Video.channel_id)
        .where(Channel.owner_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    stmt = select(User, videos_count).order_by(User.created_at.desc()).offset(offset).limit(limit + 1)
    if q:
        pattern = f"%{q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(User.username.ilike(pattern) | User.email.ilike(pattern))
    rows = (await session.execute(stmt)).all()
    items = [
        AdminUserOut(
            id=u.id,
            username=u.username,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
            videos_count=cnt or 0,
        )
        for u, cnt in rows[:limit]
    ]
    return Page[AdminUserOut](items=items, has_more=len(rows) > limit, offset=offset, limit=limit)


async def update_user(
    session: AsyncSession, admin: User, user_id: uuid.UUID, data: AdminUserUpdate
) -> AdminUserOut:
    if user_id == admin.id:
        raise AppError("Admins can't change their own role or ban themselves", code="self_change")
    target = await session.get(User, user_id)
    if target is None:
        raise NotFound("User not found", code="user_not_found")
    if data.role is not None and data.role != target.role:
        old = target.role
        target.role = data.role
        _record(
            session,
            admin,
            ModerationActionType.CHANGE_ROLE,
            data.reason or f"{old.value} -> {data.role.value}",
            target_user_id=target.id,
        )
    if data.is_active is not None and data.is_active != target.is_active:
        target.is_active = data.is_active
        _record(
            session,
            admin,
            ModerationActionType.UNBAN_USER if data.is_active else ModerationActionType.BAN_USER,
            data.reason,
            target_user_id=target.id,
        )
        if not data.is_active:
            await users_repo.revoke_all_for_user(session, target.id)  # ban = logout everywhere
    await session.commit()
    return await _admin_user_out(session, target)


async def _admin_user_out(session: AsyncSession, user: User) -> AdminUserOut:
    from app.models import Channel

    count = await session.scalar(
        select(func.count())
        .select_from(Video)
        .join(Channel, Channel.id == Video.channel_id)
        .where(Channel.owner_id == user.id)
    )
    return AdminUserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        videos_count=count or 0,
    )
