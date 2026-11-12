"""Private videos are visible only to the owner, staff and users the owner granted access to:
not through the API, not through the stream redirect, not in listings, not via comments."""

import httpx

from app.models import Role, Visibility
from tests.conftest import Users, make_ready_video


async def _assert_hidden(c: httpx.AsyncClient, video_id) -> None:
    assert (await c.get(f"/api/v1/videos/{video_id}")).status_code == 404
    assert (await c.get(f"/api/v1/videos/{video_id}/stream", follow_redirects=False)).status_code == 404
    assert (await c.get(f"/api/v1/videos/{video_id}/comments")).status_code == 404
    assert (await c.get(f"/api/v1/videos/{video_id}/related")).status_code == 404


async def _assert_visible(c: httpx.AsyncClient, video_id) -> None:
    assert (await c.get(f"/api/v1/videos/{video_id}")).status_code == 200
    r = await c.get(f"/api/v1/videos/{video_id}/stream", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/storage/")


async def test_private_video_is_hidden_from_strangers_and_anonymous(
    users: Users, client: httpx.AsyncClient
) -> None:
    owner, stranger = await users.new(), await users.new()
    vid = await make_ready_video(owner, Visibility.PRIVATE, title="Секретное приватное видео")

    await _assert_hidden(client, vid)
    await _assert_hidden(stranger, vid)
    await _assert_visible(owner, vid)

    # Strangers can't react or comment either.
    assert (await stranger.put(f"/api/v1/videos/{vid}/reaction", json={"value": 1})).status_code == 404
    assert (await stranger.post(f"/api/v1/videos/{vid}/comments", json={"body": "hi"})).status_code == 404

    # Not in feed, not in channel listing for others.
    feed_ids = [v["id"] for v in (await stranger.get("/api/v1/videos?limit=60")).json()["items"]]
    assert str(vid) not in feed_ids


async def test_grant_and_revoke_access(users: Users) -> None:
    owner, friend, stranger = await users.new(), await users.new(), await users.new()
    vid = await make_ready_video(owner, Visibility.PRIVATE)

    r = await owner.post(f"/api/v1/videos/{vid}/access", json={"username": friend.me["username"]})  # type: ignore[attr-defined]
    assert r.status_code == 201
    await _assert_visible(friend, vid)
    await _assert_hidden(stranger, vid)

    grants = (await owner.get(f"/api/v1/videos/{vid}/access")).json()
    assert [g["username"] for g in grants] == [friend.me["username"]]  # type: ignore[attr-defined]

    friend_id = friend.me["id"]  # type: ignore[attr-defined]
    assert (await owner.delete(f"/api/v1/videos/{vid}/access/{friend_id}")).status_code == 204
    await _assert_hidden(friend, vid)


async def test_only_owner_manages_access(users: Users) -> None:
    owner, friend, mallory = await users.new(), await users.new(), await users.new()
    vid = await make_ready_video(owner, Visibility.PRIVATE)
    r = await mallory.post(f"/api/v1/videos/{vid}/access", json={"username": mallory.me["username"]})  # type: ignore[attr-defined]
    assert r.status_code == 404
    assert (await mallory.get(f"/api/v1/videos/{vid}/access")).status_code == 404
    await _assert_hidden(mallory, vid)
    del friend


async def test_unlisted_video_is_reachable_by_link_but_not_listed(
    users: Users, client: httpx.AsyncClient
) -> None:
    owner = await users.new()
    vid = await make_ready_video(owner, Visibility.UNLISTED, title="Unlisted by link")
    await _assert_visible(client, vid)
    feed_ids = [v["id"] for v in (await client.get("/api/v1/videos?limit=60")).json()["items"]]
    assert str(vid) not in feed_ids


async def test_staff_can_see_private_videos(users: Users) -> None:
    owner, moderator = await users.new(), await users.new(Role.MODERATOR)
    vid = await make_ready_video(owner, Visibility.PRIVATE)
    await _assert_visible(moderator, vid)


async def test_switching_to_private_hides_immediately(users: Users, client: httpx.AsyncClient) -> None:
    owner = await users.new()
    vid = await make_ready_video(owner, Visibility.PUBLIC)
    await _assert_visible(client, vid)
    r = await owner.patch(f"/api/v1/videos/{vid}", json={"visibility": "private"})
    assert r.status_code == 200 and r.json()["visibility"] == "private"
    await _assert_hidden(client, vid)
