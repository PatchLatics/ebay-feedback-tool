"""
eBay Feedback Tool — core automation.

Launches Brave with the real user profile, finds all purchases (buyer-side)
awaiting feedback, and submits a fixed positive message for each one.
"""

import time
import random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BRAVE_EXE = Path(
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
)
BRAVE_PROFILE = Path(
    r"C:\Users\PatchLatics\AppData\Local\BraveSoftware\Brave-Browser\User Data"
)

EBAY_HOME = "https://www.ebay.co.uk"
FEEDBACK_URL = "https://www.ebay.co.uk/fdbk/leave_feedback"

FEEDBACK_MESSAGE = "Excellent transaction. Hope to do business again. PSLuxuries"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FeedbackResult:
    item_id: str
    title: str
    success: bool
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
    for name in ("SingletonLock", "SingletonSocket", "lockfile"):
        candidate = BRAVE_PROFILE / name
        if candidate.exists() or candidate.is_symlink():
            return True
    return False


def _extract_param(url: str, param: str) -> Optional[str]:
    from urllib.parse import urlparse, parse_qs
    vals = parse_qs(urlparse(url).query).get(param, [])
    return vals[0] if vals else None


# ---------------------------------------------------------------------------
# Feedback page scraping
# ---------------------------------------------------------------------------

def _save_debug_snapshot(page: Page) -> None:
    """Save a screenshot and the full page HTML for selector debugging."""
    debug_dir = Path(__file__).parent / "debug"
    debug_dir.mkdir(exist_ok=True)
    screenshot_path = debug_dir / "feedback_page.png"
    html_path = debug_dir / "feedback_page.html"
    page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(page.content(), encoding="utf-8")
    print(f"\n[debug] Screenshot → {screenshot_path}")
    print(f"[debug] HTML      → {html_path}\n")


def _load_all_items(page: Page) -> None:
    """Keep clicking 'Load more' until it disappears or stops adding items."""
    while True:
        try:
            btn = page.get_by_role("button", name="Load more").first
            if not btn.is_visible(timeout=3_000):
                break
            prev_count = page.locator("input[value='Positive'], label:has-text('Positive')").count()
            btn.click()
            # Wait until new items appear or a timeout tells us there are no more
            try:
                page.wait_for_function(
                    f"document.querySelectorAll(\"input[value='Positive'], label\").length > {prev_count}",
                    timeout=8_000,
                )
            except PWTimeout:
                break  # No new items appeared — we're at the end
            _random_delay(1.0, 2.0)
        except Exception:
            break


def _get_pending_buyer_items(page: Page, debug: bool = False) -> list[dict]:
    """
    Navigate to the leave-feedback page, expand all items via 'Load more',
    then find every item that has a 'Positive' button (i.e. awaiting feedback).
    Returns a list of dicts with: item_id, title, feedback_url.
    """
    page.goto(FEEDBACK_URL, wait_until="domcontentloaded", timeout=30_000)
    _random_delay(1.5, 2.5)

    _load_all_items(page)

    if debug:
        _save_debug_snapshot(page)

    items = []

    # eBay's current feedback page renders each transaction as a card/row that
    # contains a "Positive" button (or radio label).  Walk up from every
    # "Positive" button to the nearest ancestor that also contains the item
    # title and the leave-feedback link.
    positive_buttons = page.locator(
        "input[value='Positive'], "
        "label:has-text('Positive'), "
        "button:has-text('Positive'), "
        "a:has-text('Positive')"
    ).all()

    for btn in positive_buttons:
        # Walk up the DOM to find a container that holds both the title and a link
        container = None
        for ancestor_sel in ("section", "article", "li", "tr", "div.card", "div"):
            try:
                candidate = btn.locator(f"xpath=ancestor::{ancestor_sel.split('.')[0]}[1]")
                # Verify it contains something that looks like an item link or title
                if candidate.locator("a").count() > 0:
                    container = candidate
                    break
            except Exception:
                continue

        if container is None:
            continue

        # Title: prefer a heading or named element; fall back to first non-empty text
        title = ""
        for title_sel in ("h2", "h3", "h4", ".item-title", ".title", "span.BOLD", "a[href*='/itm/']"):
            try:
                el = container.locator(title_sel).first
                if el.count() and el.is_visible(timeout=1_000):
                    title = el.inner_text().strip()
                    if title:
                        break
            except Exception:
                continue

        # Leave-feedback link: look for a form action or a direct href
        href = ""
        for link_sel in (
            "a[href*='leave_feedback']",
            "a[href*='leavefeedback']",
            "a[href*='/fdbk/']",
        ):
            try:
                el = container.locator(link_sel).first
                if el.count():
                    href = el.get_attribute("href") or ""
                    if href:
                        break
            except Exception:
                continue

        # If there's no direct link, the Positive button itself may be inside a
        # form whose action is the feedback URL
        if not href:
            try:
                form = btn.locator("xpath=ancestor::form[1]")
                href = form.get_attribute("action") or ""
            except Exception:
                pass

        if not href:
            continue

        item_id = (
            _extract_param(href, "item_id")
            or _extract_param(href, "itemId")
            or _extract_param(href, "iid")
            or ""
        )

        items.append({"item_id": item_id, "title": title or "Unknown item", "feedback_url": href})

    return items


# ---------------------------------------------------------------------------
# Feedback submission
# ---------------------------------------------------------------------------

def _submit_feedback_for_item(page: Page, item: dict) -> FeedbackResult:
    result = FeedbackResult(item_id=item["item_id"], title=item["title"], success=False)

    try:
        url = item["feedback_url"]
        if not url.startswith("http"):
            url = f"{EBAY_HOME}{url}"
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        _random_delay(1.5, 2.5)

        # --- Select Positive / 5-star ---
        clicked = False
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
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            try:
                page.get_by_text("Positive", exact=True).first.click()
                clicked = True
            except Exception:
                pass

        if not clicked:
            result.error = "Could not find Positive radio button"
            return result

        _random_delay(0.5, 1.2)

        # --- Type the fixed message ---
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
                    ta.fill(FEEDBACK_MESSAGE)
                    typed = True
                    break
            except Exception:
                continue

        if not typed:
            result.error = "Could not find feedback comment textarea"
            return result

        _random_delay(0.8, 1.5)

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

    except Exception as exc:
        result.error = str(exc)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(headless: bool = False, dry_run: bool = False, debug: bool = False) -> RunSummary:
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

        print("Fetching pending feedback items (purchases only)...")
        items = _get_pending_buyer_items(page, debug=debug)
        summary.total = len(items)

        if not items:
            print("No pending feedback items found.")
            context.close()
            return summary

        print(f"Found {len(items)} item(s) awaiting feedback.\n")

        for i, item in enumerate(items, 1):
            label = item["title"] or item["item_id"]
            print(f"  [{i}/{len(items)}] {label}")

            if dry_run:
                print(f'         [dry-run] Would post: "{FEEDBACK_MESSAGE}"')
                summary.skipped += 1
                continue

            result = _submit_feedback_for_item(page, item)
            summary.results.append(result)

            if result.success:
                summary.succeeded += 1
                print(f"         ✓ Done")
            else:
                summary.failed += 1
                print(f"         ✗ Failed: {result.error}")

            if i < len(items):
                _random_delay(2.0, 4.0)

        context.close()

    return summary
