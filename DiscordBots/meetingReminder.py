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
# Added 'confirmed_users' list to track who sent !ok
REMINDERS_LIST = [] 

# Global timezone for all reminders 
TIMEZONE_STR = 'Asia/Dhaka' 
BOT_TZ = pytz.timezone(TIMEZONE_STR)
REMINDER_INTERVALS = [15, 10, 5, 0] # Reminder times in minutes before the meeting

# ----------------------------------------------------------------------
# 2. Discord Events and Tasks
# ----------------------------------------------------------------------

@client.event
async def on_ready():
    print(f'Bot is ready and logged in as {client.user}')
    print(f'Using Timezone: {TIMEZONE_STR}')
    reminder_checker.start()
    await client.change_presence(activity=discord.Game(name=f'{BOT_PREFIX}schedule | {BOT_PREFIX}ok'))

# --- Scheduled Reminder Checker ---

@tasks.loop(minutes=1) 
async def reminder_checker():
    # Get current time, rounded down to the minute
    now = datetime.datetime.now(BOT_TZ).replace(second=0, microsecond=0)
    
    reminders_to_remove = []

    for reminder in REMINDERS_LIST:
        meeting_time = reminder['time']
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
            
        # --- 2. Handle 15, 10, 5 Minute Reminders ---
        if time_difference in REMINDER_INTERVALS:
            
            # Identify users who have NOT confirmed and should receive this reminder
            unconfirmed_users = [
                uid for uid in reminder['users'] 
                if uid not in reminder.get('confirmed_users', [])
            ]
            
            # If a user confirmed at 15 minutes, they should skip 10 minutes, but receive 5 minutes.
            # This logic must check the time the user sent !ok vs. the current reminder time.
            
            # Check the confirmed time for each user
            users_to_remind = []
            
            for user_id in reminder['users']:
                
                # If they never confirmed, send the message
                if user_id not in reminder.get('confirmed_users', {}):
                    users_to_remind.append(user_id)
                    continue
                
                # Check when they confirmed
                confirmed_time = reminder['confirmed_users'][user_id]
                
                # Logic:
                # - If time is 15 or 10 min, AND they confirmed before 15 min, skip them.
                # - If time is 5 min, AND they confirmed after the 15 min check (i.e., at 14-6 min), skip them.
                
                if time_difference == 15:
                    users_to_remind.append(user_id) # 15 min reminder always goes out first
                
                elif time_difference == 10:
                    # User confirms BEFORE 15 min (e.g., at 16 min) -> skip 15 & 10, receive 5.
                    if confirmed_time > meeting_time - datetime.timedelta(minutes=15):
                         users_to_remind.append(user_id) # Did NOT confirm early enough
                    # else: skip (confirmed early)
                    
                elif time_difference == 5:
                    # User confirms AFTER 15 min notification (e.g., at 14 min) -> skip 10 & 5.
                    if confirmed_time < meeting_time - datetime.timedelta(minutes=15):
                        users_to_remind.append(user_id) # Confirmed too early (skip 15 & 10, receive 5)
                    # else: skip (confirmed late enough to skip 5 min)
                    
            
            if users_to_remind:
                mentions = " ".join([f"<@{uid}>" for uid in users_to_remind])
                final_time_msg = f"Meeting starts in **{time_difference} minutes!**"
                
                message = (
                    f"⏰ **MEETING REMINDER!** 📢\n"
                    f"{mentions}, you have a meeting scheduled by {client.get_user(reminder['scheduler_id']).mention}:\n"
                    f"**Topic:** {reminder['message']}\n"
                    f"**Time:** {meeting_time.strftime('%Y-%m-%d %H:%M %Z')}\n"
                    f"{final_time_msg}\n"
                    f"Reply with `!ok` to silence this meeting's next reminder."
                )
                await channel.send(message)


    # Clean up finished reminders
    for reminder in reminders_to_remove:
        if reminder in REMINDERS_LIST:
            REMINDERS_LIST.remove(reminder)
            
    if reminders_to_remove:
        print(f"Removed {len(reminders_to_remove)} finished reminders.")

# ----------------------------------------------------------------------
# 3. Command Logic
# ----------------------------------------------------------------------

