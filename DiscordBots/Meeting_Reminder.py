import discord
from discord.ext import commands, tasks
import datetime
import pytz
import re
import json
import os 
from pathlib import Path # Import Pathlib for robust path handling

# --- Configuration ---

# Get the directory of the current Python script
# NOTE: If running from an IDE, __file__ might behave unexpectedly. 
# Ensure you run the script from a terminal for the most reliable path.
SCRIPT_DIR = Path(__file__).resolve().parent

# File path for persistent storage, relative to the script's directory
SCHEDULE_FILE = SCRIPT_DIR / 'reminders.json' 

# Global timezone for all reminders 
TIMEZONE_STR = 'Asia/Dhaka' 
BOT_TZ = pytz.timezone(TIMEZONE_STR)

# Initialize the Bot with a command prefix
BOT_PREFIX = "!"
intents = discord.Intents.default()
intents.members = True   
intents.message_content = True 
client = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# --- Reminder Storage ---
REMINDERS_LIST = [] 
REMINDER_INTERVALS = [15, 10, 2, 0] 

# ----------------------------------------------------------------------
# 2. JSON Persistence Functions (Modified Load)
# ----------------------------------------------------------------------

def save_reminders():
    """Saves reminders to the JSON file."""
    serializable_list = []
    for reminder in REMINDERS_LIST:
        temp = reminder.copy()
        
        # Serialization: datetime to string, int keys to string keys
        temp['time'] = temp['time'].isoformat()
        temp['confirmed_users'] = {str(k): v for k, v in temp['confirmed_users'].items()}
        
        # Ensure all IDs are stored as strings for consistency in the JSON
        temp['users'] = [str(uid) for uid in temp['users']]
        temp['channel_id'] = str(temp['channel_id'])
        temp['scheduler_id'] = str(temp['scheduler_id'])
        
        serializable_list.append(temp)
        
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(serializable_list, f, indent=4)


def load_reminders():
    """
    Loads reminders from the JSON file. 
    Returns a list of reminders that expired while the bot was offline.
    """
    global REMINDERS_LIST
    expired_reminders = []
    
    if SCHEDULE_FILE.exists(): 
        with open(SCHEDULE_FILE, 'r') as f:
            try:
                data = json.load(f)
                now = datetime.datetime.now(BOT_TZ).replace(second=0, microsecond=0)
                
                for item in data:
                    # Deserialization of IDs
                    item['users'] = [int(uid) for uid in item['users']]
                    item['channel_id'] = int(item['channel_id'])
                    item['scheduler_id'] = int(item['scheduler_id'])
                    
                    # Deserialization of Time and Confirmed Users
                    time_str = item.pop('time') 
                    meeting_time = datetime.datetime.fromisoformat(time_str).astimezone(BOT_TZ).replace(second=0, microsecond=0)
                    item['time'] = meeting_time
                    
                    confirmed_users_str = item.pop('confirmed_users')
                    confirmed_users_int = {int(k): v for k, v in confirmed_users_str.items()}
                    item['confirmed_users'] = confirmed_users_int
                    
                    # 🌟 NEW LOGIC: Check for expired meetings
                    # We check if the meeting time is within the last minute or in the past.
                    if meeting_time < now:
                        expired_reminders.append(item)
                    else:
                        REMINDERS_LIST.append(item) # Only load active meetings
                    
                print(f"Loaded {len(REMINDERS_LIST)} active reminders.")
                print(f"Found {len(expired_reminders)} expired reminders.")
                
            except json.JSONDecodeError:
                print(f"Error decoding JSON from {SCHEDULE_FILE.name}. File might be empty or corrupted.")
                REMINDERS_LIST = []
    else:
        print(f"No {SCHEDULE_FILE.name} found. Starting with an empty reminder list.")
        
    return expired_reminders


# ----------------------------------------------------------------------
# 3. Discord Events and Tasks (Modified on_ready)
# ----------------------------------------------------------------------

