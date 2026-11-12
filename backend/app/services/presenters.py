"""Turning ORM rows into API schemas. Storage keys become short-lived presigned URLs here."""

from app.core.config import get_settings
from app.models import Channel, Video
from app.schemas.auth import ChannelBrief
from app.schemas.common import Page
from app.schemas.video import VideoCard
from app.services import storage


def thumbnail_url(host: str, key: str | None) -> str | None:
    if not key:
        return None
    s = get_settings()
    return storage.presign_get(host, s.bucket_media, key, s.image_url_ttl_sec)


def channel_brief(channel: Channel) -> ChannelBrief:
    return ChannelBrief.model_validate(channel)


def video_card(host: str, video: Video, thumb_key: str | None) -> VideoCard:
    return VideoCard(
        id=video.id,
        title=video.title,
        duration_seconds=video.duration_seconds,
        views_count=video.views_count,
        published_at=video.published_at,
        created_at=video.created_at,
        visibility=video.visibility,
        status=video.status,
        thumbnail_url=thumbnail_url(host, thumb_key),
        channel=channel_brief(video.channel),
    )


def card_page(host: str, rows: list[tuple[Video, str | None]], offset: int, limit: int) -> Page[VideoCard]:
    """Repositories fetch limit+1 rows: the extra row only tells whether there is a next page."""
    return Page[VideoCard](
        items=[video_card(host, v, k) for v, k in rows[:limit]],
        has_more=len(rows) > limit,
        offset=offset,
        limit=limit,
    )
