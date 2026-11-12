from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import public_host
from app.db.session import get_session
from app.repositories import videos as videos_repo
from app.schemas.auth import ChannelBrief
from app.schemas.common import Page
from app.schemas.video import VideoCard
from app.services import channel_service
from app.services.presenters import card_page

router = APIRouter(prefix="/search", tags=["search"])


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
    rows = await videos_repo.search(session, q.strip(), offset, limit)
    return card_page(public_host(request), rows, offset, limit)


@router.get("/channels", response_model=list[ChannelBrief], summary="Channels matching the query")
async def search_channels(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=3, ge=1, le=10),
    session: AsyncSession = Depends(get_session),
) -> list[ChannelBrief]:
    return await channel_service.search_channels(session, q.strip(), limit)
