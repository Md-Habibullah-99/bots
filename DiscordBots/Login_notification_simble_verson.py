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

# 🚨 Data structure for SCHEDULED_USERS with daily times
# The 'out' time is NOT used for simple notification, but the structure is maintained.
SCHEDULED_USERS = {
    "121exampleid1": {
        "Saturday": {"in": "10:00", "out": "23:00"}, # 10:00 AM in, 11:00 PM out
        "Sunday": {"in": "13:00", "out": "21:00"},  # 1:00 PM in, 9:00 PM out
        "default": {"in": "09:00", "out": "18:00"}  # Default for other days
    },
    "121exampleid2": {
        "Monday": {"in": "09:30", "out": "17:30"},
        "default": {"in": "10:00", "out": "19:00"}
    },
    "121exampleid3": {
        "default": {"in": "08:00", "out": "17:00"}
    }

}

NOTIFICATION_CHANNEL_ID = channel_id_here # Replace with your channel ID

# --- Utility Functions ---

def get_local_now():
    """Returns the current datetime object localized to the TARGET_TIMEZONE."""
    return datetime.now(TARGET_TIMEZONE)

def get_schedule_for_user(user_id):
    """Retrieves the specific in/out schedule for a user based on the current day."""
    user_id_str = str(user_id)
    if user_id_str not in SCHEDULED_USERS:
        return None
    
    current_day_name = get_local_now().strftime('%A') # e.g., 'Saturday', 'Monday'
    user_schedule = SCHEDULED_USERS[user_id_str]
    
    # Prioritize specific day, fall back to default
    if current_day_name in user_schedule:
        return user_schedule[current_day_name]
    elif 'default' in user_schedule:
        return user_schedule['default']
    
    return None

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
        # Handle small time differences (less than a minute) which are considered 'on time'
        return "less than a minute"

# --- Bot Setup and Data Handlers ---

intents = discord.Intents.default()
intents.members = True
intents.presences = True 
client = discord.Client(intents=intents)

# Simplified tracker structure: {'last_reset_day': 'YYYY-MM-DD', 'online_message_sent': True/False}
user_tracker = {}

def save_data():
    """Saves the tracking data to the JSON file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(user_tracker, f, indent=4)

def reset_user_data(user_id_str):
    """Resets the tracking flag for a user for the new day."""
    current_day = get_local_now().strftime('%Y-%m-%d')
    user_tracker[user_id_str] = {
        'last_reset_day': current_day,
        'online_message_sent': False 
    }

def load_data():
    """Loads data and performs daily resets for all tracked users."""
    global user_tracker
    try:
        with open(DATA_FILE, 'r') as f:
            user_tracker = json.load(f)
            print("Loaded tracking data.")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    current_day = get_local_now().strftime('%Y-%m-%d')
    for user_id in SCHEDULED_USERS:
        user_id_str = str(user_id)
        # Reset if user not tracked yet OR if the stored day is not the current day
        if user_id_str not in user_tracker or user_tracker[user_id_str]['last_reset_day'] != current_day:
            print(f"Initializing/Resetting data for user {user_id_str}")
            reset_user_data(user_id_str)
            
    save_data()
    return user_tracker

# --- Core Bot Events ---

@client.event
async def on_ready():
    print(f'Bot is ready and logged in as {client.user}')
    load_data()


@client.event
async def on_presence_update(old_presence, new_presence):
    user_id_str = str(new_presence.id)

    # 1. Check if the user is in our monitored list
    if user_id_str not in SCHEDULED_USERS:
        return

    # 2. Daily reset check
    user_data = user_tracker.get(user_id_str)
    if not user_data or user_data['last_reset_day'] != get_local_now().strftime('%Y-%m-%d'):
        load_data()
        user_data = user_tracker.get(user_id_str)
        if not user_data: return

    old_status = old_presence.status
    new_status = new_presence.status
    
    # Trigger if user transitions to an active state
    is_going_online = new_status in [discord.Status.online, discord.Status.idle, discord.Status.dnd] and \
                      old_status not in [discord.Status.online, discord.Status.idle, discord.Status.dnd]

    if not is_going_online:
        return

    # 3. Check if the notification has already been sent today
    if user_data['online_message_sent']:
        return # Notification already sent for this user today

    member = new_presence
    channel = client.get_channel(NOTIFICATION_CHANNEL_ID)

    if not channel:
        print(f"Error: Notification channel (ID: {NOTIFICATION_CHANNEL_ID}) not found.")
        return
    
    # 🚨 CORE CHANGE: Get the day-specific schedule and calculate status (on time/late/early)
    current_schedule = get_schedule_for_user(user_id_str)
    if not current_schedule or not current_schedule.get('in'):
        # If no 'in' time is defined, we can't check lateness, but still track the first online event
        scheduled_in_time_str = "N/A"
        lateness_message = "⚠️ **NO SCHEDULE:** Could not determine scheduled IN time."
    else:
        scheduled_in_time_str = current_schedule['in']
        current_time = get_local_now()
        
        try:
            scheduled_time_24hr = datetime.strptime(scheduled_in_time_str, '%H:%M').time()
            scheduled_datetime = TARGET_TIMEZONE.localize(
                datetime.combine(current_time.date(), scheduled_time_24hr)
            )

            lateness = current_time - scheduled_datetime
            lateness_seconds = lateness.total_seconds()
            tz_abbr = current_time.strftime('%Z')

            if lateness_seconds > 60:
                # LATE: After scheduled time by more than 60 seconds
                formatted_lateness = format_elapsed_time(lateness_seconds)
                lateness_message = f"⏰ **LATE:** They were **{formatted_lateness}** late for their scheduled **IN** time of **{scheduled_in_time_str} {tz_abbr}**."
            elif lateness_seconds < -60:
                # EARLY: Before scheduled time by more than 60 seconds
                formatted_earlyness = format_elapsed_time(abs(lateness_seconds))
                lateness_message = f"⚠️ **EARLY:** They came **{formatted_earlyness}** early for their scheduled **IN** time of **{scheduled_in_time_str} {tz_abbr}**."
            else:
                # ON TIME: Within +/- 60 seconds
                lateness_message = f"✅ **ON TIME:** They were on time for their scheduled **IN** time of **{scheduled_in_time_str} {tz_abbr}**."
                
        except ValueError:
            lateness_message = f"⚠️ **SCHEDULE ERROR:** Scheduled time '{scheduled_in_time_str}' is invalid."


    # 4. Send the notification
    current_time = get_local_now()
    tz_abbr = current_time.strftime('%Z')
    formatted_online_time = current_time.strftime(f'%I:%M:%S %p {tz_abbr}')
    
    message = f"""
🟢 **ATTENTION!** {member.mention} has just come **ONLINE** at **{formatted_online_time}**.
---
{lateness_message}
"""
    
    await channel.send(message)
    
    # 5. Mark the notification as sent and save
    user_data['online_message_sent'] = True
    save_data()

# --- Run the Bot ---
client.run('bot id here/token')
