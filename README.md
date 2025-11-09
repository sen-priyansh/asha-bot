# Asha Discord Bot

Feature-rich Discord bot with moderation, leveling, reaction roles, AI chat (Gemini), and utility commands.

## ✨ Core Features

### Moderation
`/ban`, `/kick`, `/mute`, `/unmute`, `/warn`, `/warnings`, `/clearwarnings`, `/purge`

### Leveling System
Automatic XP from messages, level-based role rewards, custom level-up messages, rich diagnostics, backups, image cards.

Key commands:
`/level check` – View your (or another user's) level
`/level leaderboard` – Text leaderboard
`/level card show` – Image level card
`/level admin setxp | addxp | setlevel` – Admin XP/level management
`/level role add | remove | list` – Configure role rewards
`/level settings xprate` – Adjust XP min/max & cooldown
`/level settings setmessage | clearmessage | listmessages` – Manage level-up messages
`/level settings levelupchannel` – Set a dedicated announcement channel
`/level settings toggleleveling` – Enable/disable leveling globally
`/level settings togglemessages` – Enable/disable level-up announcements
`/level card background | resetbackgrounds` – Per-user card background images
`/level advanced topleaderboard` – Image leaderboard
`/level advanced resetuser | resetall` – Dangerous reset operations (with confirmation)
`/level advanced diagnose` – Auto-fix & report issues
`/level advanced backup` – Export structured JSON backup
`/level advanced syncfonts` – Download fonts for better card rendering
`/level advanced resetcards` – Remove all custom backgrounds

### Reaction Roles
Create reaction/button role messages and configure limits/requirements.
`/reaction create`, `/reaction add`, `/reaction remove`, `/reaction list`, `/reaction settings`, `/reaction edit`

### Utility & System
`/ping`, `/botinfo`, `/serverinfo`, `/userinfo`, `/help`, `/sync`

### AI Chat (Gemini)
Configured via `GEMINI_API_KEY` for chat/response features (see `aichat.py`).

## 🛠 Setup
```bash
git clone <repo_url>
cd asha-bot
python -m venv .venv
./.venv/Scripts/Activate.ps1  # PowerShell (Windows)
pip install -r requirements.txt
```

Create a `.env` file:
```
DISCORD_TOKEN=your_bot_token
GEMINI_API_KEY=your_gemini_api_key   # optional unless using AI chat
OWNER_ID=your_user_id_numeric
```

Run:
```bash
python bot.py
```

## 🔑 Required Privileged Intents
Enable in the Discord Developer Portal:
- Server Members Intent
- Message Content Intent
- (Presence Intent optional)

## 🧪 Leveling Formula
Total XP for level L: `5*L^2 + 50*L + 100`.
XP gain per message: random between configured `min_xp` and `max_xp` after cooldown.

## 🖼 Level Cards & Leaderboard Images
Uses Pillow; run `/level advanced syncfonts` for better typography. Supports custom backgrounds (PNG/JPG/WEBP < 8MB).

## 🔒 Permissions Needed
- Manage Roles (role rewards, moderation)
- Manage Messages (purge, warn checks)
- Send Messages / Embed Links / Add Reactions
- Read Message History

## 💾 Persistence
JSON files in root:
- `leveling.json`, `level_roles.json`, `level_messages.json`, `level_backgrounds.json`, `leveling_settings.json`
- `reaction_roles.json`
Periodic autosave tasks run every 5 minutes.

## 🩺 Diagnostics
Use `/level advanced diagnose` to auto-detect & fix malformed data (missing roles, orphaned users, invalid channels).

## 🚨 Resets
`/level advanced resetuser` (single user) and `/level advanced resetall` (entire server) have confirmation prompts. Irreversible.

## 📤 Backups
`/level advanced backup` exports a versioned JSON snapshot (safe to store externally).

## 🤖 AI Chat
Requires valid Gemini API key. Configure model & parameters in `config.py`.

## 🪲 Troubleshooting
- Token NoneType error → Check `.env` naming (`DISCORD_TOKEN`).
- Privileged intents error → Enable intents in portal.
- Font rendering fallback → Run `/level advanced syncfonts`.
- Image card errors → Ensure Pillow installed & background URL accessible.

## 📄 License
MIT

---
Contributions & feature requests welcome. Feel free to open issues for enhancements or bug reports.
