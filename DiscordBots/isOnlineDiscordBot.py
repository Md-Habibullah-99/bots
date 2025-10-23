import discord
import json
import asyncio
from datetime import datetime, time, timedelta, timezone

# --- CONFIGURATION & DATA MANAGEMENT ---

# File path to store persistent data
DATA_FILE = 'schedule_data.json'

# Replace with your actual IDs (use strings for dictionary keys)
# Format: "USER_ID": {"schedule": "HH:MM"} (24-hour time)
SCHEDULED_USERS = {
    "121exampleid1": {"schedule": "10:00"}, # User 1 expected online at 10:00 AM
    "212exampleid2": {"schedule": "11:30"}, # User 2 expected online at 11:30 AM
    "111exampleid3": {"schedule": "09:00"}  # User 3 expected online at 09:00 AM
}

NOTIFICATION_CHANNEL_ID = channel_id_here # Replace with your channel ID

# --- Bot Setup ---
intents = discord.Intents.default()
intents.members = True
intents.presences = True 
client = discord.Client(intents=intents)

# Global dictionary to hold daily tracking data
# Example: {'121exampleid1': {'last_reset_day': '2025-10-23', 'online_time': None, 'total_time_online': 0}}
user_tracker = {}

def load_data():
    """Loads user tracking data from the JSON file."""
    global user_tracker
    try:
        with open(DATA_FILE, 'r') as f:
            user_tracker = json.load(f)
            print("Loaded tracking data.")
    except (FileNotFoundError, json.JSONDecodeError):
        # Initialize with schedule data and required fields
        for user_id in SCHEDULED_USERS:
            user_tracker[user_id] = {
                'last_reset_day': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                'online_time_timestamp': None, # epoch time of the last time they came online
                'total_time_online': 0,        # in seconds
                'reported_today': False        # Flag for single daily report
            }
        print("Initialized new tracking data.")

def save_data():
    """Saves user tracking data to the JSON file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(user_tracker, f, indent=4)

def get_user_data(user_id):
    """Retrieves or initializes user data and checks for daily reset."""
    user_id_str = str(user_id)
    if user_id_str not in user_tracker:
        # Initialize if the user is in the SCHEDULED_USERS but not in the tracker
        if user_id_str in SCHEDULED_USERS:
            user_tracker[user_id_str] = {
                'last_reset_day': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                'online_time_timestamp': None,
                'total_time_online': 0,
                'reported_today': False
            }
        else:
            return None # Not a user we are tracking

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
    load_data() # Load persistent data on startup

@client.event
async def on_presence_update(old_presence, new_presence):
    """Fires when a member's status, activity, or client changes."""
    user_id_str = str(new_presence.id)

    # 1. Check if the user is one we are tracking
    if user_id_str not in SCHEDULED_USERS:
        return

    # Get tracking data and ensure daily reset
    user_data = get_user_data(user_id_str)
    if not user_data:
        return # Should not happen if logic is correct, but safe check

    # Check for status change (from offline/idle/dnd to online, or vice-versa)
    old_status = old_presence.status
    new_status = new_presence.status
    
    if old_status == new_status:
        return # No status change

    member = new_presence # The member object
    channel = client.get_channel(NOTIFICATION_CHANNEL_ID)

    if not channel:
        print(f"Error: Notification channel (ID: {NOTIFICATION_CHANNEL_ID}) not found.")
        return

    # --- GOING ONLINE LOGIC ---
    if new_status == discord.Status.online and user_data['online_time_timestamp'] is None:
        
        # This is the first time the user has gone online since the last daily report/reset
        
        current_time = datetime.now(timezone.utc)
        user_data['online_time_timestamp'] = current_time.timestamp()
        
        # Calculate lateness
        schedule_str = SCHEDULED_USERS[user_id_str]['schedule']
        # Combine today's date with the scheduled time, assuming UTC for simplicity
        scheduled_datetime = datetime.combine(
            current_time.date(), 
            datetime.strptime(schedule_str, '%H:%M').time(), 
            tzinfo=timezone.utc
        )

        lateness = current_time - scheduled_datetime
        
        message = f"🟢 **ATTENTION!** {member.mention} has just come **ONLINE** at **{current_time.strftime('%H:%M:%S UTC')}**."
        
        # Check if they were late
        if lateness.total_seconds() > 60: # 60 seconds tolerance
            minutes_late = int(lateness.total_seconds() / 60)
            message += f"\n⏰ **LATE:** They were **{minutes_late} minutes** late for their scheduled time of **{schedule_str} UTC**."
        elif lateness.total_seconds() < -60:
            minutes_early = int(abs(lateness.total_seconds()) / 60)
            message += f"\n✅ **EARLY:** They came **{minutes_early} minutes** early for their scheduled time of **{schedule_str} UTC**."
        else:
            message += f"\n✅ **ON TIME:** They were on time for their scheduled time of **{schedule_str} UTC**."

        await channel.send(message)
        save_data()


    # --- GOING OFFLINE LOGIC (IDLE/DND/OFFLINE) ---
    elif (new_status in [discord.Status.offline, discord.Status.idle, discord.Status.dnd]) \
         and user_data['online_time_timestamp'] is not None:
        
        # User is going offline/away from an 'online' state

        current_time = datetime.now(timezone.utc)
        
        # Calculate time spent online in this single session
        time_online_session = current_time.timestamp() - user_data['online_time_timestamp']
        
        # Accumulate total time
        user_data['total_time_online'] += time_online_session
        
        # Clear the online timestamp to prepare for the next 'online' session
        user_data['online_time_timestamp'] = None

        # Check if we should send the final daily report
        if new_status == discord.Status.offline and not user_data['reported_today']:
            
            # Format the total time
            total_seconds = user_data['total_time_online']
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            
            final_message = f"""
            🛑 **DAILY REPORT FOR {member.mention}** 🛑
            ---
            **Last Status:** Went **OFFLINE** at **{current_time.strftime('%H:%M:%S UTC')}**.
            **Total Time Online Today:** **{hours} hours and {minutes} minutes**.
            """
            
            await channel.send(final_message)
            
            # Set the reported flag to prevent spam
            user_data['reported_today'] = True

        save_data()

# --- Run the Bot ---
client.run('bot id here/token')
