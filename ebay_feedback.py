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
    """Quick check: look for any signed-in indicator eBay renders in the header."""
    try:
        page.goto(EBAY_HOME, wait_until="domcontentloaded", timeout=20_000)
        # Try multiple known header selectors across eBay layout versions
        for sel in ("#gh-ug", "[data-testid='gh-ug']", ".gh-username", "#gh-eb-My"):
            try:
                if page.locator(sel).is_visible(timeout=3_000):
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def _fill_input(page: Page, selectors: list[str], value: str, timeout_each: int = 4_000) -> bool:
    """Try each selector in order; fill the first visible one. Returns True on success."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=timeout_each)
            el.click()
            el.fill(value)
            return True
        except Exception:
            continue
    return False


def _click_button(page: Page, selectors: list[str], timeout_each: int = 4_000) -> bool:
    """Try each selector in order; click the first visible one. Returns True on success."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=timeout_each)
            el.click()
            return True
        except Exception:
            continue
    return False


def _handle_challenge(page: Page) -> None:
    """Pause and let the user resolve any 2FA / CAPTCHA / security challenge."""
    print(
        "\n[!] eBay is asking for verification (2FA / CAPTCHA).\n"
        "    Please complete it in the browser window, then press ENTER here to continue."
    )
    input("    Press ENTER when done > ")
    _random_delay(2.0, 3.0)


def _login(page: Page, username: str, password: str) -> None:
    """Perform eBay sign-in, handling both the legacy and current two-step login flow."""
    # eBay sometimes redirects /signin/ to signin.ebay.co.uk — follow it
    page.goto(f"{EBAY_HOME}/signin/", wait_until="domcontentloaded", timeout=30_000)
    _random_delay(1.5, 2.5)

    # --- Step 1: username / email ---
    # eBay has used several IDs/attributes for this field over the years
    username_selectors = [
        "#userid",                          # legacy id
        "input[name='userid']",             # name attr (stable)
        "input[type='email']",              # newer layout
        "input[type='text'][autocomplete*='email']",
        "input[aria-label*='email' i]",
        "input[aria-label*='username' i]",
        "input[placeholder*='email' i]",
        "input[placeholder*='username' i]",
        "form input[type='text']",          # last-resort generic
    ]
    if not _fill_input(page, username_selectors, username, timeout_each=5_000):
        raise RuntimeError(
            "Could not find the username/email input on eBay's login page. "
            "Run with --headed to debug."
        )

    _random_delay(0.5, 1.0)

    # --- Continue button (shown before password on two-step flow) ---
    continue_selectors = [
        "#signin-continue-btn",
        "button[id*='continue']",
        "input[id*='continue']",
        "button[type='submit']:has-text('Continue')",
        "button[type='submit']:has-text('Sign in')",
        "button[type='submit']",
        "input[type='submit']",
    ]
    _click_button(page, continue_selectors, timeout_each=4_000)
    _random_delay(1.5, 3.0)

    # Check for immediate challenge after entering email
    if any(k in page.url for k in ("challenge", "verify", "security", "captcha")):
        _handle_challenge(page)

    # --- Step 2: password ---
    password_selectors = [
        "#pass",
        "input[name='pass']",
        "input[type='password']",
        "input[aria-label*='password' i]",
        "input[placeholder*='password' i]",
    ]
    if not _fill_input(page, password_selectors, password, timeout_each=15_000):
        raise RuntimeError(
            "Could not find the password input on eBay's login page. "
            "Run with --headed to debug."
        )

    _random_delay(0.5, 1.2)

    # --- Sign-in submit button ---
    signin_selectors = [
        "#sgnBt",
        "button[id*='sgnBt']",
        "input[id*='sgnBt']",
        "button[type='submit']:has-text('Sign in')",
        "button[type='submit']",
        "input[type='submit']",
    ]
    _click_button(page, signin_selectors, timeout_each=4_000)

    # Wait for navigation away from the sign-in page
    try:
        page.wait_for_url(lambda url: "signin" not in url.lower(), timeout=30_000)
    except PWTimeout:
        pass

    _random_delay(2.0, 3.5)

    # Handle post-login challenge (2FA, SMS code, CAPTCHA, etc.)
    if any(k in page.url.lower() for k in ("challenge", "verify", "security", "captcha", "2fa", "otp")):
        _handle_challenge(page)


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
