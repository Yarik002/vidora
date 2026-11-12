import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, current_user_optional
from app.db.session import get_session
from app.models import User
from app.schemas.comment import CommentIn, CommentOut, CommentReactionIn, CommentUpdate
from app.schemas.common import Message, Page
from app.services import comment_service

router = APIRouter(tags=["comments"])


@router.get("/videos/{video_id}/comments", response_model=Page[CommentOut])
async def list_comments(
    video_id: uuid.UUID,
    sort: Literal["top", "new"] = "top",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> Page[CommentOut]:
    return await comment_service.list_comments(session, video_id, user, sort, offset, limit)


@router.post("/videos/{video_id}/comments", response_model=CommentOut, status_code=201)
async def create_comment(
    video_id: uuid.UUID,
    data: CommentIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CommentOut:
    return await comment_service.create(session, video_id, user, data)


@router.get("/comments/{comment_id}/replies", response_model=Page[CommentOut])
async def list_replies(
    comment_id: uuid.UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> Page[CommentOut]:
    return await comment_service.list_replies(session, comment_id, user, offset, limit)


@router.patch("/comments/{comment_id}", response_model=CommentOut)
async def edit_comment(
    comment_id: uuid.UUID,
    data: CommentUpdate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CommentOut:
    return await comment_service.edit(session, comment_id, user, data)


@router.delete("/comments/{comment_id}", response_model=Message)
async def delete_comment(
    comment_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> Message:
    await comment_service.remove(session, comment_id, user)
    return Message()


@router.put("/comments/{comment_id}/reaction")
async def react_comment(
    comment_id: uuid.UUID,
    data: CommentReactionIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await comment_service.react(session, comment_id, user, data.value)
