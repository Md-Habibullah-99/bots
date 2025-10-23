import discord
import json
import pytz
from datetime import datetime, time, timedelta, timezone

# --- CONFIGURATION & DATA MANAGEMENT ---

# File path to store persistent data
DATA_FILE = 'schedule_data.json'

# 🚨 CHANGE 1: Define the target timezone explicitly (e.g., 'Asia/Dhaka' which is UTC+6)
TARGET_TIMEZONE = pytz.timezone('Asia/Dhaka') 
# Note: If 'Asia/Dhaka' doesn't cover your specific +6 zone, you can use pytz.FixedOffset(360) 
# where 360 is minutes (6 hours * 60 minutes). 'Asia/Dhaka' is more robust.

# Replace with your actual IDs (use strings for dictionary keys)
# Format: "USER_ID": {"schedule": "HH:MM"} (This time is interpreted in TARGET_TIMEZONE)
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
    if total_seconds < 60:
        return f"{total_seconds} seconds"
        
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

# --- Bot Setup ---
intents = discord.Intents.default()
intents.members = True
intents.presences = True 
client = discord.Client(intents=intents)

user_tracker = {}

def load_data():
    """Loads user tracking data from the JSON file."""
    global user_tracker
    try:
        with open(DATA_FILE, 'r') as f:
            user_tracker = json.load(f)
            print("Loaded tracking data.")
    except (FileNotFoundError, json.JSONDecodeError):
        # Initialize the tracker with scheduled users
        for user_id in SCHEDULED_USERS:
             user_tracker[user_id] = {
                'last_reset_day': get_local_now().strftime('%Y-%m-%d'),
                'online_time_timestamp': None,
                'total_time_online': 0,
                'reported_today': False
            }
        print("Initialized new tracking data.")

def save_data():
    """Saves user tracking data to the JSON file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(user_tracker, f, indent=4)

def get_user_data(user_id):
    """Retrieves or initializes user data and checks for daily reset."""
    user_id_str = str(user_id)
    if user_id_str not in SCHEDULED_USERS:
        return None 
    
    if user_id_str not in user_tracker:
         user_tracker[user_id_str] = {
            'last_reset_day': '1970-01-01', # Force reset on first run
            'online_time_timestamp': None,
            'total_time_online': 0,
            'reported_today': False
        }

    # 🚨 CHANGE 2: Check for daily reset using the local target day
    current_day = get_local_now().strftime('%Y-%m-%d')
    if user_tracker[user_id_str]['last_reset_day'] != current_day:
        print(f"Resetting data for user {user_id_str} for new day: {current_day}")
        user_tracker[user_id_str] = {
            'last_reset_day': current_day,
            'online_time_timestamp': None,
            'total_time_online': 0,
            'reported_today': False
        }
        save_data()

    return user_tracker[user_id_str]

# --- Core Bot Events ---

@client.event
async def on_ready():
    """Runs when the bot is connected."""
    print(f'Bot is ready and logged in as {client.user}')
    load_data()

@client.event
async def on_presence_update(old_presence, new_presence):
    """Fires when a member's status, activity, or client changes."""
    user_id_str = str(new_presence.id)

    if user_id_str not in SCHEDULED_USERS:
        return

    user_data = get_user_data(user_id_str)
    if not user_data:
        return 

    old_status = old_presence.status
    new_status = new_presence.status
    
    # Ignore status changes if the user remains online/idle/dnd or remains offline
    is_going_online = new_status == discord.Status.online and old_status not in [discord.Status.online, discord.Status.idle, discord.Status.dnd]
    is_going_offline_or_away = new_status in [discord.Status.offline, discord.Status.idle, discord.Status.dnd] and old_status == discord.Status.online

    if not (is_going_online or is_going_offline_or_away):
        return # Only process transitions that matter for session tracking

    member = new_presence 
    channel = client.get_channel(NOTIFICATION_CHANNEL_ID)

    if not channel:
        print(f"Error: Notification channel (ID: {NOTIFICATION_CHANNEL_ID}) not found.")
        return

    # --- GOING ONLINE LOGIC (First time in a session) ---
    # 🚨 CHANGE 3: Only report ONCE PER DAY (if they haven't been reported) and when they start a new session (online_time_timestamp is None)
    if is_going_online and user_data['online_time_timestamp'] is None:
        
        current_time = get_local_now()
        user_data['online_time_timestamp'] = current_time.timestamp() # Store UTC timestamp
        
        # Check if the "online" message has already been sent for today
        if user_data['reported_today']:
             save_data()
             return # Already reported the summary, don't report online again

        # --- Lateness Calculation ---
        schedule_str = SCHEDULED_USERS[user_id_str]['schedule']
        
        # Combine current day's date with the scheduled time, localized to TARGET_TIMEZONE
        scheduled_time_24hr = datetime.strptime(schedule_str, '%H:%M').time()
        scheduled_datetime = TARGET_TIMEZONE.localize(
            datetime.combine(current_time.date(), scheduled_time_24hr)
        )

        lateness = current_time - scheduled_datetime
        
        # 🚨 CHANGE 4: Use 12-hour format and local time zone name
        tz_abbr = current_time.strftime('%Z')
        formatted_online_time = current_time.strftime(f'%I:%M:%S %p {tz_abbr}')
        message = f"🟢 **ATTENTION!** {member.mention} has just come **ONLINE** at **{formatted_online_time}**."
        
        # Check for lateness
        lateness_seconds = lateness.total_seconds()
        
        if lateness_seconds > 60: # 60 seconds tolerance for late
            formatted_lateness = format_elapsed_time(lateness_seconds)
            message += f"\n⏰ **LATE:** They were **{formatted_lateness}** late for their scheduled time of **{schedule_str} {tz_abbr}**."
        elif lateness_seconds < -60: # 60 seconds tolerance for early
            formatted_earlyness = format_elapsed_time(abs(lateness_seconds))
            message += f"\n✅ **EARLY:** They came **{formatted_earlyness}** early for their scheduled time of **{schedule_str} {tz_abbr}**."
        else:
            message += f"\n✅ **ON TIME:** They were on time for their scheduled time of **{schedule_str} {tz_abbr}**."

        await channel.send(message)
        save_data()


    # --- GOING OFFLINE LOGIC (Session ends) ---
    elif is_going_offline_or_away and user_data['online_time_timestamp'] is not None:
        
        current_time = get_local_now()
        
        # Calculate time spent online in this single session
        time_online_session = current_time.timestamp() - user_data['online_time_timestamp']
        user_data['total_time_online'] += time_online_session
        user_data['online_time_timestamp'] = None # Session ended

        # 🚨 CHANGE 5: Check if we should send the final daily report (ONLY when going fully offline)
        if new_status == discord.Status.offline and not user_data['reported_today']:
            
            formatted_total_time = format_elapsed_time(user_data['total_time_online'])
            
            # Use 12-hour format and local time zone name
            tz_abbr = current_time.strftime('%Z')
            formatted_offline_time = current_time.strftime(f'%I:%M:%S %p {tz_abbr}')

            final_message = f"""
            🛑 **DAILY REPORT FOR {member.mention}** 🛑
            ---
            **Last Status:** Went **OFFLINE** at **{formatted_offline_time}** ({tz_abbr}).
            **Total Time Online Today:** **{formatted_total_time}**.
            """
            
            await channel.send(final_message)
            user_data['reported_today'] = True # Mark as reported for the day
            
        save_data()

# --- Run the Bot ---
client.run('bot id here/token')