# Background task: check reminders every minute and send notifications
@tasks.loop(minutes=1) 
async def reminder_checker():
    now = datetime.datetime.now(BOT_TZ).replace(second=0, microsecond=0)
    reminders_to_remove = []

    for reminder in REMINDERS_LIST:
        meeting_time = reminder['time']
        # Time remaining in minutes, rounded down
        time_difference = int((meeting_time - now).total_seconds() / 60)
        
        channel = client.get_channel(reminder['channel_id'])
        if not channel:
            continue

        # --- 1. Handle Final Reminder (Time is NOW) ---
        if time_difference == 0:
            reminders_to_remove.append(reminder) 
            
            # Send the final "NOW" message to *everyone*
            mentions = " ".join([f"<@{uid}>" for uid in reminder['users']])
            message = (
                f"⏰ **MEETING TIME IS NOW!** 🔔\n"
                f"{mentions}, your meeting **'{reminder['message']}'** is starting now."
            )
            await channel.send(message)
            continue
            
        # --- 2. Handle 15, 10, 2 Minute Reminders ---
        if time_difference in REMINDER_INTERVALS:
            
            users_to_remind = []
            
            for user_id in reminder['users']:
                
                # Users who confirmed are stored in the dictionary
                is_confirmed = user_id in reminder.get('confirmed_users', {})
                
                if not is_confirmed:
                    # If user has NOT confirmed, they get all 15, 10, and 2 min reminders
                    users_to_remind.append(user_id)
                
                elif time_difference == 2:
                    # If user HAS confirmed, they ONLY get the 2-minute reminder
                    users_to_remind.append(user_id)
            
            
            if users_to_remind:
                mentions = " ".join([f"<@{uid}>" for uid in users_to_remind])
                final_time_msg = f"Meeting starts in **{time_difference} minutes!**"
                
                message = (
                    f"⏰ **MEETING REMINDER!** 📢\n"
                    f"{mentions}, you have a meeting scheduled by {client.get_user(reminder['scheduler_id']).mention}:\n"
                    f"**Topic:** {reminder['message']}\n"
                    f"**Time:** {meeting_time.strftime('%Y-%m-%d %I:%M %p %Z')}\n" # 12hr format in reminder
                    f"{final_time_msg}\n"
                    f"Reply with `!ok` to silence the next reminder."
                )
                await channel.send(message)


    # Clean up finished reminders
    for reminder in reminders_to_remove:
        if reminder in REMINDERS_LIST:
            REMINDERS_LIST.remove(reminder)
            
    if reminders_to_remove:
        print(f"Removed {len(reminders_to_remove)} finished reminders.")



@client.event
async def on_ready():
    # 🌟 NEW: Load data and get list of expired reminders
    expired_reminders = load_reminders()
    
    # 🌟 NEW: Process Expired Reminders
    if expired_reminders:
        await process_expired_reminders(expired_reminders)
        # Save after cleanup to remove expired items from the JSON file
        save_reminders() 
    
    print(f'Bot is ready and logged in as {client.user}')
    print(f'Using Timezone: {TIMEZONE_STR}')
    reminder_checker.start()
    await client.change_presence(activity=discord.Game(name=f'{BOT_PREFIX}schedule | {BOT_PREFIX}ok'))


async def process_expired_reminders(expired_reminders):
    """Sends a message about expired meetings found on startup."""
    
    for reminder in expired_reminders:
        channel = client.get_channel(reminder['channel_id'])
        if channel:
            mentions = " ".join([f"<@{uid}>" for uid in reminder['users']])
            
            # The time the meeting was scheduled for
            meeting_time_str = reminder['time'].strftime('%Y-%m-%d %I:%M %p %Z')
            
            # Message explaining the missed event
            message = (
                f"⚠️ **MISSED MEETING ALERT - Bot Restarted** ⚠️\n"
                f"The meeting **'{reminder['message']}'** scheduled for `{meeting_time_str}` "
                f"was missed while the bot was offline.\n"
                f"**Participants:** {mentions}\n"
                f"This schedule has been automatically removed."
            )
            await channel.send(message)
    
    print(f"Successfully notified channels about {len(expired_reminders)} missed meetings.")


# ----------------------------------------------------------------------
# 4. Command Logic (Modified to include save_reminders())
# ----------------------------------------------------------------------

