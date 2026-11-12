from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import public_host
from app.core.errors import AppError
from app.db.session import get_session
from app.schemas.auth import ChannelBrief
from app.schemas.common import Page
from app.schemas.video import VideoCard
from app.services import channel_service, feed_service

router = APIRouter(prefix="/search", tags=["search"])


class EmptyQuery(AppError):
    status_code = 422
    code = "validation_error"
    default_message = "Search query is empty"


def _clean(q: str) -> str:
    """Validate the query after trimming: '   ' must not turn into 'match everything'."""
    q = " ".join(q.split())
    if not q:
        raise EmptyQuery()
    return q


@router.get(
    "",
    response_model=Page[VideoCard],
    summary="Search public videos by title/description",
    description="PostgreSQL full-text search (russian stemming, title weighted higher) "
    "combined with trigram similarity, so typos and partial words still match.",
)
async def search_videos(
    request: Request,
    q: str = Query(min_length=1, max_length=100),
    offset: int = Query(default=0, ge=0, le=1000),
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> Page[VideoCard]:
    return await feed_service.search(session, public_host(request), _clean(q), offset, limit)


@router.get("/channels", response_model=list[ChannelBrief], summary="Channels matching the query")
async def search_channels(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=3, ge=1, le=10),
    session: AsyncSession = Depends(get_session),
) -> list[ChannelBrief]:
    return await channel_service.search_channels(session, _clean(q), limit)
