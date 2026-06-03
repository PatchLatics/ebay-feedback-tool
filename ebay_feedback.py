"""
Core eBay feedback automation using Playwright.

Flow:
  1. Launch a persistent browser context (saves login session between runs).
  2. Log in if not already authenticated.
  3. Navigate to the "Leave Feedback" page and collect all pending items.
  4. For each item, submit a positive feedback message.
  5. Report results.
"""

import os
import time
import random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError as PWTimeout

from feedback_messages import get_feedback

# Path where the browser session/cookies are stored between runs
SESSION_DIR = Path(__file__).parent / ".browser_session"

EBAY_HOME = "https://www.ebay.co.uk"
FEEDBACK_URL = "https://www.ebay.co.uk/fdbk/leave_feedback"


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
    """Pause for a human-like random interval."""
    time.sleep(random.uniform(min_s, max_s))


def _is_logged_in(page: Page) -> bool:
    """Quick check: look for the signed-in username element."""
    try:
        page.goto(EBAY_HOME, wait_until="domcontentloaded", timeout=20_000)
        # eBay shows a greeting element when logged in
        return page.locator("#gh-ug").is_visible(timeout=4_000)
    except Exception:
        return False


def _login(page: Page, username: str, password: str) -> None:
    """Perform eBay sign-in flow."""
    page.goto(f"{EBAY_HOME}/signin/", wait_until="domcontentloaded", timeout=30_000)
    _random_delay()

    # Enter username / email
    page.fill("#userid", username)
    page.click("#signin-continue-btn")
    _random_delay(1.5, 3.0)

    # Enter password
    page.wait_for_selector("#pass", timeout=15_000)
    page.fill("#pass", password)
    _random_delay(0.5, 1.5)
    page.click("#sgnBt")

    # Wait for redirect back to home / dashboard
    try:
        page.wait_for_url(lambda url: "signin" not in url, timeout=30_000)
    except PWTimeout:
        pass  # May already be on the right page

    _random_delay(2.0, 4.0)

    # Check for 2FA / security challenge — pause and let the user handle it
    if "challenge" in page.url or "verify" in page.url or "security" in page.url.lower():
        print(
            "\n[!] eBay is asking for verification (2FA / CAPTCHA).\n"
            "    Please complete it in the browser window, then press ENTER here to continue."
        )
        input("    Press ENTER when done > ")
        _random_delay(2.0, 3.0)


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

    # eBay renders feedback items in a table/list; selectors may shift but these are stable.
    # Primary approach: look for "Leave feedback" buttons/links with item data.
    rows = page.locator("tr.fb-row, .feedback-row, [data-itemid]").all()

    if not rows:
        # Fallback: parse the feedback landing page for links
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


def _extract_param(url: str, param: str) -> Optional[str]:
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(url).query)
    vals = qs.get(param, [])
    return vals[0] if vals else None


def _submit_feedback_for_item(page: Page, item: dict) -> FeedbackResult:
    """Open the feedback form for a single item and submit positive feedback."""
    item_id = item["item_id"]
    title = item["title"]
    feedback_url = item["feedback_url"]

    result = FeedbackResult(item_id=item_id, title=title, success=False)

    try:
        # Navigate to the individual feedback form
        if feedback_url.startswith("http"):
            page.goto(feedback_url, wait_until="domcontentloaded", timeout=30_000)
        else:
            page.goto(f"{EBAY_HOME}{feedback_url}", wait_until="domcontentloaded", timeout=30_000)
        _random_delay(1.5, 2.5)

        # --- Select "Positive" radio ---
        positive_selectors = [
            "input[value='Positive']",
            "input[id*='positive']",
            "label[for*='positive'] input",
            "#Positive",
        ]
        clicked_positive = False
        for sel in positive_selectors:
            try:
                radio = page.locator(sel).first
                if radio.is_visible(timeout=3_000):
                    radio.click()
                    clicked_positive = True
                    break
            except Exception:
                continue

        if not clicked_positive:
            # Try clicking a "Positive" label directly
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
        message = get_feedback(title)
        comment_selectors = [
            "textarea[name*='comment']",
            "textarea[id*='comment']",
            "textarea[name*='feedback']",
            "textarea",
        ]
        typed = False
        for sel in comment_selectors:
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
        submit_selectors = [
            "input[type='submit'][value*='Leave']",
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Leave feedback')",
            "button:has-text('Submit')",
        ]
        submitted = False
        for sel in submit_selectors:
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

        # Wait for confirmation
        try:
            page.wait_for_selector(
                "text=Thank you, text=feedback has been, text=successfully",
                timeout=15_000,
            )
        except PWTimeout:
            # Acceptable — some eBay pages redirect without a visible confirmation
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

def run(username: str, password: str, headless: bool = True, dry_run: bool = False) -> RunSummary:
    """
    Main entry point. Logs in (reusing saved session if available), then
    iterates over all pending feedback items and submits positive feedback.
    """
    SESSION_DIR.mkdir(exist_ok=True)
    summary = RunSummary()

    with sync_playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 800},
            locale="en-GB",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        page = browser.new_page() if browser.pages == [] else browser.pages[0]

        # --- Auth ---
        if not _is_logged_in(page):
            print("Not logged in — signing in to eBay...")
            _login(page, username, password)
            if not _is_logged_in(page):
                print("[!] Login failed. Check your credentials and try again.")
                browser.close()
                return summary
            print("Logged in successfully.")
        else:
            print("Session active — already logged in.")

        # --- Collect pending items ---
        print("Fetching pending feedback items...")
        items = _get_pending_items(page)
        summary.total = len(items)

        if not items:
            print("No pending feedback items found.")
            browser.close()
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

            # Polite delay between submissions
            if i < len(items):
                _random_delay(2.0, 5.0)

        browser.close()

    return summary
