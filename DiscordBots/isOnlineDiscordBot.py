import discord
import json
import pytz
import asyncio
from datetime import datetime, time, timedelta

# --- CONFIGURATION & DATA MANAGEMENT ---

# File path to store persistent data
DATA_FILE = 'schedule_data.json'

# 🚨 TARGET TIMEZONE: Asia/Dhaka is UTC+6
TARGET_TIMEZONE = pytz.timezone('Asia/Dhaka') 

# Format: "USER_ID": {"schedule": "HH:MM"} 
SCHEDULED_USERS = {
    "121exampleid1": {"schedule": "10:00"}, # 10:00 AM in UTC+6
    "212exampleid2": {"schedule": "11:30"}, 
    "111exampleid3": {"schedule": "09:00"}
}

NOTIFICATION_CHANNEL_ID = channel_id_here # Replace with your channel ID

# --- Utility Functions ---

def get_local_now():
    """Returns the current datetime object localized to the TARGET_TIMEZONE."""
    return datetime.now(TARGET_TIMEZONE)

def format_elapsed_time(total_seconds):
    """
    Converts total seconds into a human-readable string (e.g., "1 hour and 15 minutes").
    """
    total_seconds = int(total_seconds)
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    elif len(parts) == 1:
        return parts[0]
    else:
        return "less than a minute"

# --- Bot Setup and Data Handlers ---

intents = discord.Intents.default()
intents.members = True
intents.presences = True 
client = discord.Client(intents=intents)

user_tracker = {} # Global dictionary

