"""Roles: user / moderator / admin. Moderation hides videos everywhere and is fully logged."""

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import AuditLog, ModerationAction, Role
from tests.conftest import Users, make_ready_video


async def test_regular_user_has_no_access_to_moderation_or_admin(users: Users) -> None:
    alice = await users.new()
    owner = await users.new()
    vid = await make_ready_video(owner)
    assert (await alice.get("/api/v1/moderation/reports")).status_code == 403
    assert (
        await alice.post(f"/api/v1/moderation/videos/{vid}/hide", json={"reason": "x"})
    ).status_code == 403
    assert (await alice.get("/api/v1/admin/users")).status_code == 403


async def test_moderator_cannot_administer_users(users: Users) -> None:
    moderator, alice = await users.new(Role.MODERATOR), await users.new()
    assert (await moderator.get("/api/v1/admin/users")).status_code == 403
    r = await moderator.patch(f"/api/v1/admin/users/{alice.me['id']}", json={"role": "admin"})  # type: ignore[attr-defined]
    assert r.status_code == 403


async def test_report_hide_restore_flow(users: Users) -> None:
    owner, reporter, viewer = await users.new(), await users.new(), await users.new()
    moderator = await users.new(Role.MODERATOR)
    vid = await make_ready_video(owner, title="Нарушающее правила видео")

    r = await reporter.post(
        "/api/v1/reports", json={"video_id": str(vid), "reason": "spam", "details": "реклама"}
    )
    assert r.status_code == 201
    # second open report from the same user on the same video is rejected (partial unique index)
    assert (
        await reporter.post("/api/v1/reports", json={"video_id": str(vid), "reason": "spam"})
    ).status_code == 409

    queue = (await moderator.get("/api/v1/moderation/reports")).json()["items"]
    mine = [i for i in queue if i["video"] and i["video"]["id"] == str(vid)]
    assert mine and mine[0]["reason"] == "spam" and mine[0]["reporter"] == reporter.me["username"]  # type: ignore[attr-defined]

    r = await moderator.post(
        f"/api/v1/moderation/videos/{vid}/hide", json={"reason": "Спам", "report_id": mine[0]["id"]}
    )
    assert r.status_code == 200

    # Hidden: gone for viewers (API, stream, feed, search), still visible to owner and staff.
    assert (await viewer.get(f"/api/v1/videos/{vid}")).status_code == 404
    assert (await viewer.get(f"/api/v1/videos/{vid}/stream", follow_redirects=False)).status_code == 404
    feed = [v["id"] for v in (await viewer.get("/api/v1/videos?limit=60")).json()["items"]]
    assert str(vid) not in feed
    search = [
        v["id"] for v in (await viewer.get("/api/v1/search", params={"q": "Нарушающее"})).json()["items"]
    ]
    assert str(vid) not in search
    own = (await owner.get(f"/api/v1/videos/{vid}")).json()
    assert own["moderation_state"] == "hidden"
    assert (await moderator.get(f"/api/v1/videos/{vid}")).status_code == 200

    # The report is resolved and the queue is clean.
    open_ids = [i["id"] for i in (await moderator.get("/api/v1/moderation/reports")).json()["items"]]
    assert mine[0]["id"] not in open_ids
    hidden = [v["id"] for v in (await moderator.get("/api/v1/moderation/videos/hidden")).json()["items"]]
    assert str(vid) in hidden

    # Restore brings it back.
    assert (
        await moderator.post(f"/api/v1/moderation/videos/{vid}/restore", json={"reason": "ошибка"})
    ).status_code == 200
    assert (await viewer.get(f"/api/v1/videos/{vid}")).status_code == 200

    # Everything is logged: moderation log + audit log.
    log = (await moderator.get("/api/v1/moderation/actions")).json()["items"]
    actions = [(a["action"], a["video_id"]) for a in log]
    assert ("hide_video", str(vid)) in actions and ("restore_video", str(vid)) in actions
    async with SessionLocal() as session:
        audit_actions = set((await session.scalars(select(AuditLog.action))).all())
    assert {"moderation.hide_video", "moderation.restore_video"} <= audit_actions


async def test_dismiss_report_and_comment_moderation(users: Users) -> None:
    owner, author, reporter = await users.new(), await users.new(), await users.new()
    moderator = await users.new(Role.MODERATOR)
    vid = await make_ready_video(owner)
    comment = (await author.post(f"/api/v1/videos/{vid}/comments", json={"body": "оскорбление"})).json()

    rep = (
        await reporter.post("/api/v1/reports", json={"comment_id": comment["id"], "reason": "hate"})
    ).json()
    queue = (await moderator.get("/api/v1/moderation/reports")).json()["items"]
    item = next(i for i in queue if i["id"] == rep["id"])
    assert item["comment"]["body"] == "оскорбление" and item["comment"]["author"] == author.me["username"]  # type: ignore[attr-defined]

    r = await moderator.post(f"/api/v1/moderation/comments/{comment['id']}/delete", json={"reason": "hate"})
    assert r.status_code == 200
    bodies = [c["body"] for c in (await owner.get(f"/api/v1/videos/{vid}/comments")).json()["items"]]
    assert "оскорбление" not in bodies

    # A report without violation is dismissed.
    rep2 = (await reporter.post("/api/v1/reports", json={"video_id": str(vid), "reason": "other"})).json()
    assert (
        await moderator.post(f"/api/v1/moderation/reports/{rep2['id']}/dismiss", json={})
    ).status_code == 200
    assert (
        await moderator.post(f"/api/v1/moderation/reports/{rep2['id']}/dismiss", json={})
    ).status_code == 409
    assert (await owner.get(f"/api/v1/videos/{vid}")).json()["moderation_state"] == "active"


async def test_report_validation(users: Users) -> None:
    alice, owner = await users.new(), await users.new()
    vid = await make_ready_video(owner)
    both = {"video_id": str(vid), "comment_id": str(vid), "reason": "spam"}
    assert (await alice.post("/api/v1/reports", json=both)).status_code == 422
    assert (await alice.post("/api/v1/reports", json={"reason": "spam"})).status_code == 422


async def test_admin_changes_roles_and_bans(users: Users) -> None:
    admin, alice = await users.new(Role.ADMIN), await users.new()
    alice_id = alice.me["id"]  # type: ignore[attr-defined]

    r = await admin.patch(f"/api/v1/admin/users/{alice_id}", json={"role": "moderator"})
    assert r.status_code == 200 and r.json()["role"] == "moderator"
    assert (await alice.get("/api/v1/moderation/reports")).status_code == 200  # new role applies immediately

    r = await admin.patch(f"/api/v1/admin/users/{alice_id}", json={"is_active": False, "reason": "abuse"})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert (await alice.get("/api/v1/auth/me")).status_code == 401  # ban logs out everywhere
    assert (await alice.post("/api/v1/auth/refresh")).status_code == 401

    # Admin can't demote or ban themselves (no lock-out by accident).
    assert (
        await admin.patch(f"/api/v1/admin/users/{admin.me['id']}", json={"role": "user"})
    ).status_code == 400  # type: ignore[attr-defined]

    users_page = (await admin.get("/api/v1/admin/users", params={"q": alice.me["username"]})).json()  # type: ignore[attr-defined]
    assert users_page["items"][0]["id"] == alice_id
    async with SessionLocal() as session:
        logged = (await session.scalars(select(ModerationAction.action))).all()
    assert {"change_role", "ban_user"} <= {a.value for a in logged}
