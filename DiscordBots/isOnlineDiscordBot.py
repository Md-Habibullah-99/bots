import discord
import json
from datetime import datetime, time, timedelta, timezone

# --- CONFIGURATION & DATA MANAGEMENT ---

# File path to store persistent data
DATA_FILE = 'schedule_data.json'

# Replace with your actual IDs (use strings for dictionary keys)
# Format: "USER_ID": {"schedule": "HH:MM"} (24-hour time for internal calculation)
SCHEDULED_USERS = {
    "121exampleid1": {"schedule": "10:00"},
    "212exampleid2": {"schedule": "11:30"},
    "111exampleid3": {"schedule": "09:00"}
}

NOTIFICATION_CHANNEL_ID = channel_id_here # Replace with your channel ID

# --- Utility Functions ---

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
    
    # Handle cases like "1 hour" and "1 hour and 15 minutes"
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    elif len(parts) == 1:
        return parts[0]
    else:
        return "less than a minute" # Should be caught by the < 60 check, but safe fallback

# --- Bot Setup ---
intents = discord.Intents.default()
intents.members = True
intents.presences = True 
client = discord.Client(intents=intents)

# Global dictionary to hold daily tracking data
user_tracker = {}

def load_data():
    """Loads user tracking data from the JSON file."""
    global user_tracker
    try:
        with open(DATA_FILE, 'r') as f:
            user_tracker = json.load(f)
            print("Loaded tracking data.")
    except (FileNotFoundError, json.JSONDecodeError):
        for user_id in SCHEDULED_USERS:
            user_tracker[user_id] = {
                'last_reset_day': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
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

    # Check for daily reset (using UTC day)
    current_day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if user_tracker[user_id_str]['last_reset_day'] != current_day:
        print(f"Resetting data for user {user_id_str}")
        user_tracker[user_id_str] = {
            'last_reset_day': current_day,
            'online_time_timestamp': None,
            'total_time_online': 0,
            'reported_today': False
        }
        save_data() # Save reset

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
    
    if old_status == new_status:
        return

    member = new_presence 
    channel = client.get_channel(NOTIFICATION_CHANNEL_ID)

    if not channel:
        print(f"Error: Notification channel (ID: {NOTIFICATION_CHANNEL_ID}) not found.")
        return

    # --- GOING ONLINE LOGIC ---
    if new_status == discord.Status.online and user_data['online_time_timestamp'] is None:
        
        current_time = datetime.now(timezone.utc)
        user_data['online_time_timestamp'] = current_time.timestamp()
        
        # Calculate lateness
        schedule_str = SCHEDULED_USERS[user_id_str]['schedule']
        scheduled_datetime = datetime.combine(
            current_time.date(), 
            datetime.strptime(schedule_str, '%H:%M').time(), 
            tzinfo=timezone.utc
        )

        lateness = current_time - scheduled_datetime
        
        # 🚨 CHANGE: Use 12-hour format for reporting
        formatted_online_time = current_time.strftime('%I:%M:%S %p UTC')
        message = f"🟢 **ATTENTION!** {member.mention} has just come **ONLINE** at **{formatted_online_time}**."
        
        # Check if they were late
        lateness_seconds = lateness.total_seconds()
        
        if lateness_seconds > 60: # 60 seconds tolerance
            formatted_lateness = format_elapsed_time(lateness_seconds)
            message += f"\n⏰ **LATE:** They were **{formatted_lateness}** late for their scheduled time of **{schedule_str} UTC**."
        elif lateness_seconds < -60:
            formatted_earlyness = format_elapsed_time(abs(lateness_seconds))
            message += f"\n✅ **EARLY:** They came **{formatted_earlyness}** early for their scheduled time of **{schedule_str} UTC**."
        else:
            message += f"\n✅ **ON TIME:** They were on time for their scheduled time of **{schedule_str} UTC**."

        await channel.send(message)
        save_data()


    # --- GOING OFFLINE LOGIC (IDLE/DND/OFFLINE) ---
    elif (new_status in [discord.Status.offline, discord.Status.idle, discord.Status.dnd]) \
         and user_data['online_time_timestamp'] is not None:
        
        current_time = datetime.now(timezone.utc)
        
        time_online_session = current_time.timestamp() - user_data['online_time_timestamp']
        user_data['total_time_online'] += time_online_session
        user_data['online_time_timestamp'] = None

        # Check if we should send the final daily report
        if new_status == discord.Status.offline and not user_data['reported_today']:
            
            # 🚨 CHANGE: Use new function for total time format
            formatted_total_time = format_elapsed_time(user_data['total_time_online'])
            
            # 🚨 CHANGE: Use 12-hour format for reporting
            formatted_offline_time = current_time.strftime('%I:%M:%S %p UTC')

            final_message = f"""
            🛑 **DAILY REPORT FOR {member.mention}** 🛑
            ---
            **Last Status:** Went **OFFLINE** at **{formatted_offline_time}**.
            **Total Time Online Today:** **{formatted_total_time}**.
            """
            
            await channel.send(final_message)
            user_data['reported_today'] = True

        save_data()

# --- Run the Bot ---
client.run('bot id here/token')
