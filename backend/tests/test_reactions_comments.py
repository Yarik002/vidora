import asyncio

import httpx

from app.models import Role
from tests.conftest import Users, make_ready_video, video_from_db


async def test_like_dislike_switch_and_remove(users: Users) -> None:
    owner, alice = await users.new(), await users.new()
    vid = await make_ready_video(owner)

    r = await alice.put(f"/api/v1/videos/{vid}/reaction", json={"value": 1})
    assert r.json() == {"likes_count": 1, "dislikes_count": 0, "my_reaction": 1}
    r = await alice.put(f"/api/v1/videos/{vid}/reaction", json={"value": 1})  # idempotent
    assert r.json()["likes_count"] == 1
    r = await alice.put(f"/api/v1/videos/{vid}/reaction", json={"value": -1})  # switch
    assert r.json() == {"likes_count": 0, "dislikes_count": 1, "my_reaction": -1}
    r = await alice.put(f"/api/v1/videos/{vid}/reaction", json={"value": 0})  # remove
    assert r.json() == {"likes_count": 0, "dislikes_count": 0, "my_reaction": 0}

    assert (await alice.put(f"/api/v1/videos/{vid}/reaction", json={"value": 5})).status_code == 422


async def test_parallel_likes_keep_counter_consistent(users: Users) -> None:
    owner = await users.new()
    vid = await make_ready_video(owner)
    likers = [await users.new() for _ in range(5)]
    # The same user double-clicks, many users click at once.
    await asyncio.gather(
        *[c.put(f"/api/v1/videos/{vid}/reaction", json={"value": 1}) for c in likers for _ in range(2)]
    )
    video = await video_from_db(vid)
    assert video.likes_count == 5


async def test_anonymous_cannot_react_or_comment(users: Users, client: httpx.AsyncClient) -> None:
    owner = await users.new()
    vid = await make_ready_video(owner)
    assert (await client.put(f"/api/v1/videos/{vid}/reaction", json={"value": 1})).status_code == 401
    assert (await client.post(f"/api/v1/videos/{vid}/comments", json={"body": "x"})).status_code == 401
    assert (await client.get(f"/api/v1/videos/{vid}/comments")).status_code == 200  # reading is public


async def test_comments_replies_and_counters(users: Users) -> None:
    owner, alice, bob = await users.new(), await users.new(), await users.new()
    vid = await make_ready_video(owner)

    top = (await alice.post(f"/api/v1/videos/{vid}/comments", json={"body": "  Отличное видео!  "})).json()
    assert top["body"] == "Отличное видео!" and top["can_edit"] and top["can_delete"]
    reply = (
        await bob.post(f"/api/v1/videos/{vid}/comments", json={"body": "Согласен", "parent_id": top["id"]})
    ).json()
    # A reply to a reply lands in the same thread (one nesting level, like YouTube).
    nested = (
        await owner.post(f"/api/v1/videos/{vid}/comments", json={"body": "Спасибо", "parent_id": reply["id"]})
    ).json()
    assert nested["parent_id"] == top["id"] and nested["is_video_owner"]

    listing = (await bob.get(f"/api/v1/videos/{vid}/comments")).json()["items"]
    assert [c["id"] for c in listing] == [top["id"]]
    assert listing[0]["replies_count"] == 2 and not listing[0]["can_edit"]
    replies = (await bob.get(f"/api/v1/comments/{top['id']}/replies")).json()["items"]
    assert [r["body"] for r in replies] == ["Согласен", "Спасибо"]
    assert (await video_from_db(vid)).comments_count == 3

    assert (await alice.post(f"/api/v1/videos/{vid}/comments", json={"body": "   "})).status_code == 422


