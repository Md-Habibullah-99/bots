# Discord Bots: Meeting Reminders and Presence Alerts

Two lightweight Discord bots live in this repository under `DiscordBots/`:

- Meeting Reminder Bot (`DiscordBots/meetingReminder.py`): schedule meeting reminders with 12‑hour time input and send notices at 15, 10, 2 minutes, and at start time. Users can acknowledge with `!ok` to reduce intermediate pings.
- Presence Alert Bot (`DiscordBots/isOnlineDiscordBot.py`): watches specific user IDs and posts a message when any of them comes online in your server.

This README covers both how a developer should set them up and how end users interact with them in Discord.

> Note: Per request, this guide documents only the `DiscordBots/` folder.

## What’s inside

```
DiscordBots/
	├─ isOnlineDiscordBot.py     # Presence tracking with per-user schedules + daily reports
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

- Tracks presence for specific users you configure.
- On the first online event of the day, posts whether they were early, on time, or late relative to their scheduled IN time.
- Accumulates session time across the day (from first online to last offline).
- At local midnight, posts a daily attendance report per tracked user with:
	- Scheduled window (IN/OUT)
	- First Online and Last Offline timestamps (12‑hour format)
	- Total elapsed time from first online to last offline
	- Extra time or missing time compared to the schedule

Configure

- Open `DiscordBots/isOnlineDiscordBot.py` and set:
	- `TARGET_TIMEZONE` — IANA timezone for your location (default: `Asia/Dhaka`). All times are computed and displayed in this timezone.
	- `SCHEDULED_USERS` — per‑user schedule map using 24‑hour time strings (`HH:MM`) with day‑wise overrides and a `default` fallback. Example:

		```python
		SCHEDULED_USERS = {
				"121exampleid1": {
						"Saturday": {"in": "10:00", "out": "23:00"},
						"Sunday":   {"in": "11:00", "out": "21:00"},
						"default":  {"in": "09:00", "out": "18:00"}
				},
				"212exampleid2": {
						"Monday":  {"in": "09:30", "out": "17:30"},
						"default": {"in": "10:00", "out": "19:00"}
				}
		}
		```

		Notes:
		- Keys are Discord user IDs as strings.
		- Day names must be full names (e.g., `Monday`, `Tuesday`).
		- If a day isn’t specified, `default` is used.

	- `NOTIFICATION_CHANNEL_ID` — numeric ID of the channel where alerts/reports are posted.
	- At the bottom, replace `client.run('bot id here/token')` with your bot token string. If you prefer environment variables, you can modify the script to read `os.getenv('DISCORD_TOKEN')`.

- Intents: the code enables `members` and `presences`. Ensure both are turned on for your bot in the Developer Portal.

Run

```bash
cd DiscordBots
python isOnlineDiscordBot.py
```

Behavior

- Online event:
	- When a tracked user first comes online for the day, the bot posts an alert indicating if they were Early, On time, or Late compared to their scheduled IN time.
	- Subsequent online/offline transitions accumulate total time; the first‑online message is sent only once per day per user.
- Offline/away event:
	- Ends the current session and records `last_offline` for the day.
- Daily report at midnight (local timezone):
	- Posts an attendance summary for the previous day, including First Online, Last Offline, Total Elapsed (first→last), scheduled window, and whether extra or missing time occurred.
- Time formats:
	- Inputs in `SCHEDULED_USERS` use 24‑hour format (`HH:MM`).
	- All messages display times in 12‑hour format with AM/PM and timezone abbreviation.
- Persistence:
	- The bot writes lightweight tracking data to `schedule_data.json` in the working directory and resets per user at the start of each new day.

## Troubleshooting

- Bot doesn’t respond to commands
	- Confirm the bot is online in your server (green status in terminal after `on_ready`).
	- Ensure “Message Content Intent” is enabled (required for command parsing) and the bot has permission to read and send messages in that channel.
- Presence alerts never fire
	- Ensure “Presence Intent” and “Server Members Intent” are enabled in Developer Portal and that the bot is in a guild (server) with those users.
	- Confirm the user is included in `SCHEDULED_USERS`.
	- Verify `NOTIFICATION_CHANNEL_ID` points to a channel the bot can access.
- Midnight report didn’t appear
	- The bot must be running across midnight in the configured timezone; if it starts after midnight, it will wait until the next midnight.
	- Check that `NOTIFICATION_CHANNEL_ID` is correct, and the bot has permission to post there.
- “Invalid date/time format” errors
	- Use the exact format with quotes and AM/PM, e.g., `"2025-12-31 02:30 PM"`.
- Timezone appears wrong
	- Set `TIMEZONE_STR` in `meetingReminder.py` and `TARGET_TIMEZONE` in `isOnlineDiscordBot.py` to your local IANA timezone (e.g., `America/New_York`).
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