# --- !SCHEDULE command (ADDED save_reminders) ---
@client.command(name='schedule', help='Schedule a meeting reminder. Format: !schedule "<YYYY-MM-DD HH:MM AM/PM>" or "<HH:M>" or "<HH:MM AM/PM>" <@user1 @user2...> <Meeting Topic>')
async def schedule_meeting(ctx, date_time_str: str, *args):
    scheduler_id = ctx.author.id
    now = datetime.datetime.now(BOT_TZ).replace(second=0, microsecond=0)
    meeting_time = None
    
    # 1. Attempt to Parse Date and Time (Parsing logic remains unchanged)
    try:
        # A. Full format: "YYYY-MM-DD HH:MM AM/PM"
        naive_dt = datetime.datetime.strptime(date_time_str, '%Y-%m-%d %I:%M %p')
        meeting_time = BOT_TZ.localize(naive_dt).replace(second=0, microsecond=0)
        
    except ValueError:
        # B. Smart Time-Only Parsing (HH:M AM/PM or HH:M)
        time_only_match = re.match(r'^(\d{1,2}:\d{1,2})( (AM|PM))?$', date_time_str, re.IGNORECASE)
        
        if time_only_match:
            time_raw = time_only_match.group(1) 
            ampm_part = time_only_match.group(2) 
            
            # --- NORMALIZATION STEP ---
            try:
                hour_str, minute_str = time_raw.split(':')
                if len(minute_str) == 1:
                    minute_str = '0' + minute_str
                time_part = f"{hour_str}:{minute_str}" 
            except ValueError:
                return await ctx.send(f"❌ **Error:** Time format issue encountered during normalization. Please check your time input.")
            # --------------------------
            
            date_today = now.date()
            
            if ampm_part:
                # Case 1: Format: "HH:MM AM/PM" (Explicit AM/PM)
                try:
                    time_with_ampm = time_part + ampm_part 
                    time_obj = datetime.datetime.strptime(time_with_ampm, '%I:%M %p').time()
                    naive_dt = datetime.datetime.combine(date_today, time_obj)
                    meeting_time = BOT_TZ.localize(naive_dt).replace(second=0, microsecond=0)
                    
                    if meeting_time <= now:
                        date_tomorrow = date_today + datetime.timedelta(days=1)
                        naive_dt = datetime.datetime.combine(date_tomorrow, time_obj)
                        meeting_time = BOT_TZ.localize(naive_dt).replace(second=0, microsecond=0)
                        
                except ValueError:
                    pass 

            else:
                # Case 2: Format: "HH:MM" (Naked Time - AM/PM must be guessed)
                try:
                    # 1. Try PM first
                    time_with_pm = time_part + " PM"
                    time_obj_pm = datetime.datetime.strptime(time_with_pm, '%I:%M %p').time()
                    naive_dt_pm = datetime.datetime.combine(date_today, time_obj_pm)
                    meeting_time_pm = BOT_TZ.localize(naive_dt_pm).replace(second=0, microsecond=0)

                    if meeting_time_pm > now:
                        meeting_time = meeting_time_pm
                    else:
                        # 2. If PM is in the past, try AM for tomorrow
                        time_with_am = time_part + " AM"
                        time_obj_am = datetime.datetime.strptime(time_with_am, '%I:%M %p').time()
                        
                        date_tomorrow = date_today + datetime.timedelta(days=1)
                        naive_dt_am = datetime.datetime.combine(date_tomorrow, time_obj_am)
                        meeting_time = BOT_TZ.localize(naive_dt_am).replace(second=0, microsecond=0)

                except ValueError:
                    # Fallback: If 12-hour parsing fails (e.g., input was "13:30"), try 24-hour parsing
                    try:
                        time_obj = datetime.datetime.strptime(time_part, '%H:%M').time()
                        naive_dt = datetime.datetime.combine(date_today, time_obj)
                        meeting_time = BOT_TZ.localize(naive_dt).replace(second=0, microsecond=0)

                        if meeting_time <= now:
                            date_tomorrow = date_today + datetime.timedelta(days=1)
                            naive_dt = datetime.datetime.combine(date_tomorrow, time_obj)
                            meeting_time = BOT_TZ.localize(naive_dt).replace(second=0, microsecond=0)
                    except ValueError:
                        pass 
        
        
    if not meeting_time:
        return await ctx.send(
            f"❌ **Error:** Invalid date/time format. Use `\"YYYY-MM-DD HH:MM AM/PM\"`, `\"HH:MM AM/PM\"`, or just `\"HH:M\"` (e.g., `\"11:2\"` for 11:02 PM/AM, which smartly picks the next occurrence)."
        )

    # 2. Check if the meeting is in the past
    if meeting_time < now + datetime.timedelta(minutes=1):
        return await ctx.send("❌ **Error:** Cannot schedule a meeting in the past or immediately. Please choose a future time.")

    # 3. Separate Mentions from the Message Topic
    mentioned_ids = []
    message_parts = []
    
    for arg in args:
        match = re.match(r'<@!?(\d+)>', arg)
        if match:
            user_id = int(match.group(1))
            if user_id not in mentioned_ids:
                mentioned_ids.append(user_id)
        else:
            message_parts.append(arg)
            
    if scheduler_id not in mentioned_ids:
        mentioned_ids.append(scheduler_id)
        
    meeting_topic = " ".join(message_parts) or "Untitled Meeting"

    if len(mentioned_ids) < 2 and ctx.author.id in mentioned_ids:
        pass 
    elif not mentioned_ids:
        return await ctx.send("❌ **Error:** Please mention at least one other user for the meeting, or include a topic.")

    # 4. Store the new reminder
    new_reminder = {
        'time': meeting_time,
        'users': mentioned_ids,
        'message': meeting_topic,
        'channel_id': ctx.channel.id, 
        'scheduler_id': scheduler_id,
        'confirmed_users': {} # Key: user_id, Value: datetime_confirmed (Not used for JSON here, just the ID is key)
    }
    REMINDERS_LIST.append(new_reminder)
    
    # 🌟 NEW: Save data after successful scheduling
    save_reminders() 
    
    # 5. Confirmation Message
    user_mentions_str = " ".join([f"<@{uid}>" for uid in mentioned_ids])
    
    confirmation_message = (
        f"✅ **Reminder Set!**\n"
        f"**Topic:** {meeting_topic}\n"
        f"**Time:** {meeting_time.strftime('%Y-%m-%d %I:%M %p %Z')}\n"
        f"**Participants:** {user_mentions_str}\n"
        f"Type `!list` to see your active scheduled meetings\n"
        f"Reminders will be sent at 15, 10, and 2 minutes. Use `!ok` to skip 15/10 min reminders."
    )
    await ctx.send(confirmation_message)

