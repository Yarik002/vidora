#!/usr/bin/env python3
"""README screenshots + a browser-level smoke test of the main screens (Playwright, Chromium).

    pip install playwright            # in any venv
    python scripts/screenshots.py --base http://localhost:8080 [--chrome PATH_TO_chrome.exe]

Needs a running stack with demo data (`./deploy.sh --demo`, or compose.dev.yml locally).
Logs in as demo users with DEMO_PASSWORD read from .env (never printed). The upload screen is
driven through the real file input, so this also checks upload -> processing in a real browser.
Fails (exit 1) if a page shows an error or an expected element does not appear.
"""

import argparse
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"


def env_value(key: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    raise SystemExit(f"{key} not found in .env")


def login(ctx: BrowserContext, base: str, username: str, password: str) -> None:
    ctx.clear_cookies()
    ctx.request.get(f"{base}/api/v1/health")  # sets the CSRF cookie
    csrf = next(c["value"] for c in ctx.cookies() if c["name"] == "vid_csrf")
    r = ctx.request.post(
        f"{base}/api/v1/auth/login",
        data={"login": username, "password": password},
        headers={"X-CSRF-Token": csrf},
    )
    if not r.ok:
        raise SystemExit(f"login as {username} failed: HTTP {r.status}")


def shot(page: Page, name: str) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(600)  # let lazy thumbnails paint
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  {path.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--chrome", help="use an already installed chrome.exe instead of Playwright's")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    password = env_value("DEMO_PASSWORD")
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chrome) if args.chrome else p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, ignore_https_errors=True, locale="ru-RU")
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        print("home (alice)")
        login(ctx, base, "alice", password)
        page.goto(f"{base}/")
        page.locator(".vcard").first.wait_for()
        shot(page, "home")

        print("watch")
        found = ctx.request.get(f"{base}/api/v1/search?q=ноутбук").json()["items"]
        page.goto(f"{base}/watch/{found[0]['id']}")
        page.locator(".watch__title").wait_for()
        page.locator(".comment").first.wait_for()
        page.locator("video").evaluate("v => { v.pause(); v.currentTime = 3; }")
        shot(page, "watch")

        print("channel")
        page.goto(f"{base}/channel/bob")
        page.locator(".channel__info h1").wait_for()
        page.locator(".vcard").first.wait_for()
        shot(page, "channel")

        print("search with a typo")
        page.goto(f"{base}/results?search_query=" + "борш")
        page.locator(".vcard--list").first.wait_for()
        shot(page, "search")

        print("upload through the real file input (bob)")
        login(ctx, base, "bob", password)
        clip = ctx.request.get(f"{base}/api/v1/videos/{found[0]['id']}/stream?quality=360p")
        if not clip.ok:
            raise SystemExit(f"could not fetch a sample clip: HTTP {clip.status}")
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "Мой новый ролик.mp4"
            sample.write_bytes(clip.body())
            page.goto(f"{base}/upload")
            page.locator("input[type=file]").set_input_files(str(sample))
            page.locator(".upload__form").wait_for()
            page.get_by_label("Описание").fill("Загружено из браузера скриптом scripts/screenshots.py")
            page.locator(".upload__ok").wait_for(timeout=180_000)  # "Обработка завершена"
        shot(page, "upload")

        print("moderation (moderator)")
        login(ctx, base, "moderator", password)
        page.goto(f"{base}/moderation")
        page.locator(".report").first.wait_for()
        shot(page, "moderation")

        print("light theme")
        page.evaluate("localStorage.setItem('vidora-theme', 'light')")
        login(ctx, base, "alice", password)
        page.goto(f"{base}/")
        page.locator(".vcard").first.wait_for()
        shot(page, "home-light")
        page.evaluate("localStorage.removeItem('vidora-theme')")

        browser.close()
        if errors:
            print("JS errors on pages:\n  " + "\n  ".join(errors), file=sys.stderr)
            return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