# --- !SCHEDULE command (Modified to initialize confirmed_users) ---
@client.command(name='schedule', help='Schedule a meeting reminder. Format: !schedule "<YYYY-MM-DD HH:MM>" <@user1 @user2...> <Meeting Topic>')
async def schedule_meeting(ctx, date_time_str: str, *args):
    scheduler_id = ctx.author.id
    
    # ... (Date/Time parsing and validation logic is unchanged)
    try:
        naive_dt = datetime.datetime.strptime(date_time_str, '%Y-%m-%d %H:%M')
        meeting_time = BOT_TZ.localize(naive_dt).replace(second=0, microsecond=0)
    except ValueError:
        return await ctx.send(f"❌ **Error:** Invalid date/time format. Use `\"YYYY-MM-DD HH:MM\"`. Example: `{BOT_PREFIX}schedule \"2025-12-31 14:30\" @user Team Sync`")

    now = datetime.datetime.now(BOT_TZ).replace(second=0, microsecond=0)
    if meeting_time < now + datetime.timedelta(minutes=1):
        return await ctx.send("❌ **Error:** Cannot schedule a meeting in the past or immediately. Please choose a future time.")

    # ... (Mention parsing logic is unchanged)
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

    # 4. Store the new reminder (MODIFIED: added confirmed_users dictionary)
    new_reminder = {
        'time': meeting_time,
        'users': mentioned_ids,
        'message': meeting_topic,
        'channel_id': ctx.channel.id, 
        'scheduler_id': scheduler_id,
        'confirmed_users': {} # Key: user_id, Value: datetime_confirmed
    }
    REMINDERS_LIST.append(new_reminder)
    
    # ... (Confirmation message logic is unchanged)
    user_mentions_str = " ".join([f"<@{uid}>" for uid in mentioned_ids])
    
    confirmation_message = (
        f"✅ **Reminder Set!**\n"
        f"**Topic:** {meeting_topic}\n"
        f"**Time:** {meeting_time.strftime('%Y-%m-%d %H:%M %Z')}\n"
        f"**Participants:** {user_mentions_str}\n"
        f"Reminders will be sent at 15, 10, and 5 minutes. Use `!ok` to silence the next reminder."
    )
    await ctx.send(confirmation_message)

# --- NEW !OK Command ---
@client.command(name='ok', help='Acknowledges the meeting reminder to silence the next notification.')
async def confirm_meeting(ctx):
    user_id = ctx.author.id
    now = datetime.datetime.now(BOT_TZ)
    
    # 1. Find the MOST RECENT meeting that the user is attending and is NOT YET started.
    relevant_reminders = sorted([
        r for r in REMINDERS_LIST 
        if user_id in r['users'] and r['time'] > now
    ], key=lambda r: r['time']) # Sort by earliest meeting first

    if not relevant_reminders:
        return await ctx.send("ℹ️ You have no active meetings scheduled to confirm.")

    # Use the next meeting (the first one in the sorted list)
    reminder = relevant_reminders[0]
    
    # Check if the user has already confirmed the next reminder
    if user_id in reminder['confirmed_users']:
        return await ctx.send(f"ℹ️ You have already confirmed the next reminder for **'{reminder['message']}'**.")

    # 2. Update the reminder status
    reminder['confirmed_users'][user_id] = now
    
    # 3. Determine which reminder(s) will be skipped
    
    meeting_time = reminder['time']
    minutes_until_meeting = int((meeting_time - now).total_seconds() / 60)
    
    skip_message = ""
    
    # Logic to confirm skipped reminders based on minutes_until_meeting:
    if minutes_until_meeting > 15:
        # User confirmed very early (e.g., 20 min before). Skip 15 & 10, receive 5.
        skip_message = "You will skip the **15-minute and 10-minute** reminders."
    elif minutes_until_meeting > 10:
        # User confirmed between 15 and 10 min (e.g., 12 min before). Skip 10, receive 5.
        skip_message = "You will skip the **10-minute** reminder."
    elif minutes_until_meeting > 5:
        # User confirmed between 10 and 5 min (e.g., 7 min before). Skip 5.
        skip_message = "You will skip the **5-minute** reminder."
    else:
        # User confirmed less than 5 min before. Only the "NOW" reminder remains.
        skip_message = "Only the **'Meeting is NOW'** reminder will be sent to you."


    # 4. Send Confirmation
    await ctx.send(
        f"✅ **Confirmation Received!**\n"
        f"For meeting **'{reminder['message']}'** at `{meeting_time.strftime('%H:%M %Z')}`.\n"
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
        
        # Get the list of attendees 
        attendees = [uid for uid in reminder['users'] if uid != user_id]
        attendee_mentions = " ".join([f"<@{uid}>" for uid in attendees])
        
        # Add confirmation status
        confirmed_count = len(reminder.get('confirmed_users', {}))
        status = f" ({confirmed_count}/{len(reminder['users'])} confirmed)"
        
        message += (
            f"**ID:** `{temp_id}` {status}\n"
            f"**Time:** {reminder['time'].strftime('%Y-%m-%d %H:%M %Z')}\n"
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
            f"`{reminder_to_remove['time'].strftime('%Y-%m-%d %H:%M %Z')}` has been removed."
        )
    except ValueError:
        await ctx.send("❌ **Cancellation Error:** Could not find the meeting in the active list.")

@client.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        if ctx.command.name == 'schedule':
            await ctx.send(f"❌ **Missing Arguments:** Please use the full format, remember to quote the date and time. Example: `{BOT_PREFIX}schedule \"2025-12-31 14:30\" @user Topic`")
        else:
            await ctx.send(f"❌ **Missing Arguments:** Please use the full format. Type `{BOT_PREFIX}help {ctx.command.name}` for usage.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"An unexpected error occurred: {error}")
# 4. Run the Bot
client.run('Your bot token goes here')
