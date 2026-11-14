"""Real-browser smoke test against a RUNNING CivicEye server.

Uses Playwright with the locally installed Microsoft Edge (no browser download).

    .\\.venv\\Scripts\\pip install playwright
    $env:CIVICEYE_REVIEWER_EMAIL="..."; $env:CIVICEYE_REVIEWER_PASSWORD="..."
    .\\.venv\\Scripts\\python scripts\\browser_smoke.py [--base http://127.0.0.1:5000] [--headed]

It registers a throwaway citizen, submits complaints through the real form, and
checks map tiles, JS errors, the image preview, geolocation, the reviewer pages and
charts, and private-access isolation. Screenshots go to instance/browser_smoke/.
"""
from __future__ import annotations

import argparse
import io
import os
import secrets
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "instance" / "browser_smoke"
results: list[tuple[bool, str]] = []


def check(ok: bool, msg: str) -> None:
    results.append((bool(ok), msg))
    print(("PASS " if ok else "FAIL ") + msg)


def make_jpeg(path: Path, size=(1600, 1200)) -> Path:
    img = Image.new("RGB", size, (110, 110, 110))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    path.write_bytes(buf.getvalue())
    return path


class TileWatch:
    """Records OpenStreetMap tile requests: referer and whether OSM served its 'blocked' tile."""

    def __init__(self, page):
        self.items = []
        page.on("response", self._on)

    def _on(self, resp):
        if "tile.openstreetmap.org" not in resp.url:
            return
        try:
            ref = resp.request.all_headers().get("referer")
            cc = resp.all_headers().get("cache-control", "")
        except Exception:  # noqa: BLE001
            ref, cc = None, ""
        # OSM serves real tiles with max-age and the blocked tile with no-cache.
        self.items.append({"url": resp.url, "status": resp.status, "referer": ref,
                           "blocked": resp.status != 200 or "no-cache" in cc, "from_cache": resp.from_service_worker})

    def reset(self):
        self.items.clear()

    def summary(self):
        n = len(self.items)
        blocked = sum(1 for t in self.items if t["blocked"])
        missing_ref = sum(1 for t in self.items if not t["referer"])
        return n, blocked, missing_ref


