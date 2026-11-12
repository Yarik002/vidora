import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFound
from app.models import Channel, Subscription, User, Video
from app.schemas.auth import ChannelBrief
from app.schemas.channel import ChannelDetail, ChannelUpdate, SubscriptionOut
from app.services.access import listed_condition


async def get_by_handle(session: AsyncSession, handle: str) -> Channel:
    channel = await session.scalar(select(Channel).where(Channel.handle == handle))
    if channel is None:
        raise NotFound("Channel not found", code="channel_not_found")
    return channel


async def detail(session: AsyncSession, channel: Channel, user: User | None) -> ChannelDetail:
    videos_count = await session.scalar(
        select(func.count()).select_from(Video).where(Video.channel_id == channel.id, listed_condition())
    )
    subscribed = False
    if user is not None:
        subscribed = (
            await session.scalar(
                select(Subscription.channel_id).where(
                    Subscription.subscriber_id == user.id, Subscription.channel_id == channel.id
                )
            )
        ) is not None
    return ChannelDetail(
        id=channel.id,
        handle=channel.handle,
        title=channel.title,
        avatar_color=channel.avatar_color,
        subscribers_count=channel.subscribers_count,
        description=channel.description,
        created_at=channel.created_at,
        videos_count=videos_count or 0,
        is_subscribed=subscribed,
        is_owner=user is not None and channel.owner_id == user.id,
    )


async def update_own(session: AsyncSession, user: User, data: ChannelUpdate) -> ChannelDetail:
    channel = await session.get(Channel, user.channel.id)
    assert channel is not None
    for name, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(channel, name, value)
    await session.commit()
    return await detail(session, channel, user)


async def set_subscription(
    session: AsyncSession, user: User, channel_id: uuid.UUID, subscribe: bool
) -> SubscriptionOut:
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise NotFound("Channel not found", code="channel_not_found")
    if channel.owner_id == user.id:
        raise AppError("You can't subscribe to your own channel", code="self_subscription")
    if subscribe:
        result = await session.execute(
            insert(Subscription)
            .values(subscriber_id=user.id, channel_id=channel.id)
            .on_conflict_do_nothing()
            .returning(Subscription.channel_id)
        )
        delta = 1 if result.first() is not None else 0
    else:
        result = await session.execute(
            delete(Subscription)
            .where(Subscription.subscriber_id == user.id, Subscription.channel_id == channel.id)
            .returning(Subscription.channel_id)
        )
        delta = -1 if result.first() is not None else 0
    # Counter changes only if a row was really inserted/deleted: repeated clicks are idempotent.
    count = await session.scalar(
        update(Channel)
        .where(Channel.id == channel.id)
        .values(subscribers_count=Channel.subscribers_count + delta)
        .returning(Channel.subscribers_count)
    )
    await session.commit()
    return SubscriptionOut(subscribed=subscribe, subscribers_count=count or 0)


async def subscriptions_of(session: AsyncSession, user: User) -> list[ChannelBrief]:
    rows = await session.scalars(
        select(Channel)
        .join(Subscription, Subscription.channel_id == Channel.id)
        .where(Subscription.subscriber_id == user.id)
        .order_by(Channel.title)
    )
    return [ChannelBrief.model_validate(c) for c in rows]


async def search_channels(session: AsyncSession, q: str, limit: int) -> list[ChannelBrief]:
    pattern = f"%{q.replace('%', '').replace('_', '')}%"
    rows = await session.scalars(
        select(Channel)
        .where((Channel.title.ilike(pattern)) | (Channel.handle.ilike(pattern)))
        .order_by(Channel.subscribers_count.desc())
        .limit(limit)
    )
    return [ChannelBrief.model_validate(c) for c in rows]
