import httpx

from app.models import Visibility
from tests.conftest import Users, make_ready_video


async def test_channel_page_and_subscriptions(users: Users, client: httpx.AsyncClient) -> None:
    author, fan = await users.new(), await users.new()
    handle = author.me["channel"]["handle"]  # type: ignore[attr-defined]
    channel_id = author.me["channel"]["id"]  # type: ignore[attr-defined]
    public = await make_ready_video(author, title="Публичное")
    private = await make_ready_video(author, Visibility.PRIVATE, title="Приватное")

    ch = (await client.get(f"/api/v1/channels/{handle}")).json()
    assert ch["videos_count"] == 1 and not ch["is_subscribed"]
    ids = [v["id"] for v in (await client.get(f"/api/v1/channels/{handle}/videos")).json()["items"]]
    assert ids == [str(public)] and str(private) not in ids

    # Subscribe is idempotent: double click doesn't double the counter.
    for _ in range(2):
        r = await fan.put(f"/api/v1/channels/{channel_id}/subscription")
        assert r.json() == {"subscribed": True, "subscribers_count": 1}
    assert (await fan.get(f"/api/v1/channels/{handle}")).json()["is_subscribed"]
    subs = (await fan.get("/api/v1/me/subscriptions")).json()
    assert [s["handle"] for s in subs] == [handle]
    feed = [v["id"] for v in (await fan.get("/api/v1/me/feed/subscriptions")).json()["items"]]
    assert feed == [str(public)]

    assert (await author.put(f"/api/v1/channels/{channel_id}/subscription")).status_code == 400  # own channel
    r = await fan.delete(f"/api/v1/channels/{channel_id}/subscription")
    assert r.json() == {"subscribed": False, "subscribers_count": 0}
    assert (await fan.delete(f"/api/v1/channels/{channel_id}/subscription")).json()["subscribers_count"] == 0

    r = await author.patch("/api/v1/channels/me", json={"title": "Новый канал", "description": "О канале"})
    assert r.status_code == 200 and r.json()["title"] == "Новый канал"
    assert (await client.get("/api/v1/channels/no-such-channel")).status_code == 404


async def test_playlists_respect_video_access(users: Users) -> None:
    owner, friend, stranger = await users.new(), await users.new(), await users.new()
    v1 = await make_ready_video(owner, title="один")
    secret = await make_ready_video(owner, Visibility.PRIVATE, title="секрет")
    await owner.post(f"/api/v1/videos/{secret}/access", json={"username": friend.me["username"]})  # type: ignore[attr-defined]

    pl = (await owner.post("/api/v1/playlists", json={"title": "Мой плейлист"})).json()
    for vid in (v1, secret):
        assert (
            await owner.post(f"/api/v1/playlists/{pl['id']}/videos", json={"video_id": str(vid)})
        ).status_code == 204
    # adding twice does not duplicate
    await owner.post(f"/api/v1/playlists/{pl['id']}/videos", json={"video_id": str(v1)})

    assert len((await owner.get(f"/api/v1/playlists/{pl['id']}")).json()["videos"]) == 2
    assert len((await friend.get(f"/api/v1/playlists/{pl['id']}")).json()["videos"]) == 2
    stranger_view = (await stranger.get(f"/api/v1/playlists/{pl['id']}")).json()
    assert [v["title"] for v in stranger_view["videos"]] == ["один"]  # private video is filtered out
    assert stranger_view["items_count"] == 2 and not stranger_view["is_owner"]

    # A stranger can't save a private video into own playlist, nor edit someone else's playlist.
    own = (await stranger.post("/api/v1/playlists", json={"title": "чужое"})).json()
    r = await stranger.post(f"/api/v1/playlists/{own['id']}/videos", json={"video_id": str(secret)})
    assert r.status_code == 404
    assert (
        await stranger.post(f"/api/v1/playlists/{pl['id']}/videos", json={"video_id": str(v1)})
    ).status_code == 404
    assert (await stranger.delete(f"/api/v1/playlists/{pl['id']}")).status_code == 404

    mine = (await owner.get("/api/v1/me/playlists", params={"video_id": str(v1)})).json()
    assert mine[0]["contains_video"] is True

    # Private playlist is invisible to others.
    await owner.patch(f"/api/v1/playlists/{pl['id']}", json={"visibility": "private"})
    assert (await stranger.get(f"/api/v1/playlists/{pl['id']}")).status_code == 404
    assert (await owner.delete(f"/api/v1/playlists/{pl['id']}/videos/{v1}")).status_code == 204
    assert (await owner.get(f"/api/v1/playlists/{pl['id']}")).json()["items_count"] == 1


