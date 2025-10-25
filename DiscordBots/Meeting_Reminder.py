import discord
from discord.ext import commands, tasks
import datetime
import pytz
import re 

# --- Configuration ---

# 1. Set Intents
intents = discord.Intents.default()
intents.members = True   
intents.message_content = True 

# Initialize the Bot with a command prefix
BOT_PREFIX = "!"
client = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# --- Reminder Storage ---
REMINDERS_LIST = [] 

# Global timezone for all reminders 
TIMEZONE_STR = 'Asia/Dhaka' 
BOT_TZ = pytz.timezone(TIMEZONE_STR)
# Updated reminder times in minutes before the meeting
REMINDER_INTERVALS = [15, 10, 2, 0] 

# ----------------------------------------------------------------------
# 2. Discord Events and Tasks
# ----------------------------------------------------------------------

@client.event
async def on_ready():
    print(f'Bot is ready and logged in as {client.user}')
    print(f'Using Timezone: {TIMEZONE_STR}')
    reminder_checker.start()
    # Updated help message to reflect 12hr time format
    await client.change_presence(activity=discord.Game(name=f'{BOT_PREFIX}schedule | {BOT_PREFIX}ok'))

# --- Scheduled Reminder Checker ---

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

# ----------------------------------------------------------------------
# 3. Command Logic (UPDATED: !SCHEDULE for smart time parsing)
# ----------------------------------------------------------------------

# --- !SCHEDULE command (MODIFIED: Date/Time parsing) ---
@client.command(name='schedule', help='Schedule a meeting reminder. Format: !schedule "<YYYY-MM-DD HH:MM AM/PM>" or "<HH:MM>" or "<HH:MM AM/PM>" <@user1 @user2...> <Meeting Topic>')
async def schedule_meeting(ctx, date_time_str: str, *args):
    scheduler_id = ctx.author.id
    # Current time: 2025-10-25 11:20:xx AM +06
    now = datetime.datetime.now(BOT_TZ).replace(second=0, microsecond=0)
    meeting_time = None
    
    # 1. Attempt to Parse Date and Time
    try:
        # A. Full format: "YYYY-MM-DD HH:MM AM/PM"
        naive_dt = datetime.datetime.strptime(date_time_str, '%Y-%m-%d %I:%M %p')
        meeting_time = BOT_TZ.localize(naive_dt).replace(second=0, microsecond=0)
        
    except ValueError:
        # B. Smart Time-Only Parsing (HH:MM AM/PM or HH:MM)
        
        # Regex to check if it's a time-only format: HH:MM or HH:MM AM/PM
        # group(1) = HH:MM, group(2) = ( AM| PM), group(3) = AM|PM
        time_only_match = re.match(r'^(\d{1,2}:\d{2})( (AM|PM))?$', date_time_str, re.IGNORECASE)
        
        if time_only_match:
            time_part = time_only_match.group(1) # e.g., "10:30" or "02:00"
            ampm_part = time_only_match.group(2) # e.g., " AM" or " PM" or None
            
            date_today = now.date()
            
            if ampm_part:
                # Case 1: Format: "HH:MM AM/PM" (Explicit AM/PM)
                try:
                    time_obj = datetime.datetime.strptime(date_time_str, '%I:%M %p').time()
                    naive_dt = datetime.datetime.combine(date_today, time_obj)
                    meeting_time = BOT_TZ.localize(naive_dt).replace(second=0, microsecond=0)
                    
                    # If the localized time is in the past, push it to tomorrow
                    if meeting_time <= now:
                        date_tomorrow = date_today + datetime.timedelta(days=1)
                        naive_dt = datetime.datetime.combine(date_tomorrow, time_obj)
                        meeting_time = BOT_TZ.localize(naive_dt).replace(second=0, microsecond=0)
                        
                except ValueError:
                    pass # Continue to final error check

            else:
                # Case 2: Format: "HH:MM" (Naked Time - AM/PM must be guessed)
                try:
                    # Attempt to parse as a 12-hour time for the PM occurrence today
                    
                    # 1. Try PM first (most common for naked scheduling during the day)
                    # We combine the time string with " PM" and try to parse
                    time_with_pm = time_part + " PM"
                    time_obj_pm = datetime.datetime.strptime(time_with_pm, '%I:%M %p').time()
                    naive_dt_pm = datetime.datetime.combine(date_today, time_obj_pm)
                    meeting_time_pm = BOT_TZ.localize(naive_dt_pm).replace(second=0, microsecond=0)

                    if meeting_time_pm > now:
                        # Success! The PM time is in the future. (e.g., now 11:20 AM, user enters 1:30 -> 1:30 PM today)
                        meeting_time = meeting_time_pm
                    else:
                        # 2. If PM is in the past, try AM for tomorrow
                        # (e.g., now 1:35 PM, user enters 1:30 -> 1:30 PM is past, so next 1:30 is 1:30 AM tomorrow)
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
                            # If in the past, push to tomorrow
                            date_tomorrow = date_today + datetime.timedelta(days=1)
                            naive_dt = datetime.datetime.combine(date_tomorrow, time_obj)
                            meeting_time = BOT_TZ.localize(naive_dt).replace(second=0, microsecond=0)
                    except ValueError:
                        pass # Continue to final error check
        
        
    if not meeting_time:
        # If any parsing attempt failed, send a generic error
        return await ctx.send(
            f"❌ **Error:** Invalid date/time format. Use `\"YYYY-MM-DD HH:MM AM/PM\"`, `\"HH:MM AM/PM\"`, or just `\"HH:MM\"` (which smartly picks the next occurrence)."
        )

    # 2. Check if the meeting is in the past
    if meeting_time < now + datetime.timedelta(minutes=1):
        return await ctx.send("❌ **Error:** Cannot schedule a meeting in the past or immediately. Please choose a future time.")

    # 3. Separate Mentions from the Message Topic (Unchanged)
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
        'confirmed_users': {} # Key: user_id, Value: datetime_confirmed
    }
    REMINDERS_LIST.append(new_reminder)
    
    # 5. Confirmation Message (Updated to show 12hr time)
    user_mentions_str = " ".join([f"<@{uid}>" for uid in mentioned_ids])
    
    confirmation_message = (
        f"✅ **Reminder Set!**\n"
        f"**Topic:** {meeting_topic}\n"
        f"**Time:** {meeting_time.strftime('%Y-%m-%d %I:%M %p %Z')}\n"
        f"**Participants:** {user_mentions_str}\n"
        f"Reminders will be sent at 15, 10, and 2 minutes. Use `!ok` to skip 15/10 min reminders."
    )
    await ctx.send(confirmation_message)

