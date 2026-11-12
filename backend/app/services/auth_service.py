import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, TooManyRequests, Unauthorized
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    password_needs_rehash,
    verify_password,
)
from app.models import Channel, RefreshSession, Role, User
from app.repositories import users as users_repo
from app.schemas.auth import RegisterIn
from app.services.audit import audit

AVATAR_COLORS = ["#3ea6ff", "#ff4e45", "#2ba640", "#f9a825", "#ab47bc", "#ef6c00", "#26a69a", "#5c6bc0"]
# A rotated token presented again within this window is treated as a benign race
# (two tabs refreshing at once), not as theft.
REUSE_GRACE = timedelta(seconds=15)
# Per-account brute-force guard (the per-IP limit alone doesn't stop a distributed guesser).
MAX_FAILED_LOGINS = 10
FAILED_LOGIN_WINDOW_SEC = 15 * 60


@dataclass
class Tokens:
    access: str
    refresh: str
    user: User


@dataclass
class ClientInfo:
    ip: str | None
    user_agent: str | None


async def _issue(
    session: AsyncSession, user: User, client: ClientInfo, family_id: uuid.UUID | None = None
) -> Tokens:
    settings = get_settings()
    refresh, refresh_hash = new_opaque_token()
    row = RefreshSession(
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=refresh_hash,
        user_agent=(client.user_agent or "")[:255] or None,
        ip=client.ip,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_ttl_days),
    )
    session.add(row)
    await session.flush()
    return Tokens(access=create_access_token(user.id, user.role.value, row.id), refresh=refresh, user=user)


async def register(
    session: AsyncSession, data: RegisterIn, client: ClientInfo, role: Role = Role.USER
) -> Tokens:
    email_taken, username_taken = await users_repo.exists_email_or_username(
        session, data.email, data.username
    )
    if email_taken:
        raise Conflict("Email is already registered", code="email_taken")
    if username_taken or await users_repo.handle_taken(session, data.username):
        raise Conflict("Username is already taken", code="username_taken")

    user = User(
        email=data.email, username=data.username, password_hash=hash_password(data.password), role=role
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:  # two concurrent registrations passed the check above
        await session.rollback()
        raise Conflict("Email or username is already taken", code="username_taken") from exc
    channel = Channel(
        owner_id=user.id,
        handle=data.username.lower(),
        title=data.channel_title or data.username,
        avatar_color=random.choice(AVATAR_COLORS),  # noqa: S311 - cosmetic, not security
    )
    session.add(channel)
    await session.flush()
    user.channel = channel
    audit(session, "user.register", actor_id=user.id, entity_type="user", entity_id=user.id, ip=client.ip)
    tokens = await _issue(session, user, client)
    await session.commit()
    return tokens


async def login(session: AsyncSession, login_value: str, password: str, client: ClientInfo) -> Tokens:
    login_value = login_value.strip()
    fail_key = f"rl:loginfail:{login_value.lower()}"
    redis = get_redis()
    if int(await redis.get(fail_key) or 0) >= MAX_FAILED_LOGINS:
        raise TooManyRequests("Too many failed attempts for this account, try again later")
    user = await users_repo.get_user_by_login(session, login_value)
    # verify_password runs a full argon2 check even for unknown users (equal timing).
    if not verify_password(user.password_hash if user else None, password) or user is None:
        audit(session, "auth.login_failed", actor_id=user.id if user else None, ip=client.ip)
        await session.commit()
        if await redis.incr(fail_key) == 1:
            await redis.expire(fail_key, FAILED_LOGIN_WINDOW_SEC)
        raise Unauthorized("Wrong login or password", code="invalid_credentials")
    if not user.is_active:
        raise Forbidden("Account is disabled", code="account_disabled")
    await redis.delete(fail_key)
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    audit(session, "auth.login", actor_id=user.id, ip=client.ip)
    tokens = await _issue(session, user, client)
    await session.commit()
    return tokens


async def refresh(session: AsyncSession, refresh_token: str | None, client: ClientInfo) -> Tokens:
    if not refresh_token:
        raise Unauthorized("No refresh token", code="no_refresh_token")
    row = await users_repo.get_refresh_by_hash(session, hash_token(refresh_token))
    now = datetime.now(UTC)
    if row is None:
        raise Unauthorized("Invalid refresh token", code="invalid_refresh_token")
    if row.revoked_at is not None:
        if now - row.revoked_at > REUSE_GRACE:
            # A token that was already rotated is used again: likely stolen. Kill the whole family.
            await users_repo.revoke_family(session, row.family_id)
            audit(
                session,
                "auth.refresh_reuse_detected",
                actor_id=row.user_id,
                ip=client.ip,
                family=row.family_id,
            )
            await session.commit()
        raise Unauthorized("Refresh token was revoked", code="invalid_refresh_token")
    if row.expires_at <= now:
        raise Unauthorized("Refresh token expired", code="invalid_refresh_token")
    user = await users_repo.get_user(session, row.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Account is not available", code="invalid_refresh_token")
    row.revoked_at = now
    tokens = await _issue(session, user, client, family_id=row.family_id)
    await session.commit()
    return tokens


async def logout(session: AsyncSession, refresh_token: str | None, user: User | None) -> None:
    if refresh_token:
        row = await users_repo.get_refresh_by_hash(session, hash_token(refresh_token))
        if row is not None:
            await users_repo.revoke_family(session, row.family_id)
    if user is not None:
        audit(session, "auth.logout", actor_id=user.id)
    await session.commit()


async def issue_bearer(session: AsyncSession, login_value: str, password: str, client: ClientInfo) -> str:
    """OAuth2 password flow for Swagger and API clients: bearer token, no cookies."""
    tokens = await login(session, login_value, password, client)
    return tokens.access
