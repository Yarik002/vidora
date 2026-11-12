import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import AuditLog, RefreshSession
from tests.conftest import PASSWORD, Users


async def test_register_sets_cookies_and_me_works(client: httpx.AsyncClient) -> None:
    name = f"reg{uuid.uuid4().hex[:8]}"
    r = await client.post(
        "/api/v1/auth/register", json={"email": f"{name}@example.com", "username": name, "password": PASSWORD}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == name and body["role"] == "user"
    assert body["channel"]["handle"] == name
    assert "password_hash" not in body and "password" not in body
    set_cookie = " ".join(r.headers.get_list("set-cookie")).lower()
    assert "__host-vid_at=" in set_cookie and "httponly" in set_cookie and "secure" in set_cookie
    assert "vid_rt=" in set_cookie and "path=/api/v1/auth" in set_cookie and "samesite=strict" in set_cookie

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["id"] == body["id"]


async def test_duplicate_username_and_email_rejected(users: Users, client: httpx.AsyncClient) -> None:
    alice = await users.new()
    name = alice.me["username"]  # type: ignore[attr-defined]
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "username": name.upper(), "password": PASSWORD},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "username_taken"
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": alice.me["email"].upper(), "username": "freshname", "password": PASSWORD},  # type: ignore[attr-defined]
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


@pytest.mark.parametrize("password", ["short1", "onlyletters", "1234567890"])
async def test_weak_password_rejected(client: httpx.AsyncClient, password: str) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "username": "weakling", "password": password},
    )
    assert r.status_code == 422


async def test_login_by_username_or_email_and_wrong_password(users: Users, client: httpx.AsyncClient) -> None:
    alice = await users.new()
    me = alice.me  # type: ignore[attr-defined]
    for login in (me["username"], me["email"].upper()):
        r = await client.post("/api/v1/auth/login", json={"login": login, "password": PASSWORD})
        assert r.status_code == 200, r.text
    r = await client.post("/api/v1/auth/login", json={"login": me["username"], "password": "Wrong-pass-1"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    r = await client.post("/api/v1/auth/login", json={"login": "nobody-here", "password": "Wrong-pass-1"})
    assert r.status_code == 401  # same answer for unknown users: no account enumeration


async def test_unsafe_request_without_csrf_header_is_rejected(users: Users) -> None:
    alice = await users.new()
    token = alice.headers.pop("X-CSRF-Token")
    r = await alice.post("/api/v1/auth/logout")
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    alice.headers["X-CSRF-Token"] = "forged"
    assert (await alice.post("/api/v1/auth/logout")).status_code == 403
    alice.headers["X-CSRF-Token"] = token
    assert (await alice.post("/api/v1/auth/logout")).status_code == 200


async def test_foreign_origin_is_rejected(users: Users) -> None:
    alice = await users.new()
    r = await alice.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


async def test_bearer_token_flow_for_swagger_needs_no_csrf(users: Users) -> None:
    alice = await users.new()
    me = alice.me  # type: ignore[attr-defined]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as raw:
        r = await raw.post("/api/v1/auth/token", data={"username": me["username"], "password": PASSWORD})
        assert r.status_code == 200
        assert not any("vid_at" in c for c in r.headers.get_list("set-cookie"))  # no auth cookies
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert (await raw.get("/api/v1/auth/me", headers=headers)).json()["id"] == me["id"]
        # Unsafe request with a bearer token and no CSRF header is fine: cookies are not used.
        assert (await raw.post("/api/v1/auth/logout", headers=headers)).status_code == 200


async def test_refresh_rotates_token_and_reuse_revokes_family(users: Users) -> None:
    alice = await users.new()
    old_refresh = alice.cookies.get("vid_rt", path="/api/v1/auth")
    r = await alice.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    new_refresh = alice.cookies.get("vid_rt", path="/api/v1/auth")
    assert new_refresh and new_refresh != old_refresh

    # Pretend the old token was rotated long ago (outside the two-tabs grace window), then reuse it.
    async with SessionLocal() as session:
        await session.execute(
            update(RefreshSession)
            .where(RefreshSession.revoked_at.is_not(None))
            .values(revoked_at=datetime.now(UTC) - timedelta(minutes=5))
        )
        await session.commit()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as attacker:
        r = await attacker.post(
            "/api/v1/auth/refresh",
            headers={"Cookie": f"vid_rt={old_refresh}; vid_csrf=x", "X-CSRF-Token": "x"},
        )
    assert r.status_code == 401

    # The whole family is revoked: the legitimate session is dead too (theft detected).
    r = await alice.post("/api/v1/auth/refresh")
    assert r.status_code == 401
    assert (await alice.get("/api/v1/auth/me")).status_code == 401
    async with SessionLocal() as session:
        actions = (await session.scalars(select(AuditLog.action))).all()
    assert "auth.refresh_reuse_detected" in actions


async def test_logout_kills_access_token_immediately(users: Users) -> None:
    alice = await users.new()
    access = alice.cookies.get("__Host-vid_at")
    assert (await alice.post("/api/v1/auth/logout")).status_code == 200
    r = await alice.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 401  # JWT is still unexpired, but its session is revoked


async def test_disabled_account_cannot_use_its_token(users: Users) -> None:
    alice = await users.new()
    async with SessionLocal() as session:
        from app.models import User

        await session.execute(
            update(User).where(User.id == uuid.UUID(alice.me["id"])).values(is_active=False)  # type: ignore[attr-defined]
        )
        await session.commit()
    assert (await alice.get("/api/v1/auth/me")).status_code == 401


async def test_login_rate_limit(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "login_rate_limit", 3)
    from app.core.redis import get_redis

    await get_redis().delete("rl:login:127.0.0.1")
    codes = [
        (
            await client.post("/api/v1/auth/login", json={"login": "nobody", "password": "Wrong-pass-1"})
        ).status_code
        for _ in range(5)
    ]
    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]
    await get_redis().delete("rl:login:127.0.0.1")
