# eBay Feedback Tool

Automatically leaves positive feedback on all pending eBay orders — no manual steps, no cookie exports, no bot detection.

Runs entirely inside your real Brave browser profile, so eBay sees the same trusted session it always sees when you browse normally.

---

## Requirements

- Python 3.11+
- [Brave browser](https://brave.com/download/) installed (uses your existing profile)
- Playwright

---

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

That's it. No credentials to configure, no cookies to export.

---

## Usage

**Close Brave first**, then run:

```bash
python main.py
```

The tool will:
1. Launch Brave using your real profile (same session eBay already trusts)
2. Find every order awaiting feedback
3. Submit a varied, natural-sounding positive message for each one automatically

### Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Show what would be posted without submitting anything |
| `--headed` | Keep the Brave window visible while running |

```bash
python main.py --dry-run
python main.py --headed
```

---

## How it works

Playwright's `launch_persistent_context` opens Brave pointed at your real `User Data` directory — the same cookies, extensions, saved passwords and browser fingerprint you use every day. eBay cannot distinguish this from you opening Brave manually and going to the feedback page yourself.

Feedback messages are randomly selected from themed pools (Pokémon cards, football stickers, generic) based on the item title, keeping them varied and natural.

---

## Brave paths

The tool is pre-configured for the default Windows Brave installation:

| Setting | Path |
|---------|------|
| Brave executable | `C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe` |
| Brave profile | `C:\Users\PatchLatics\AppData\Local\BraveSoftware\Brave-Browser\User Data` |

If your paths differ, edit `BRAVE_EXE` and `BRAVE_PROFILE` at the top of `ebay_feedback.py`.

---

## Notes

- **Brave must be fully closed** before running — Chromium locks the profile directory while it's open. The tool detects this and shows a clear error if Brave is still running.
- If eBay prompts you to log in inside the Brave window, just log in normally, let the script finish, and it will work on all future runs.
