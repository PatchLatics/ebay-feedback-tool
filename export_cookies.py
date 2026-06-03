"""
export_cookies.py — one-time setup script.

Opens a visible Brave browser window, navigates to eBay, and waits for you
to log in manually. Once you confirm you're logged in, it saves all eBay
cookies to cookies.json so the main script can reuse them without triggering
hCaptcha or any automated-login detection.

Usage:
    python export_cookies.py
"""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

COOKIES_FILE = Path(__file__).parent / "cookies.json"
EBAY_HOME = "https://www.ebay.co.uk"

# Brave executable search paths per platform
_BRAVE_CANDIDATES = [
    # Linux
    "/usr/bin/brave-browser",
    "/usr/bin/brave",
    "/snap/bin/brave",
    "/usr/local/bin/brave-browser",
    # macOS
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    # Windows (forward slashes work in Playwright)
    "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
    "C:/Program Files (x86)/BraveSoftware/Brave-Browser/Application/brave.exe",
]


def _find_brave() -> str | None:
    for path in _BRAVE_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def _is_logged_in(page: Page) -> bool:
    for sel in ("#gh-ug", "[data-testid='gh-ug']", ".gh-username", "#gh-eb-My"):
        try:
            if page.locator(sel).is_visible(timeout=2_000):
                return True
        except Exception:
            continue
    return False


def main() -> None:
    brave_path = _find_brave()
    if brave_path is None:
        print(
            "[!] Brave browser not found.\n"
            "    Install Brave from https://brave.com/download/ and try again.\n"
            "    If it's installed in a non-standard location, add the path to\n"
            "    _BRAVE_CANDIDATES at the top of export_cookies.py."
        )
        sys.exit(1)

    print(f"Using Brave at: {brave_path}")
    print("Opening eBay in Brave — please log in manually in the browser window.")
    print("Press ENTER here once you are fully logged in.\n")

    with sync_playwright() as pw:
        # Launch a plain (non-persistent) Brave context, fully visible
        browser = pw.chromium.launch(
            executable_path=brave_path,
            headless=False,
            args=["--start-maximized"],
        )
        context = browser.new_context(
            viewport=None,  # use the window's natural size
            locale="en-GB",
        )
        page = context.new_page()
        page.goto(EBAY_HOME, wait_until="domcontentloaded", timeout=30_000)

        # Wait for the user to say they're done
        input("Press ENTER once you are logged in to eBay > ")

        # Verify we can see a logged-in state before saving
        page.goto(EBAY_HOME, wait_until="domcontentloaded", timeout=20_000)
        time.sleep(2)

        if not _is_logged_in(page):
            print(
                "\n[!] Could not detect a logged-in session on the page.\n"
                "    Make sure you are signed in to eBay, then run this script again."
            )
            browser.close()
            sys.exit(1)

        # Dump all cookies for eBay domains
        cookies = context.cookies([
            "https://www.ebay.co.uk",
            "https://signin.ebay.co.uk",
            "https://ebay.co.uk",
        ])

        browser.close()

    if not cookies:
        print("[!] No cookies captured. Try logging in again and re-running this script.")
        sys.exit(1)

    COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
    print(f"\n✓ Saved {len(cookies)} cookies to {COOKIES_FILE.name}")
    print("  You can now run  python main.py  at any time — no manual login needed.")
    print("\n  Keep cookies.json private — it grants full access to your eBay account.")
    print("  Re-run this script if eBay ever signs you out.")


if __name__ == "__main__":
    main()
