import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Channel, RefreshSession, User


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.scalar(select(User).options(joinedload(User.channel)).where(User.id == user_id))


async def get_user_by_login(session: AsyncSession, login: str) -> User | None:
    # email and username are CITEXT: comparison is case-insensitive and uses the unique indexes.
    return await session.scalar(
        select(User).options(joinedload(User.channel)).where(or_(User.email == login, User.username == login))
    )


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    return await session.scalar(select(User).where(User.username == username))


async def exists_email_or_username(session: AsyncSession, email: str, username: str) -> tuple[bool, bool]:
    rows = (
        await session.execute(
            select(User.email, User.username).where(or_(User.email == email, User.username == username))
        )
    ).all()
    return (
        any(r.email.lower() == email.lower() for r in rows),
        any(r.username.lower() == username.lower() for r in rows),
    )


async def handle_taken(session: AsyncSession, handle: str) -> bool:
    return (await session.scalar(select(Channel.id).where(Channel.handle == handle))) is not None


async def get_active_user_for_session(
    session: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> User | None:
    """User behind an access token, only if the account is active and its refresh session
    was not revoked (logout / token theft / ban take effect immediately)."""
    now = datetime.now(UTC)
    return await session.scalar(
        select(User)
        .options(joinedload(User.channel))
        .join(RefreshSession, RefreshSession.user_id == User.id)
        .where(
            User.id == user_id,
            User.is_active.is_(True),
            RefreshSession.id == session_id,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > now,
        )
    )


async def get_refresh_by_hash(session: AsyncSession, token_hash: str) -> RefreshSession | None:
    return await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == token_hash).with_for_update()
    )


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshSession)
        .where(RefreshSession.family_id == family_id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
