#!/usr/bin/env python3
"""End-to-end check of a deployed Vidora, through Caddy, exactly like a browser does:

    register -> upload (multipart, presigned URLs) -> processing -> watch (302 + Range) -> like -> comment
    + private video is not reachable anonymously.

Standard library only: runs on a clean Ubuntu with python3.

    python3 scripts/e2e.py                       # https://localhost, self-signed certificate allowed
    python3 scripts/e2e.py --base https://my.domain --strict-tls
    python3 scripts/e2e.py --video my.mp4        # otherwise a clip is generated with ffmpeg in the worker container
"""

import argparse
import http.cookiejar
import json
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


class Client:
    def __init__(self, base: str, strict_tls: bool) -> None:
        self.base = base.rstrip("/")
        ctx = ssl.create_default_context()
        if not strict_tls:  # self-signed internal CA of a fresh deployment
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self.jar = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPSHandler(context=ctx), urllib.request.HTTPCookieProcessor(self.jar)]
        self.opener = urllib.request.build_opener(*handlers)
        self.raw = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), NoRedirect())

    def csrf(self) -> str:
        return next((c.value for c in self.jar if c.name == "vid_csrf"), "")

    def request(self, method: str, path: str, body: object | None = None, expect: int | tuple = 200,
                headers: dict | None = None, raw_body: bytes | None = None, no_redirect: bool = False):
        url = path if path.startswith("http") else self.base + path
        data = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(url, data=data, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if method not in ("GET", "HEAD"):
            req.add_header("X-CSRF-Token", self.csrf())
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        opener = self.raw if no_redirect else self.opener
        if no_redirect:  # still send cookies
            self.jar.add_cookie_header(req)
        try:
            resp = opener.open(req, timeout=60)
            status, payload, resp_headers = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            status, payload, resp_headers = e.code, e.read(), e.headers
        expected = expect if isinstance(expect, tuple) else (expect,)
        if status not in expected:
            raise AssertionError(f"{method} {path}: expected {expected}, got {status}: {payload[:300]!r}")
        return status, payload, resp_headers

    def json(self, method: str, path: str, body: object | None = None, expect: int | tuple = 200):
        _, payload, _ = self.request(method, path, body, expect)
        return json.loads(payload) if payload else None


def step(n: int, text: str) -> None:
    print(f"[{n}] {text}", flush=True)


def generate_clip() -> bytes:
    """6-second 640x360 test pattern with a tone, generated inside the worker container (has ffmpeg)."""
    cmd = [
        "docker", "compose", "exec", "-T", "worker", "ffmpeg", "-nostdin", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=330:duration=6",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest",
        "-movflags", "frag_keyframe+empty_moov", "-f", "mp4", "pipe:1",
    ]
    out = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True).stdout
    if len(out) < 10_000:
        raise RuntimeError("ffmpeg produced an empty clip")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="https://localhost")
    ap.add_argument("--strict-tls", action="store_true", help="verify the TLS certificate")
    ap.add_argument("--video", type=Path, help="video file to upload (default: generated)")
    ap.add_argument("--timeout", type=int, default=300, help="seconds to wait for processing")
    args = ap.parse_args()

    t0 = time.monotonic()
    c = Client(args.base, args.strict_tls)

    step(1, "health")
    assert c.json("GET", "/api/v1/health/ready")["status"] == "ready"

    step(2, "register a new user")
    name = f"e2e{uuid.uuid4().hex[:8]}"
    me = c.json("POST", "/api/v1/auth/register",
                {"email": f"{name}@example.com", "username": name, "password": f"E2e-{uuid.uuid4().hex[:10]}"}, 201)
    assert c.json("GET", "/api/v1/auth/me")["id"] == me["id"]

    step(3, "upload a video (multipart, straight to storage)")
    data = args.video.read_bytes() if args.video else generate_clip()
    up = c.json("POST", "/api/v1/uploads", {"filename": "e2e.mp4", "size_bytes": len(data), "content_type": "video/mp4",
                                           "title": "E2E: сквозной сценарий", "tags": ["e2e"]}, 201)
    parts = []
    for part in up["parts"]:
        n = part["part_number"]
        chunk = data[(n - 1) * up["part_size"]: n * up["part_size"]]
        _, _, h = c.request("PUT", part["url"], raw_body=chunk)
        parts.append({"part_number": n, "etag": h["ETag"]})
    done = c.json("POST", f"/api/v1/uploads/{up['upload_id']}/complete", {"parts": parts})
    assert done["status"] == "uploaded", done
    vid = up["video_id"]
    print(f"    uploaded {len(data)} bytes in {len(parts)} part(s), video {vid}")

    step(4, "wait for background processing (ffmpeg in the worker)")
    t_proc = time.monotonic()
    while True:
        st = c.json("GET", f"/api/v1/videos/{vid}/status")
        if st["status"] in ("ready", "failed"):
            break
        if time.monotonic() - t_proc > args.timeout:
            raise AssertionError(f"processing did not finish in {args.timeout}s, status={st['status']}")
        time.sleep(2)
    assert st["status"] == "ready", st
    print(f"    ready in {time.monotonic() - t_proc:.1f}s, duration {st['duration_seconds']}s")

    c.json("PATCH", f"/api/v1/videos/{vid}", {"description": "Проверка развертывания"})

    step(5, "watch: 302 to a signed URL, Range request returns 206")
    detail = c.json("GET", f"/api/v1/videos/{vid}")
    assert detail["qualities"], detail
    status, _, h = c.request("GET", f"/api/v1/videos/{vid}/stream", expect=302, no_redirect=True)
    location = h["Location"]
    assert location.startswith("/storage/"), location
    status, body, h = c.request("GET", location, headers={"Range": "bytes=0-1023"}, expect=206)
    assert len(body) == 1024 and h["Content-Type"] == "video/mp4"
    c.json("POST", f"/api/v1/videos/{vid}/view")

    step(6, "like")
    r = c.json("PUT", f"/api/v1/videos/{vid}/reaction", {"value": 1})
    assert r["likes_count"] == 1 and r["my_reaction"] == 1

    step(7, "comment")
    com = c.json("POST", f"/api/v1/videos/{vid}/comments", {"body": "Работает!"}, 201)
    items = c.json("GET", f"/api/v1/videos/{vid}/comments")["items"]
    assert any(i["id"] == com["id"] for i in items)

    step(8, "the video is in the public feed; a private one is not reachable anonymously")
    anon = Client(args.base, args.strict_tls)
    feed = anon.json("GET", "/api/v1/videos?limit=60")["items"]
    assert any(v["id"] == vid for v in feed)
    c.json("PATCH", f"/api/v1/videos/{vid}", {"visibility": "private"})
    anon.request("GET", f"/api/v1/videos/{vid}", expect=404)
    anon.request("GET", f"/api/v1/videos/{vid}/stream", expect=404, no_redirect=True)
    c.json("PATCH", f"/api/v1/videos/{vid}", {"visibility": "public"})

    print(f"OK: full scenario passed in {time.monotonic() - t0:.1f}s ({args.base}/watch/{vid})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, urllib.error.URLError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"E2E FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
