# eBay Feedback Tool

Automatically leaves positive feedback on all pending eBay orders — no manual steps after first-time setup.

Designed for buyers who purchase lots of individual Pokémon cards / football stickers and spend hours leaving feedback manually.

---

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Capture your session (one-time setup)

```bash
python export_cookies.py
```

This opens a **Brave browser** window, navigates to eBay, and waits for you to log in manually — bypassing hCaptcha entirely. Once you confirm you're logged in, it saves your session cookies to `cookies.json`. You only need to do this once (or whenever eBay signs you out).

> **Requires Brave browser.** Download from https://brave.com/download/ if you don't have it.

### 3. Run it

```bash
python main.py
```

That's it. The tool loads your saved cookies, verifies the session is active, finds every pending feedback item, and submits a varied positive message for each one — fully automatically.

---

## Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Show what would be posted without submitting anything |
| `--headed` | Show the Chromium window while it runs (useful for debugging) |

```bash
python main.py --dry-run
python main.py --headed
```

---

## How it works

- **`export_cookies.py`** — opens Brave (a real browser, not Playwright's bundled Chromium) so eBay's hCaptcha never triggers. After you log in normally, it dumps all eBay session cookies to `cookies.json`.
- **`main.py` / `ebay_feedback.py`** — launches headless Chromium, injects the saved cookies before loading any page, then processes all pending feedback items.
- Messages are randomly selected from themed pools (Pokémon cards, football stickers, generic) based on the item title, so they look natural and varied.
- Adds human-like random delays between actions.
- If eBay ever expires the session, the tool detects it immediately and tells you to re-run `export_cookies.py`.

---

## Files

| File | Purpose |
|------|---------|
| `export_cookies.py` | One-time setup: log in via Brave, save cookies |
| `main.py` | CLI entry point |
| `ebay_feedback.py` | Core automation logic |
| `feedback_messages.py` | Varied positive message pools |
| `cookies.json` | Your saved session *(gitignored — keep private)* |

---

## Notes

- `cookies.json` grants full access to your eBay account — keep it private and never commit it.
- Re-run `export_cookies.py` if the tool reports that cookies are expired.
- Set `HEADLESS=false` in a `.env` file (or use `--headed`) to watch the browser work.
