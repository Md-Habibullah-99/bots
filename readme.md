# Discord Bots: Meeting Reminders and Presence Alerts

Two lightweight Discord bots live in this repository under `DiscordBots/`:

- Meeting Reminder Bot (`DiscordBots/meetingReminder.py`): schedule meeting reminders with 12‑hour time input and send notices at 15, 10, 2 minutes, and at start time. Users can acknowledge with `!ok` to reduce intermediate pings.
- Presence Alert Bot (`DiscordBots/isOnlineDiscordBot.py`): watches specific user IDs and posts a message when any of them comes online in your server.

This README covers both how a developer should set them up and how end users interact with them in Discord.

> Note: Per request, this guide documents only the `DiscordBots/` folder.

## What’s inside

```
DiscordBots/
	├─ isOnlineDiscordBot.py     # Posts when target users come online
	└─ meetingReminder.py        # Schedule and manage meeting reminders via commands
```

## Prerequisites

- Python 3.9+ (3.10+ recommended)
- A Discord account with permission to add a bot to your server
- A Discord Application and Bot token (created in Discord Developer Portal)
- Basic terminal access on Linux/macOS/WSL

Python packages used:

- `discord.py` (Discord API client)
- `pytz` (timezone handling; used by the reminder bot)
- `python-dotenv` (optional; if you choose to load secrets from a `.env` file)

## 1) Create and configure your Discord bot

1. Open https://discord.com/developers/applications and click “New Application”.
2. In the left sidebar → “Bot” → “Add Bot”. Copy the bot token (you’ll need it later).
3. Under Bot → Privileged Gateway Intents, enable the following based on the bot(s) you plan to run:
	 - Meeting Reminder bot: enable “Server Members Intent” and “Message Content Intent”.
	 - Presence Alert bot: enable “Server Members Intent” and “Presence Intent”.
4. Invite the bot to your server: under “OAuth2” → “URL Generator”
	 - Scopes: `bot`
	 - Bot Permissions (minimum): `Read Messages/View Channels`, `Send Messages`
	 - Open the generated URL and add the bot to your server.

## 2) Local setup (developer)

Create and activate a virtual environment, then install dependencies.

```bash
# From the repo root
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install discord.py pytz python-dotenv
```

Optional: create a `.env` file (used if you modify code to read env vars) and keep it out of git:

```
# .env (example)
DISCORD_TOKEN=your-bot-token
TARGET_USER_IDS=123456789012345678,987654321098765432
NOTIFICATION_CHANNEL_ID=112233445566778899
```

Make sure `.env` is listed in `.gitignore` (don’t commit secrets).

## 3) Configure and run the bots

You can run either bot independently. Use separate terminals if you want both online at the same time.

### A) Meeting Reminder Bot (`DiscordBots/meetingReminder.py`)

What it does

- Registers chat commands with a prefix (default `!`).
- Stores reminders in memory and checks every minute.
- Sends group pings at 15, 10, and 2 minutes before the meeting, plus a “time is now” message.
- Users can reply `!ok` to suppress intermediate reminders (they’ll still get the 2‑minute and “now” notices).

Configure

- Open `DiscordBots/meetingReminder.py` and review these variables at the top:
	- `BOT_PREFIX` (default `!`)
	- `TIMEZONE_STR` (default `Asia/Dhaka`) — set to your preferred IANA timezone, e.g., `America/New_York`.
- At the bottom of the file, replace the placeholder in `client.run('Your bot token goes here')` with your actual bot token string. If you prefer environment variables, you can replace that line with something like `client.run(os.getenv('DISCORD_TOKEN'))` after importing `os` and loading `.env` via `dotenv`.

Run

```bash
cd DiscordBots
python meetingReminder.py
```

Use in Discord (for end users)

- Time format: 12‑hour with AM/PM, quoted date-time string: "YYYY-MM-DD HH:MM AM/PM"
- Commands:
	- `!schedule "2025-12-31 02:30 PM" @User1 @User2 Team Sync`
		- Schedules a meeting called “Team Sync” at the specified time for everyone mentioned.
		- The scheduler is auto-added if not mentioned.
	- `!ok`
		- Acknowledge your next upcoming meeting to skip the 15 and 10 minute reminders (you’ll still get 2‑minute and “now”).
	- `!list`
		- List meetings you scheduled, with temporary IDs.
	- `!cancel <ID>`
		- Cancel a meeting you scheduled by its ID from `!list`.

Examples

```text
!schedule "2025-11-01 09:00 AM" @alice @bob Project kickoff
!ok
!list
!cancel 1
```

Notes

- If the time is in the past or less than 1 minute ahead, scheduling will be rejected.
- All times are interpreted in `TIMEZONE_STR`.
- Reminders clear from memory when the “now” message is sent or the process restarts.

### B) Presence Alert Bot (`DiscordBots/isOnlineDiscordBot.py`)

What it does

- Listens to presence updates and posts to a channel when a specific user comes online.

Configure

- Open `DiscordBots/isOnlineDiscordBot.py` and set:
	- `TARGET_USER_IDs` to a list of integer Discord user IDs to watch.
	- `NOTIFICATION_CHANNEL_ID` to the ID of the text channel where alerts should be posted.
	- Replace the placeholder in `client.run('bot id here/token')` with your bot token.
- Intents: the code already enables `members` and `presences`. Ensure both are enabled for your bot in the Developer Portal (see step 1 above).
- Optional (recommended): switch to environment variables (`DISCORD_TOKEN`, `TARGET_USER_IDS`, `NOTIFICATION_CHANNEL_ID`) using `os.getenv(...)` and `python-dotenv`.

Run

```bash
cd DiscordBots
python isOnlineDiscordBot.py
```

Behavior

- When any target user transitions to `online`, the bot posts a message mentioning them in the configured channel.

## Troubleshooting

- Bot doesn’t respond to commands
	- Confirm the bot is online in your server (green status in terminal after `on_ready`).
	- Ensure “Message Content Intent” is enabled (required for command parsing) and the bot has permission to read and send messages in that channel.
- Presence alerts never fire
	- Ensure “Presence Intent” and “Server Members Intent” are enabled in Developer Portal and that the bot is in a guild (server) with those users.
- “Invalid date/time format” errors
	- Use the exact format with quotes and AM/PM, e.g., `"2025-12-31 02:30 PM"`.
- Timezone appears wrong
	- Set `TIMEZONE_STR` to your local timezone (IANA name) in `meetingReminder.py`.
- Permissions
	- Make sure the bot’s role has “View Channels” and “Send Messages” in the target channel, and the channel isn’t muted or restricted.

## Security and secrets

- Never commit bot tokens. Prefer environment variables and a `.env` file ignored by git.
- Rotate tokens immediately if exposed.
- Limit permissions to the minimum necessary when inviting the bot.

## Developer notes

- These scripts are intentionally simple and have no database; reminders are in-memory. If you need persistence, consider storing reminders in a database (SQLite, Postgres) and reloading them on startup.
- If you run both bots with the same token, use separate terminals. It’s often cleaner to register/use distinct bot apps (tokens) per function.

## License

No license file is included. If you plan to share this publicly, consider adding a license (e.g., MIT) to clarify usage rights.