async def test_comment_edit_and_delete_permissions(users: Users) -> None:
    owner, alice, mallory = await users.new(), await users.new(), await users.new()
    moderator = await users.new(Role.MODERATOR)
    vid = await make_ready_video(owner)
    c1 = (await alice.post(f"/api/v1/videos/{vid}/comments", json={"body": "first"})).json()
    c2 = (await alice.post(f"/api/v1/videos/{vid}/comments", json={"body": "second"})).json()
    c3 = (await alice.post(f"/api/v1/videos/{vid}/comments", json={"body": "third"})).json()

    # Someone else can neither edit nor delete.
    assert (await mallory.patch(f"/api/v1/comments/{c1['id']}", json={"body": "hacked"})).status_code == 404
    assert (await mallory.delete(f"/api/v1/comments/{c1['id']}")).status_code == 404
    # Video owner may not edit, but may delete comments under own video; moderator too.
    assert (await owner.patch(f"/api/v1/comments/{c1['id']}", json={"body": "x"})).status_code == 404
    assert (await owner.delete(f"/api/v1/comments/{c1['id']}")).status_code == 200
    assert (await moderator.delete(f"/api/v1/comments/{c2['id']}")).status_code == 200
    # Author edits own comment.
    r = await alice.patch(f"/api/v1/comments/{c3['id']}", json={"body": "third, edited"})
    assert r.status_code == 200 and r.json()["body"] == "third, edited"
    assert (await video_from_db(vid)).comments_count == 1


async def test_deleting_comment_with_replies_keeps_thread(users: Users) -> None:
    owner, alice, bob = await users.new(), await users.new(), await users.new()
    vid = await make_ready_video(owner)
    top = (await alice.post(f"/api/v1/videos/{vid}/comments", json={"body": "top"})).json()
    await bob.post(f"/api/v1/videos/{vid}/comments", json={"body": "reply", "parent_id": top["id"]})
    assert (await alice.delete(f"/api/v1/comments/{top['id']}")).status_code == 200
    items = (await bob.get(f"/api/v1/videos/{vid}/comments")).json()["items"]
    assert items[0]["is_deleted"] and items[0]["body"] is None and items[0]["author"] is None
    assert items[0]["replies_count"] == 1


async def test_comment_likes(users: Users) -> None:
    owner, alice = await users.new(), await users.new()
    vid = await make_ready_video(owner)
    c = (await owner.post(f"/api/v1/videos/{vid}/comments", json={"body": "pinned-ish"})).json()
    r = await alice.put(f"/api/v1/comments/{c['id']}/reaction", json={"value": 1})
    assert r.json() == {"likes_count": 1, "my_reaction": 1}
    items = (await alice.get(f"/api/v1/videos/{vid}/comments")).json()["items"]
    assert items[0]["my_reaction"] == 1
    r = await alice.put(f"/api/v1/comments/{c['id']}/reaction", json={"value": 0})
    assert r.json()["likes_count"] == 0


async def test_views_are_deduplicated(users: Users, client: httpx.AsyncClient) -> None:
    owner, alice = await users.new(), await users.new()
    vid = await make_ready_video(owner)
    assert (await alice.post(f"/api/v1/videos/{vid}/view")).json()["views_count"] == 1
    assert (await alice.post(f"/api/v1/videos/{vid}/view")).json()["views_count"] == 1  # same viewer
    assert (await client.post(f"/api/v1/videos/{vid}/view")).json()["views_count"] == 2  # anonymous viewer


async def test_only_owner_can_edit_or_delete_video(users: Users) -> None:
    """IDOR: knowing a video id is not enough to modify it."""
    owner, mallory = await users.new(), await users.new()
    moderator, admin = await users.new(Role.MODERATOR), await users.new(Role.ADMIN)
    vid = await make_ready_video(owner)
    assert (await mallory.patch(f"/api/v1/videos/{vid}", json={"title": "pwned"})).status_code == 404
    assert (await mallory.delete(f"/api/v1/videos/{vid}")).status_code == 404
    assert (await moderator.patch(f"/api/v1/videos/{vid}", json={"title": "x"})).status_code == 403
    r = await owner.patch(
        f"/api/v1/videos/{vid}", json={"title": "New title", "tags": ["#Music", "music", "live"]}
    )
    assert r.status_code == 200 and r.json()["title"] == "New title"
    assert set(r.json()["tags"]) == {"live", "Music"}  # "#Music" and "music" collapse into one tag
    assert (await admin.delete(f"/api/v1/videos/{vid}")).status_code == 200
    assert (await owner.get(f"/api/v1/videos/{vid}")).status_code == 404