def save_data():
    """Saves user tracking data to the JSON file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(user_tracker, f, indent=4)

def reset_user_data(user_id_str):
    """Resets all daily tracking data for a new day."""
    current_day = get_local_now().strftime('%Y-%m-%d')
    user_tracker[user_id_str] = {
        'last_reset_day': current_day,
        'online_time_timestamp': None,        # Tracks current *session* start
        'first_online_timestamp': None,       # Tracks *daily* first online
        'last_offline_timestamp': None,       # Tracks *daily* last offline
        'total_time_online': 0,               # Accumulates total session time
        'online_message_sent': False          # Flag for single online alert
    }

def load_data():
    """Loads user tracking data and performs daily reset check."""
    global user_tracker
    try:
        with open(DATA_FILE, 'r') as f:
            user_tracker = json.load(f)
            print("Loaded tracking data.")
    except (FileNotFoundError, json.JSONDecodeError):
        pass # Will be initialized below

    # Initialize or check for daily reset for all scheduled users
    current_day = get_local_now().strftime('%Y-%m-%d')
    for user_id in SCHEDULED_USERS:
        user_id_str = str(user_id)
        if user_id_str not in user_tracker or user_tracker[user_id_str]['last_reset_day'] != current_day:
            print(f"Initializing/Resetting data for user {user_id_str}")
            reset_user_data(user_id_str)
            
    save_data() # Save initialization/reset data
    return user_tracker

# --- Background Task for Midnight Report ---

async def midnight_reporter():
    """Handles sleeping until 12:00 AM and then sends the daily report."""
    await client.wait_until_ready()
    channel = client.get_channel(NOTIFICATION_CHANNEL_ID)
    
    if not channel:
        print(f"Error: Notification channel (ID: {NOTIFICATION_CHANNEL_ID}) not found. Midnight reports disabled.")
        return

    while not client.is_closed():
        now = get_local_now()
        # Set the target time to today at 12:00 AM
        tomorrow = now.date() + timedelta(days=1)
        target_time = TARGET_TIMEZONE.localize(datetime.combine(tomorrow, time(0, 0, 0)))

        # If we are already past midnight (shouldn't happen often, but safety)
        if now > target_time:
            target_time += timedelta(days=1)

        # Calculate sleep duration
        sleep_seconds = (target_time - now).total_seconds()
        
        print(f"Midnight Reporter: Sleeping for {sleep_seconds/3600:.2f} hours until {target_time.strftime('%I:%M:%S %p %Z')}")
        await asyncio.sleep(sleep_seconds)

        # --- Report Generation Logic (Fires exactly at 12:00 AM Local Time) ---
        print("Midnight Reporter: Triggered. Generating reports.")
        
        for user_id_str, user_data in user_tracker.items():
            
            # Check if user activity was logged today (i.e., they went online at least once)
            if user_data['first_online_timestamp'] is None:
                continue

            first_online = datetime.fromtimestamp(user_data['first_online_timestamp'], tz=TARGET_TIMEZONE)
            last_offline = datetime.fromtimestamp(user_data['last_offline_timestamp'], tz=TARGET_TIMEZONE)
            
            # Calculate duration between first online and last offline
            total_duration_raw = last_offline - first_online
            formatted_duration = format_elapsed_time(total_duration_raw.total_seconds())
            
            # Get member to use mention in report
            member = client.get_user(int(user_id_str))
            
            if member:
                message = f"""
                🌙 **MIDNIGHT ATTENDANCE REPORT for {member.mention}** 🌙
                ---
                **First Online:** {first_online.strftime('%I:%M:%S %p %Z')}
                **Last Offline:** {last_offline.strftime('%I:%M:%S %p %Z')}
                **Total Time Elapsed (First to Last):** **{formatted_duration}**
                
                *Note: This is the duration between the start and end of their window, not the accumulated activity time.*
                """
                await channel.send(message)

            # Reset data for the start of the new day
            reset_user_data(user_id_str)

        save_data()
        await asyncio.sleep(1) # Sleep briefly to avoid immediate re-trigger if execution took time

# --- Core Bot Events ---

@client.event
async def on_ready():
    """Runs when the bot is connected."""
    print(f'Bot is ready and logged in as {client.user}')
    load_data()
    # Start the midnight reporting task
    client.loop.create_task(midnight_reporter())


@client.event
async def on_presence_update(old_presence, new_presence):
    """Fires when a member's status changes. Only handles lateness/online message and data logging."""
    user_id_str = str(new_presence.id)

    if user_id_str not in SCHEDULED_USERS:
        return

    # Ensure data is loaded/reset for the current day
    user_data = user_tracker.get(user_id_str)
    if not user_data:
        # If tracker is empty (e.g., bot started without load_data finishing), ensure load/reset happens.
        load_data()
        user_data = user_tracker.get(user_id_str)
        if not user_data: return # If still not found, exit.


    old_status = old_presence.status
    new_status = new_presence.status
    
    is_going_online = new_status == discord.Status.online and old_status not in [discord.Status.online, discord.Status.idle, discord.Status.dnd]
    is_going_offline_or_away = new_status in [discord.Status.offline, discord.Status.idle, discord.Status.dnd] and old_status == discord.Status.online

    if not (is_going_online or is_going_offline_or_away):
        return

    member = new_presence 
    channel = client.get_channel(NOTIFICATION_CHANNEL_ID)

    if not channel:
        return

    # --- GOING ONLINE LOGIC (Start session / Record first online time) ---
    if is_going_online:
        
        current_time = get_local_now()
        
        # 1. Start the current session timestamp
        user_data['online_time_timestamp'] = current_time.timestamp() 
        
        # 2. Record the first online time of the day
        if user_data['first_online_timestamp'] is None:
            user_data['first_online_timestamp'] = current_time.timestamp()

        # 3. Report Lateness (only once per day)
        if not user_data['online_message_sent']:
            
            schedule_str = SCHEDULED_USERS[user_id_str]['schedule']
            scheduled_time_24hr = datetime.strptime(schedule_str, '%H:%M').time()
            scheduled_datetime = TARGET_TIMEZONE.localize(
                datetime.combine(current_time.date(), scheduled_time_24hr)
            )

            lateness = current_time - scheduled_datetime
            tz_abbr = current_time.strftime('%Z')
            formatted_online_time = current_time.strftime(f'%I:%M:%S %p {tz_abbr}')
            message = f"🟢 **ATTENTION!** {member.mention} has just come **ONLINE** at **{formatted_online_time}**."
            
            lateness_seconds = lateness.total_seconds()
            
            if lateness_seconds > 60: 
                formatted_lateness = format_elapsed_time(lateness_seconds)
                message += f"\n⏰ **LATE:** They were **{formatted_lateness}** late for their scheduled time of **{schedule_str} {tz_abbr}**."
            elif lateness_seconds < -60: 
                formatted_earlyness = format_elapsed_time(abs(lateness_seconds))
                message += f"\n✅ **EARLY:** They came **{formatted_earlyness}** early for their scheduled time of **{schedule_str} {tz_abbr}**."
            else:
                message += f"\n✅ **ON TIME:** They were on time for their scheduled time of **{schedule_str} {tz_abbr}**."

            await channel.send(message)
            user_data['online_message_sent'] = True
        
        save_data()


    # --- GOING OFFLINE LOGIC (End session / Record last offline time) ---
    elif is_going_offline_or_away and user_data['online_time_timestamp'] is not None:
        
        current_time = get_local_now()
        
        # 1. Accumulate session time (in case we want this for detailed reports later)
        time_online_session = current_time.timestamp() - user_data['online_time_timestamp']
        user_data['total_time_online'] += time_online_session
        
        # 2. Clear session timestamp
        user_data['online_time_timestamp'] = None
        
        # 3. Record the last offline time (this will be used in the midnight report)
        user_data['last_offline_timestamp'] = current_time.timestamp() 
        
        # NO REPORT SENT HERE, it's saved for the midnight task.
        save_data()

# --- Run the Bot ---
client.run('bot id here/token')