async def test_search_fulltext_typos_and_access(users: Users, client: httpx.AsyncClient) -> None:
    owner = await users.new()
    cats = await make_ready_video(owner, title="Смешные кошки играют с мячом")
    await make_ready_video(owner, title="Обзор горного велосипеда")
    hidden = await make_ready_video(owner, Visibility.PRIVATE, title="Кошки секретные")

    async def ids(q: str) -> list[str]:
        r = await client.get("/api/v1/search", params={"q": q})
        assert r.status_code == 200
        return [v["id"] for v in r.json()["items"]]

    assert str(cats) in await ids("кошка")  # russian stemming: кошка ~ кошки
    assert str(cats) in await ids("смешные кошки")
    assert str(cats) in await ids("кошьки")  # typo, found by trigram similarity
    assert str(hidden) not in await ids("кошки")  # private never appears in search
    assert await ids("квантовая хромодинамика") == []
    assert (await client.get("/api/v1/search", params={"q": ""})).status_code == 422
    # SQL/LIKE special characters are just text
    assert (await client.get("/api/v1/search", params={"q": "%' OR 1=1 --"})).status_code == 200


async def test_history_and_liked_pages(users: Users) -> None:
    owner, alice = await users.new(), await users.new()
    v1, v2 = await make_ready_video(owner, title="первое"), await make_ready_video(owner, title="второе")
    await alice.post(f"/api/v1/videos/{v1}/view")
    await alice.post(f"/api/v1/videos/{v2}/view")
    await alice.put(f"/api/v1/videos/{v1}/reaction", json={"value": 1})
    history = [v["id"] for v in (await alice.get("/api/v1/me/history")).json()["items"]]
    assert history == [str(v2), str(v1)]
    liked = [v["id"] for v in (await alice.get("/api/v1/me/liked")).json()["items"]]
    assert liked == [str(v1)]
    # If the owner makes a video private, it disappears from other people's history as well.
    await owner.patch(f"/api/v1/videos/{v2}", json={"visibility": "private"})
    history = [v["id"] for v in (await alice.get("/api/v1/me/history")).json()["items"]]
    assert history == [str(v1)]
    assert (await alice.delete("/api/v1/me/history")).status_code == 204
    assert (await alice.get("/api/v1/me/history")).json()["items"] == []

    studio = (await owner.get("/api/v1/me/videos")).json()["items"]
    assert {v["id"] for v in studio} == {str(v1), str(v2)}


async def test_deleting_video_keeps_playlist_counter_right(users: Users) -> None:
    """Regression (code review): cascade removed playlist items but not the counter."""
    owner = await users.new()
    v1, v2 = await make_ready_video(owner), await make_ready_video(owner)
    pl = (await owner.post("/api/v1/playlists", json={"title": "p"})).json()
    for vid in (v1, v2):
        await owner.post(f"/api/v1/playlists/{pl['id']}/videos", json={"video_id": str(vid)})
    assert (await owner.delete(f"/api/v1/videos/{v1}")).status_code == 200
    detail = (await owner.get(f"/api/v1/playlists/{pl['id']}")).json()
    assert detail["items_count"] == 1 and len(detail["videos"]) == 1


async def test_whitespace_search_is_rejected(client: httpx.AsyncClient) -> None:
    """Regression (code review): '   ' turned into ILIKE '%%' and returned everything."""
    assert (await client.get("/api/v1/search", params={"q": "   "})).status_code == 422
