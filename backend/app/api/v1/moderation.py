"""Reports (any user), moderation queue (moderator, admin) and user administration (admin)."""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, public_host, require_admin, require_moderator
from app.db.session import get_session
from app.models import ReportStatus, User
from app.schemas.common import Message, Page
from app.schemas.moderation import (
    AdminUserOut,
    AdminUserUpdate,
    ModerationActionOut,
    ModerationDecision,
    ReportCreated,
    ReportIn,
    ReportOut,
)
from app.schemas.video import VideoCard
from app.services import moderation_service

reports_router = APIRouter(prefix="/reports", tags=["moderation"])
router = APIRouter(prefix="/moderation", tags=["moderation"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])


@reports_router.post("", response_model=ReportCreated, status_code=201, summary="Report a video or a comment")
async def create_report(
    data: ReportIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> ReportCreated:
    return await moderation_service.create_report(session, user, data)


@router.get("/reports", response_model=Page[ReportOut])
async def list_reports(
    request: Request,
    status: ReportStatus = ReportStatus.OPEN,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    _: User = Depends(require_moderator),
    session: AsyncSession = Depends(get_session),
) -> Page[ReportOut]:
    return await moderation_service.list_reports(session, status, offset, limit, public_host(request))


@router.post(
    "/videos/{video_id}/hide", response_model=Message, summary="Hide a video from everyone but staff/owner"
)
async def hide_video(
    video_id: uuid.UUID,
    data: ModerationDecision,
    moderator: User = Depends(require_moderator),
    session: AsyncSession = Depends(get_session),
) -> Message:
    await moderation_service.set_video_hidden(session, moderator, video_id, True, data.reason, data.report_id)
    return Message()


@router.post("/videos/{video_id}/restore", response_model=Message)
async def restore_video(
    video_id: uuid.UUID,
    data: ModerationDecision,
    moderator: User = Depends(require_moderator),
    session: AsyncSession = Depends(get_session),
) -> Message:
    await moderation_service.set_video_hidden(session, moderator, video_id, False, data.reason)
    return Message()


@router.get("/videos/hidden", response_model=Page[VideoCard])
async def hidden_videos(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    _: User = Depends(require_moderator),
    session: AsyncSession = Depends(get_session),
) -> Page[VideoCard]:
    return await moderation_service.hidden_videos(session, offset, limit, public_host(request))


@router.post("/comments/{comment_id}/delete", response_model=Message)
async def delete_comment(
    comment_id: uuid.UUID,
    data: ModerationDecision,
    moderator: User = Depends(require_moderator),
    session: AsyncSession = Depends(get_session),
) -> Message:
    await moderation_service.delete_comment(session, moderator, comment_id, data.reason, data.report_id)
    return Message()


@router.post("/reports/{report_id}/dismiss", response_model=Message, summary="No violation: close the report")
async def dismiss_report(
    report_id: uuid.UUID,
    data: ModerationDecision,
    moderator: User = Depends(require_moderator),
    session: AsyncSession = Depends(get_session),
) -> Message:
    await moderation_service.dismiss_report(session, moderator, report_id, data.reason)
    return Message()


@router.get("/actions", response_model=Page[ModerationActionOut], summary="Moderation log")
async def actions(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    _: User = Depends(require_moderator),
    session: AsyncSession = Depends(get_session),
) -> Page[ModerationActionOut]:
    return await moderation_service.list_actions(session, offset, limit)


@admin_router.get("/users", response_model=Page[AdminUserOut])
async def list_users(
    q: str | None = Query(default=None, max_length=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Page[AdminUserOut]:
    return await moderation_service.list_users(session, q, offset, limit)


@admin_router.patch("/users/{user_id}", response_model=AdminUserOut, summary="Change role or ban/unban")
async def update_user(
    user_id: uuid.UUID,
    data: AdminUserUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserOut:
    return await moderation_service.update_user(session, admin, user_id, data)