# --- !OK Command (ADDED save_reminders) ---
@client.command(name='ok', help='Acknowledges the meeting reminder to silence the next notification.')
async def confirm_meeting(ctx):
    user_id = ctx.author.id
    now = datetime.datetime.now(BOT_TZ)
    
    # 1. Find the NEXT meeting the user is attending and is NOT YET started.
    relevant_reminders = sorted([
        r for r in REMINDERS_LIST 
        if user_id in r['users'] and r['time'] > now
    ], key=lambda r: r['time']) 

    if not relevant_reminders:
        return await ctx.send("ℹ️ You have no active meetings scheduled to confirm.")

    reminder = relevant_reminders[0]
    
    # Check if the user has already confirmed the next reminder
    if user_id in reminder['confirmed_users']:
        return await ctx.send(f"ℹ️ You have already confirmed the next reminder for **'{reminder['message']}'**.")

    # 2. Update the reminder status (Note: The datetime value stored here doesn't matter for persistence, only the key)
    reminder['confirmed_users'][user_id] = now
    
    # 🌟 NEW: Save data after successful confirmation
    save_reminders()
    
    # 3. Determine skip message based on current time
    minutes_until_meeting = int((reminder['time'] - now).total_seconds() / 60)
    
    skip_message = ""
    
    if minutes_until_meeting > 15:
        skip_message = "You will skip the **15-minute and 10-minute** reminders."
    elif minutes_until_meeting > 10:
        skip_message = "You will skip the **10-minute** reminder."
    elif minutes_until_meeting > 2:
        skip_message = "You have confirmed the next reminders. You will only receive the **2-minute** reminder."
    else:
        skip_message = "Only the **'Meeting is NOW'** reminder will be sent to you."


    # 4. Send Confirmation
    await ctx.send(
        f"✅ **Confirmation Received!**\n"
        f"For meeting **'{reminder['message']}'** at `{reminder['time'].strftime('%I:%M %p %Z')}`.\n"
        f"{skip_message}\n"
        f"You will still receive the final **'Meeting is NOW'** reminder."
    )


