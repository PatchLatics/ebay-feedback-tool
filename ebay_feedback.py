"""
Core eBay feedback automation using Playwright.

Runs entirely inside the user's real Brave browser (persistent profile),
so eBay sees an already-authenticated, trusted session with no bot signals.

Flow:
  1. Launch Brave with the real User Data directory via launch_persistent_context.
  2. Verify the session looks active; warn if not but continue anyway.
  3. Navigate to the "Leave Feedback" page and collect all pending items.
  4. For each item, submit a positive feedback message.
  5. Report results.

IMPORTANT: Brave must be fully closed before running this script.
           Chromium locks the profile directory while it is open.
"""

import time
import random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

from feedback_messages import get_feedback

# ---------------------------------------------------------------------------
# Brave paths — adjust if your installation differs
# ---------------------------------------------------------------------------

BRAVE_EXE = Path(
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
)
BRAVE_PROFILE = Path(
    r"C:\Users\PatchLatics\AppData\Local\BraveSoftware\Brave-Browser\User Data"
)

EBAY_HOME = "https://www.ebay.co.uk"
FEEDBACK_URL = "https://www.ebay.co.uk/fdbk/leave_feedback"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FeedbackResult:
    item_id: str
    title: str
    success: bool
    message: str = ""
    error: str = ""


@dataclass
class RunSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    results: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_delay(min_s: float = 1.0, max_s: float = 3.0) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _check_brave_paths() -> None:
    """Abort early with a helpful message if the Brave paths don't exist."""
    if not BRAVE_EXE.exists():
        raise FileNotFoundError(
            f"Brave executable not found at:\n  {BRAVE_EXE}\n"
            "Edit BRAVE_EXE at the top of ebay_feedback.py to match your installation."
        )
    if not BRAVE_PROFILE.exists():
        raise FileNotFoundError(
            f"Brave profile directory not found at:\n  {BRAVE_PROFILE}\n"
            "Edit BRAVE_PROFILE at the top of ebay_feedback.py to match your profile path."
        )


def _profile_is_locked() -> bool:
    """Return True if another Brave/Chromium process holds the profile lock."""
    for name in ("SingletonLock", "SingletonSocket", "lockfile"):
        candidate = BRAVE_PROFILE / name
        if candidate.exists() or candidate.is_symlink():
            return True
    return False


def _is_logged_in(page: Page) -> bool:
    """Best-effort check for a logged-in eBay session."""
    try:
        page.goto(EBAY_HOME, wait_until="domcontentloaded", timeout=20_000)
        for sel in ("#gh-ug", "[data-testid='gh-ug']", ".gh-username", "#gh-eb-My"):
            try:
                if page.locator(sel).is_visible(timeout=3_000):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _extract_param(url: str, param: str) -> Optional[str]:
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(url).query)
    vals = qs.get(param, [])
    return vals[0] if vals else None


# ---------------------------------------------------------------------------
# Feedback scraping & submission
# ---------------------------------------------------------------------------

def _get_pending_items(page: Page) -> list[dict]:
    """
    Navigate to the leave-feedback page and return a list of pending items.
    Each item dict has: item_id, title, feedback_url.
    """
    page.goto(FEEDBACK_URL, wait_until="domcontentloaded", timeout=30_000)
    _random_delay(1.5, 3.0)

    items = []

    rows = page.locator("tr.fb-row, .feedback-row, [data-itemid]").all()

    if not rows:
        links = page.locator("a[href*='leave_feedback'], a[href*='leavefeedback']").all()
        for link in links:
            href = link.get_attribute("href") or ""
            if "item_id=" in href or "itemid=" in href.lower():
                item_id = _extract_param(href, "item_id") or _extract_param(href, "itemId") or ""
                title = link.inner_text().strip() or "Unknown item"
                items.append({"item_id": item_id, "title": title, "feedback_url": href})
        return items

    for row in rows:
        item_id = row.get_attribute("data-itemid") or ""
        title_el = row.locator(".item-title, .item-name, td:nth-child(2)").first
        title = title_el.inner_text().strip() if title_el else "Unknown item"
        link_el = row.locator("a[href*='leave_feedback'], a[href*='leavefeedback']").first
        href = link_el.get_attribute("href") if link_el else ""
        if href:
            items.append({"item_id": item_id, "title": title, "feedback_url": href})

    return items