def wait_tiles(page, timeout=8000):
    try:
        page.wait_for_function(
            "() => document.querySelectorAll('.leaflet-tile-loaded').length >= 4", timeout=timeout)
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5000")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    rev_email = os.environ.get("CIVICEYE_REVIEWER_EMAIL")
    rev_pw = os.environ.get("CIVICEYE_REVIEWER_PASSWORD")
    OUT.mkdir(parents=True, exist_ok=True)
    img1 = make_jpeg(OUT / "upload_test.jpg")
    big = make_jpeg(OUT / "upload_large_side.jpg", size=(4000, 3000))

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=not args.headed)
        ctx = browser.new_context(geolocation={"latitude": 12.90815, "longitude": 77.56655},
                                  permissions=["geolocation"], locale="en-IN", timezone_id="Europe/London")
        page = ctx.new_page()
        js_errors = []
        page.on("pageerror", lambda e: js_errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: js_errors.append(f"console.{m.type}: {m.text}")
                if m.type == "error" and "Failed to load resource" not in m.text else None)
        tiles = TileWatch(page)
        expected_4xx = set()  # (path, status) pairs the script triggers on purpose
        bad_responses = []

        def _on_resp(resp):
            if resp.url.startswith(base) and resp.status >= 400:
                path = resp.url[len(base):]
                if (path.split("?")[0], resp.status) not in expected_4xx:
                    bad_responses.append(f"{resp.status} {resp.request.method} {path}")
        page.on("response", _on_resp)
        # Console 'Failed to load resource' lines duplicate bad_responses; keep only real JS errors.
        page.on("console", lambda m: None)

        # --- Public pages
        for path in ("/", "/guidance", "/privacy", "/login", "/register"):
            r = page.goto(base + path)
            check(r.status == 200, f"GET {path} -> {r.status}")

        # --- Register citizen
        email = f"browser.{secrets.token_hex(3)}@example.com"
        pw = "browser-pass-" + secrets.token_hex(3)
        page.goto(base + "/register")
        page.fill("#email", email)
        page.fill("#display_name", "Browser Tester")
        page.fill("#password", pw)
        page.fill("#password2", pw)
        page.check("#accept_terms")
        page.click("button[type=submit]")
        check(page.url.endswith("/me/"), f"registration lands on citizen dashboard ({page.url})")

        # --- Complaint form: map tiles
        tiles.reset()
        page.goto(base + "/me/complaints/new")
        wait_tiles(page)
        n, blocked, noref = tiles.summary()
        check(n > 0 and blocked == 0 and noref == 0,
              f"form map tiles: {n} requested, {blocked} blocked, {noref} without Referer")
        page.screenshot(path=str(OUT / "01_form.png"), full_page=True)

        # Observation time default must be IST even though this browser runs in Europe/London
        obs = page.input_value("#observed_at")
        ist_now = page.evaluate("""() => new Intl.DateTimeFormat('sv-SE', {timeZone: 'Asia/Kolkata',
            year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date()).replace(' ', 'T')""")
        check(obs[:13] == ist_now[:13], f"default observation time is IST ({obs} vs IST now {ist_now})")

        # Geolocation button
        page.click("#use-location")
        page.wait_for_function("() => document.getElementById('latitude').value !== ''", timeout=8000)
        check(abs(float(page.input_value("#latitude")) - 12.90815) < 1e-4, "Use my location fills coordinates")
        check(page.input_value("#location_source") == "geolocation", "location_source=geolocation")

        # Clicking the map moves the pin and switches source to manual
        box = page.locator("#map").bounding_box()
        page.mouse.click(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.3)
        page.wait_for_timeout(300)
        check(page.input_value("#location_source") == "manual", "clicking map sets manual location")

        # Image preview
        page.set_input_files("#image", str(img1))
        page.wait_for_timeout(300)
        check(page.locator("#image-preview").is_visible(), "image preview shown after choosing a file")

        # Keyword suggestion
        page.fill("#description", "Big pothole near the bus stop, two-wheelers swerving")
        page.wait_for_timeout(1200)
        sugg = page.inner_text("#text-suggestion")
        check("Pothole" in sugg, f"keyword suggestion shown ({sugg[:60]!r})")
        if page.locator("#text-suggestion button").count():
            page.click("#text-suggestion button")
        check(page.input_value("#category") == "pothole", "'Use this' selects the suggested category")
        page.wait_for_timeout(800)
        check("Set a location" not in page.inner_text("#nearby"), "nearby-report panel updated")

        # Submit WITHOUT consent -> server re-renders with errors. This is the reported case.
        expected_4xx.add(("/me/complaints/new", 400))
        tiles.reset()
        page.click("#complaint-form button[type=submit]")
        page.wait_for_load_state("load")
        wait_tiles(page)
        n, blocked, noref = tiles.summary()
        check("consent" in page.content() and "/me/complaints/new" in page.url, "missing consent re-renders the form")
        check(n > 0 and blocked == 0 and noref == 0,
              f"map tiles after failed upload: {n} requested, {blocked} blocked, {noref} without Referer")
        check(page.input_value("#latitude") != "", "coordinates kept after a failed submission")
        check(page.locator("#map .leaflet-marker-icon").count() == 1, "pin re-drawn after a failed submission")
        page.wait_for_timeout(1500)
        check("Set a location" not in page.inner_text("#nearby"), "nearby panel refreshed after a failed submission")
        check("Pothole" in page.inner_text("#text-suggestion"), "keyword suggestion restored after a failed submission")
        check("Choose your photo(s) again" in page.content(), "user is told to re-select photos")
        page.screenshot(path=str(OUT / "02_after_failed_submit.png"), full_page=True)

        # Oversized photo: blocked in the browser with a message, nothing sent to the server
        max_bytes = int(page.get_attribute("#complaint-form", "data-max-image-bytes"))
        huge = OUT / "too_big.jpg"
        huge.write_bytes(img1.read_bytes() + b"\0" * (max_bytes + 1024))
        page.set_input_files("#image", str(huge))
        page.check("#consent")
        url_before = page.url
        page.click("#complaint-form button[type=submit]")
        page.wait_for_timeout(500)
        msg = page.inner_text("#image-client-error") if page.locator("#image-client-error").count() else ""
        check(page.url == url_before and "limit" in msg, f"oversized photo blocked client-side ({msg!r})")
        page.uncheck("#consent")

        # Valid submission
        page.set_input_files("#image", str(img1))
        page.set_input_files("#extra_images", str(big))
        page.check("#consent")
        page.click("#complaint-form button[type=submit]")
        page.wait_for_load_state("load")
        check("/submitted" in page.url, f"valid submission redirects to confirmation ({page.url})")
        public_id = page.locator("code.fs-5").inner_text() if page.locator("code.fs-5").count() else ""
        check(public_id.startswith("CE-"), f"complaint ID shown ({public_id})")
        page.screenshot(path=str(OUT / "03_submitted.png"), full_page=True)

        page.click("text=View complaint")
        imgs_ok = page.evaluate("() => [...document.querySelectorAll('img.evidence-img')].every(i => i.complete && i.naturalWidth > 0)")
        check(imgs_ok, "evidence images load on the detail page")
        detail_url = page.url
        page.screenshot(path=str(OUT / "04_detail.png"), full_page=True)

        # Logout via the navbar form
        page.click("text=Sign out")
        check(page.url.rstrip("/") == base, "sign out returns to home")

        # --- Another citizen cannot read it
        other = ctx.browser.new_context()
        op = other.new_page()
        op.goto(base + "/register")
        e2 = f"browser.{secrets.token_hex(3)}@example.com"
        op.fill("#email", e2); op.fill("#display_name", "Other Tester")
        op.fill("#password", pw); op.fill("#password2", pw); op.check("#accept_terms")
        op.click("button[type=submit]")
        r = op.goto(detail_url)  # separate page/context, not tracked by bad_responses
        check(r.status == 404, f"other citizen gets 404 on the private complaint ({r.status})")
        other.close()

        # --- Reviewer pages
        if rev_email and rev_pw:
            page.goto(base + "/login")
            page.fill("#email", rev_email)
            page.fill("#password", rev_pw)
            page.click("button[type=submit]")
            check("/staff/" in page.url, "reviewer lands on staff dashboard")
            page.wait_for_timeout(800)
            charts = page.evaluate("() => typeof Chart !== 'undefined' && document.querySelectorAll('canvas').length")
            check(bool(charts), f"Chart.js loaded and {charts} chart canvases present")
            page.screenshot(path=str(OUT / "05_staff_dashboard.png"), full_page=True)

            tiles.reset()
            page.goto(base + "/staff/map")
            wait_tiles(page)
            n, blocked, noref = tiles.summary()
            markers = page.locator("#map .leaflet-marker-icon").count()
            check(n > 0 and blocked == 0, f"staff map tiles: {n} requested, {blocked} blocked; {markers} markers")
            page.screenshot(path=str(OUT / "06_staff_map.png"), full_page=True)

            tiles.reset()
            page.goto(base + f"/staff/complaints/{public_id}")
            wait_tiles(page)
            n, blocked, _ = tiles.summary()
            check(n > 0 and blocked == 0, f"review page map tiles: {n} requested, {blocked} blocked")
            check("AI unavailable" in page.content(), "review page shows honest AI-unavailable state")
            page.select_option("#status", "under_review")
            page.click("#a-status button[type=submit]")
            check("Under Review" in page.content(), "reviewer can move complaint to Under Review")
            page.screenshot(path=str(OUT / "07_review.png"), full_page=True)
        else:
            print("SKIP reviewer checks (set CIVICEYE_REVIEWER_EMAIL / CIVICEYE_REVIEWER_PASSWORD)")

        check(not js_errors, "no JavaScript errors" + ("" if not js_errors else ": " + " | ".join(js_errors[:5])))
        check(not bad_responses, "no unexpected 4xx/5xx from the app" +
              ("" if not bad_responses else ": " + " | ".join(bad_responses[:8])))
        browser.close()

    failed = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed. Screenshots: {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
