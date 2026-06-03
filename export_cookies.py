"""
export_cookies.py — one-time setup script.

Attaches to your *existing* Brave profile (same cookies, extensions, saved
passwords and fingerprint as your normal browsing session), navigates to
eBay, and saves all eBay cookies to cookies.json.

Because Playwright launches Brave with your real profile, eBay sees a
browser it already recognises — no hCaptcha, no bot detection.

IMPORTANT: Close Brave completely before running this script.
           Chromium locks the profile directory while it is open; two
           processes cannot share it at the same time.

Usage:
    python export_cookies.py
"""

import json
import platform
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

COOKIES_FILE = Path(__file__).parent / "cookies.json"
EBAY_HOME = "https://www.ebay.co.uk"


# ---------------------------------------------------------------------------
# Platform-specific Brave paths
# ---------------------------------------------------------------------------

def _find_brave_executable() -> Path | None:
    """Return the path to the Brave binary, or None if not found."""
    candidates: list[str] = []
    system = platform.system()

    if system == "Linux":
        candidates = [
            "/usr/bin/brave-browser",
            "/usr/bin/brave",
            "/snap/bin/brave",
            "/usr/local/bin/brave-browser",
        ]
    elif system == "Darwin":  # macOS
        candidates = [
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            str(Path.home() / "Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
        ]
    elif system == "Windows":
        local = Path.home() / "AppData/Local"
        candidates = [
            str(local / "BraveSoftware/Brave-Browser/Application/brave.exe"),
            "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
            "C:/Program Files (x86)/BraveSoftware/Brave-Browser/Application/brave.exe",
        ]

    for c in candidates:
        p = Path(c)
        if p.exists():
            return p
    return None


def _find_brave_profile() -> Path | None:
    """Return the path to Brave's User Data directory, or None if not found."""
    system = platform.system()

    if system == "Linux":
        candidates = [
            Path.home() / ".config/BraveSoftware/Brave-Browser",
        ]
    elif system == "Darwin":
        candidates = [
            Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser",
        ]
    elif system == "Windows":
        local = Path.home() / "AppData/Local"
        candidates = [
            local / "BraveSoftware/Brave-Browser/User Data",
        ]
    else:
        return None

    for c in candidates:
        if c.exists():
            return c
    return None


# ---------------------------------------------------------------------------
# Lock-file detection
# ---------------------------------------------------------------------------

def _profile_is_locked(profile_dir: Path) -> bool:
    """
    Return True if another Chromium process is using this profile.
    Chromium writes a 'SingletonLock' symlink (Linux/macOS) or a
    'lockfile' (Windows) while running.
    """
    for lock_name in ("SingletonLock", "lockfile", "SingletonSocket", "SingletonCookie"):
        lock = profile_dir / lock_name
        if lock.exists() or lock.is_symlink():
            return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    brave_exe = _find_brave_executable()
    brave_profile = _find_brave_profile()

    if brave_exe is None:
        print(
            "[!] Brave browser executable not found.\n"
            "    Install Brave from https://brave.com/download/ and try again."
        )
        sys.exit(1)

    if brave_profile is None:
        print(
            "[!] Brave profile directory not found.\n"
            "    Have you launched Brave at least once so it can create a profile?"
        )
        sys.exit(1)

    print(f"Brave executable : {brave_exe}")
    print(f"Brave profile    : {brave_profile}")
    print()

    # Warn and abort if Brave is already running — the lock will cause a crash
    if _profile_is_locked(brave_profile):
        print(
            "[!] Brave appears to be running (profile directory is locked).\n"
            "    Please close Brave completely, then run this script again.\n"
            "\n"
            "    On Linux/macOS: quit Brave from the dock/taskbar or run:\n"
            "        pkill -x 'brave' || pkill -x 'brave-browser'\n"
            "    On Windows: right-click the Brave icon in the system tray → Exit."
        )
        sys.exit(1)

    print("Launching Brave with your existing profile...")
    print("eBay will open automatically. If you are already logged in, just")
    print("press ENTER in this terminal. If not, log in first, then press ENTER.\n")

    with sync_playwright() as pw:
        # launch_persistent_context with the real Brave profile directory means
        # Playwright inherits all of the user's cookies, extensions, saved passwords,
        # and browser fingerprint — eBay cannot distinguish this from a normal session.
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(brave_profile),
            executable_path=str(brave_exe),
            headless=False,
            args=["--start-maximized"],
            viewport=None,        # use the window's natural size
            locale="en-GB",
        )

        page = context.new_page() if not context.pages else context.pages[0]
        page.goto(EBAY_HOME, wait_until="domcontentloaded", timeout=30_000)

        input("Press ENTER once you can see your eBay account (logged-in homepage) > ")

        # Capture all cookies from the session — no validation, just save everything
        cookies = context.cookies()

        context.close()

    if not cookies:
        print("[!] No cookies captured. Try logging in again and re-running this script.")
        sys.exit(1)

    COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
    print(f"\n✓ Saved {len(cookies)} cookies to {COOKIES_FILE.name}")
    print("  You can now run  python main.py  at any time — no manual steps needed.")
    print()
    print("  Keep cookies.json private — it grants full access to your eBay account.")
    print("  Re-run this script if eBay ever signs you out.")


if __name__ == "__main__":
    main()
