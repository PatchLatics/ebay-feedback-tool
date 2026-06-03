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

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env and fill in your eBay username and password
```

Or skip this — the tool will prompt you for credentials at runtime if `.env` is not present.

### 3. Run it

```bash
python main.py
```

That's it. The tool will:
1. Log in to eBay (reusing your saved session on future runs — no re-login needed)
2. Find every pending feedback item
3. Pick a varied, natural-sounding positive message for each one
4. Submit them all automatically

---

## Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Show what would be posted without submitting anything |
| `--headed` | Show the browser window while it runs (useful for debugging) |

```bash
# Preview without submitting
python main.py --dry-run

# Watch the browser in action
python main.py --headed
```

---

## How it works

- Uses **Playwright** (headless Chromium) to drive eBay like a real browser.
- Saves your browser session in `.browser_session/` so you only need to log in once.
- If eBay triggers a 2FA / security challenge, the tool pauses and lets you complete it in the browser window, then continues automatically.
- Messages are randomly selected from themed pools (Pokémon cards, football stickers, generic) based on the item title, so they look natural and varied.
- Adds human-like random delays between actions to avoid bot detection.

---

## Notes

- Your credentials are stored only in your local `.env` file — never sent anywhere except eBay's login page.
- The `.browser_session/` directory stores cookies/localStorage. Keep it private (it's gitignored).
- If eBay changes their page layout significantly, the selectors in `ebay_feedback.py` may need updating.