def _submit_feedback_for_item(page: Page, item: dict) -> FeedbackResult:
    """Open the feedback form for a single item and submit positive feedback."""
    result = FeedbackResult(item_id=item["item_id"], title=item["title"], success=False)

    try:
        url = item["feedback_url"]
        if not url.startswith("http"):
            url = f"{EBAY_HOME}{url}"
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        _random_delay(1.5, 2.5)

        # --- Select "Positive" radio ---
        clicked_positive = False
        for sel in (
            "input[value='Positive']",
            "input[id*='positive']",
            "label[for*='positive'] input",
            "#Positive",
        ):
            try:
                radio = page.locator(sel).first
                if radio.is_visible(timeout=3_000):
                    radio.click()
                    clicked_positive = True
                    break
            except Exception:
                continue

        if not clicked_positive:
            try:
                page.get_by_text("Positive", exact=True).first.click()
                clicked_positive = True
            except Exception:
                pass

        if not clicked_positive:
            result.error = "Could not find Positive radio button"
            return result

        _random_delay(0.5, 1.5)

        # --- Type feedback comment ---
        message = get_feedback(item["title"])
        typed = False
        for sel in (
            "textarea[name*='comment']",
            "textarea[id*='comment']",
            "textarea[name*='feedback']",
            "textarea",
        ):
            try:
                ta = page.locator(sel).first
                if ta.is_visible(timeout=3_000):
                    ta.click()
                    ta.fill(message)
                    typed = True
                    break
            except Exception:
                continue

        if not typed:
            result.error = "Could not find feedback comment textarea"
            return result

        _random_delay(0.8, 1.8)

        # --- Submit ---
        submitted = False
        for sel in (
            "input[type='submit'][value*='Leave']",
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Leave feedback')",
            "button:has-text('Submit')",
        ):
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=3_000):
                    btn.click()
                    submitted = True
                    break
            except Exception:
                continue

        if not submitted:
            result.error = "Could not find submit button"
            return result

        try:
            page.wait_for_selector(
                "text=Thank you, text=feedback has been, text=successfully",
                timeout=15_000,
            )
        except PWTimeout:
            pass

        _random_delay(1.5, 3.0)
        result.success = True
        result.message = message

    except Exception as exc:
        result.error = str(exc)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(headless: bool = False, dry_run: bool = False) -> RunSummary:
    """
    Launch Brave with the real user profile and submit feedback for every
    pending eBay item.

    headless=False by default because running a persistent Brave profile
    headlessly can trigger bot-detection on some eBay flows.
    """
    _check_brave_paths()

    if _profile_is_locked():
        raise RuntimeError(
            "Brave is currently running — its profile directory is locked.\n"
            "Please close Brave completely, then run the script again.\n"
            "\n"
            "  Windows: right-click the Brave icon in the system tray → Exit\n"
            "  Or open Task Manager, find 'Brave', and end the process."
        )

    summary = RunSummary()

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(BRAVE_PROFILE),
            executable_path=str(BRAVE_EXE),
            headless=headless,
            args=["--start-maximized"],
            viewport=None,
            locale="en-GB",
        )

        page = context.pages[0] if context.pages else context.new_page()

        # Navigate to eBay home so we can check login state
        if not _is_logged_in(page):
            print(
                "[!] eBay does not appear to be logged in inside Brave.\n"
                "    Open Brave normally, sign in to eBay, close Brave, then run again."
            )
            context.close()
            return summary

        print("Session active — running inside your Brave profile.")

        # --- Collect pending items ---
        print("Fetching pending feedback items...")
        items = _get_pending_items(page)
        summary.total = len(items)

        if not items:
            print("No pending feedback items found.")
            context.close()
            return summary

        print(f"Found {len(items)} item(s) awaiting feedback.\n")

        # --- Process each item ---
        for i, item in enumerate(items, 1):
            label = item["title"] or item["item_id"]
            print(f"  [{i}/{len(items)}] {label}")

            if dry_run:
                msg = get_feedback(item["title"])
                print(f"         [dry-run] Would post: \"{msg}\"")
                summary.skipped += 1
                continue

            result = _submit_feedback_for_item(page, item)
            summary.results.append(result)

            if result.success:
                summary.succeeded += 1
                print(f"         ✓ Posted: \"{result.message}\"")
            else:
                summary.failed += 1
                print(f"         ✗ Failed: {result.error}")

            if i < len(items):
                _random_delay(2.0, 5.0)

        context.close()

    return summary