# --- !LIST command (Unchanged) ---
@client.command(name='list', help='Lists all currently scheduled meeting reminders by you.')
async def list_meetings(ctx):
    user_id = ctx.author.id
    
    user_reminders = [r for r in REMINDERS_LIST if r['scheduler_id'] == user_id]
    
    if not user_reminders:
        return await ctx.send("ℹ️ You have no active meeting reminders scheduled.")

    message = "📅 **Your Active Scheduled Meetings:**\n\n"
    
    for i, reminder in enumerate(user_reminders):
        temp_id = i + 1
        
        attendees = [uid for uid in reminder['users'] if uid != user_id]
        attendee_mentions = " ".join([f"<@{uid}>" for uid in attendees])
        
        confirmed_count = len(reminder.get('confirmed_users', {}))
        status = f" ({confirmed_count}/{len(reminder['users'])} confirmed)"
        
        message += (
            f"**ID:** `{temp_id}` {status}\n"
            f"**Time:** {reminder['time'].strftime('%Y-%m-%d %I:%M %p %Z')}\n" # 12hr format
            f"**Topic:** {reminder['message']}\n"
            f"**Attendees:** {attendee_mentions if attendees else 'Just you'}\n"
            f"---------------------------------\n"
        )
        
    message += f"\nTo cancel a meeting, use: `!cancel <ID>` (e.g., `!cancel 1`) also you can use `!cancel all` or `!cancel .` to cancel all meetings."
    await ctx.send(message)


# --- !CANCEL command (ADDED save_reminders) ---
@client.command(name='cancel', help='Cancels a scheduled meeting. Use !list to find the ID, or use "!cancel all" or "!cancel ." to cancel all your meetings.')
async def cancel_meeting(ctx, meeting_id_or_command: str):
    user_id = ctx.author.id
    
    # Check for 'all' or '.' command
    if meeting_id_or_command.lower() in ['all', '.']:
        
        user_reminders_to_cancel = [r for r in REMINDERS_LIST if r['scheduler_id'] == user_id]
        
        if not user_reminders_to_cancel:
            return await ctx.send("❌ **Cancellation Failed:** You have no active meetings to cancel.")
            
        count = 0
        for reminder in user_reminders_to_cancel:
            try:
                REMINDERS_LIST.remove(reminder)
                count += 1
            except ValueError:
                pass

        if count > 0:
            # 🌟 NEW: Save data after batch cancellation
            save_reminders() 
            await ctx.send(
                f"✅ **Batch Cancellation Complete!**\n"
                f"Successfully cancelled **{count}** active meetings scheduled by you."
            )
        else:
            await ctx.send("❌ **Cancellation Error:** Could not find and remove any of your active meetings.")
        
        return
        
    
    # Handle single meeting cancellation by ID
    try:
        meeting_id = int(meeting_id_or_command)
    except ValueError:
        return await ctx.send(f"❌ **Cancellation Failed:** Invalid input. Use the meeting ID (e.g., `!cancel 1`), or use `!cancel all` / `!cancel .` to cancel everything.")

    user_reminders = [r for r in REMINDERS_LIST if r['scheduler_id'] == user_id]
    
    if not user_reminders:
        return await ctx.send("❌ **Cancellation Failed:** You have no active meetings to cancel.")

    list_index = meeting_id - 1
    
    if not (0 <= list_index < len(user_reminders)):
        return await ctx.send(f"❌ **Cancellation Failed:** Invalid Meeting ID `{meeting_id}`. Use `!list` to see your IDs.")
    
    reminder_to_remove = user_reminders[list_index]
    
    try:
        REMINDERS_LIST.remove(reminder_to_remove)
        
        # 🌟 NEW: Save data after single cancellation
        save_reminders() 
        
        await ctx.send(
            f"✅ **Meeting Cancelled!**\n"
            f"The meeting **'{reminder_to_remove['message']}'** scheduled for "
            f"`{reminder_to_remove['time'].strftime('%Y-%m-%d %I:%M %p %Z')}` has been removed."
        )
    except ValueError:
        await ctx.send("❌ **Cancellation Error:** Could not find the meeting in the active list.")

@client.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        if ctx.command.name == 'schedule':
            await ctx.send(f"❌ **Missing Arguments:** Please use the full format, remember to quote the date and time. Example: `{BOT_PREFIX}schedule \"2025-12-31 02:30 PM\" @user Topic`")
        else:
            await ctx.send(f"❌ **Missing Arguments:** Please use the full format. Type `{BOT_PREFIX}help {ctx.command.name}` for usage.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"An unexpected error occurred: {error}")





# end. Run the Bot
client.run('Your bot token goes here') 
# NOTE: Replace 'Your bot token goes here' with your actual bot token to run it.