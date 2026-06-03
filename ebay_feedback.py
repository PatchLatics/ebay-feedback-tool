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

def _get_pending_buyer_items(page: Page) -> list[dict]:
    """
    Navigate to the leave-feedback page and return only items where the
    user is the BUYER (purchases), skipping any seller-side entries.
    Each item dict contains: item_id, title, feedback_url.
    """
    # eBay's feedback page has a "Purchases" tab — click it to filter to buyer items
    page.goto(FEEDBACK_URL, wait_until="domcontentloaded", timeout=30_000)
    _random_delay(1.5, 2.5)

    # Click the "As a Buyer" / "Purchases" tab if present
    for tab_sel in (
        "a:has-text('As a Buyer')",
        "a:has-text('Purchases')",
        "li:has-text('As a Buyer') a",
        "li:has-text('Purchases') a",
        "[data-tab*='buyer' i]",
        "[data-tab*='purchase' i]",
    ):
        try:
            tab = page.locator(tab_sel).first
            if tab.is_visible(timeout=2_000):
                tab.click()
                _random_delay(1.0, 2.0)
                break
        except Exception:
            continue

    items = []

    # Primary: rows with data-itemid attribute
    rows = page.locator("tr.fb-row, .feedback-row, [data-itemid]").all()
    if rows:
        for row in rows:
            item_id = row.get_attribute("data-itemid") or ""
            title_el = row.locator(".item-title, .item-name, td:nth-child(2)").first
            title = title_el.inner_text().strip() if title_el else "Unknown item"
            link_el = row.locator("a[href*='leave_feedback'], a[href*='leavefeedback']").first
            href = link_el.get_attribute("href") if link_el else ""
            if href:
                items.append({"item_id": item_id, "title": title, "feedback_url": href})
        return items

    # Fallback: any leave-feedback links on the page
    for link in page.locator("a[href*='leave_feedback'], a[href*='leavefeedback']").all():
        href = link.get_attribute("href") or ""
        if "item_id=" in href or "itemid=" in href.lower():
            item_id = _extract_param(href, "item_id") or _extract_param(href, "itemId") or ""
            title = link.inner_text().strip() or "Unknown item"
            items.append({"item_id": item_id, "title": title, "feedback_url": href})

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

def run(headless: bool = False, dry_run: bool = False) -> RunSummary:
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
        items = _get_pending_buyer_items(page)
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