# --- !OK Command (MODIFIED: Simplified logic for 2-minute jump) ---
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

    # 2. Update the reminder status
    reminder['confirmed_users'][user_id] = now
    
    # 3. Determine skip message based on current time
    minutes_until_meeting = int((reminder['time'] - now).total_seconds() / 60)
    
    skip_message = ""
    
    if minutes_until_meeting > 15:
        # Confirmed before 15 min reminder. Skip 15 & 10.
        skip_message = "You will skip the **15-minute and 10-minute** reminders."
    elif minutes_until_meeting > 10:
        # Confirmed after 15 min, before 10 min. Skip 10.
        skip_message = "You will skip the **10-minute** reminder."
    elif minutes_until_meeting > 2:
        # Confirmed after 10 min, before 2 min. Skip none of the current intervals, but confirm.
        skip_message = "You have confirmed the next reminders. You will only receive the **2-minute** reminder."
    else:
        # Confirmed between 2 min and NOW. Only the "NOW" reminder remains.
        skip_message = "Only the **'Meeting is NOW'** reminder will be sent to you."


    # 4. Send Confirmation
    await ctx.send(
        f"✅ **Confirmation Received!**\n"
        f"For meeting **'{reminder['message']}'** at `{reminder['time'].strftime('%I:%M %p %Z')}`.\n"
        f"{skip_message}\n"
        f"You will still receive the final **'Meeting is NOW'** reminder."
    )


# --- !LIST command (Unchanged, time format updated) ---
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
        
    message += f"\nTo cancel a meeting, use: `!cancel <ID>` (e.g., `!cancel 1`)"
    await ctx.send(message)


# --- !CANCEL command (Unchanged) ---
@client.command(name='cancel', help='Cancels a scheduled meeting. Use !list to find the ID.')
async def cancel_meeting(ctx, meeting_id: int):
    user_id = ctx.author.id
    
    user_reminders = [r for r in REMINDERS_LIST if r['scheduler_id'] == user_id]
    
    if not user_reminders:
        return await ctx.send("❌ **Cancellation Failed:** You have no active meetings to cancel.")

    list_index = meeting_id - 1
    
    if not (0 <= list_index < len(user_reminders)):
        return await ctx.send(f"❌ **Cancellation Failed:** Invalid Meeting ID `{meeting_id}`. Use `!list` to see your IDs.")
    
    reminder_to_remove = user_reminders[list_index]
    
    try:
        REMINDERS_LIST.remove(reminder_to_remove)
        
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




# 4. Run the Bot
client.run('Your bot token goes here')
