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

# 🚨 CHANGE 1: New data structure for SCHEDULED_USERS with daily times
# Keys are full day names (Monday, Tuesday, etc.) or 'default'.
# Time is 24-hour format ('HH:MM').
SCHEDULED_USERS = {
    "121exampleid1": {
        "Saturday": {"in": "10:00", "out": "23:00"}, # 10:00 AM to 11:00 PM
        "Sunday": {"in": "11:00", "out": "21:00"},  # 11:00 AM to 9:00 PM
        "default": {"in": "09:00", "out": "18:00"}  # Default for other days
    },
    "212exampleid2": {
        "Monday": {"in": "09:30", "out": "17:30"},
        "default": {"in": "10:00", "out": "19:00"}
    },
    "111exampleid3": {
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
        return "less than a minute"

# --- Bot Setup and Data Handlers (Unchanged) ---

intents = discord.Intents.default()
intents.members = True
intents.presences = True 
client = discord.Client(intents=intents)

user_tracker = {}

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(user_tracker, f, indent=4)

def reset_user_data(user_id_str):
    current_day = get_local_now().strftime('%Y-%m-%d')
    user_tracker[user_id_str] = {
        'last_reset_day': current_day,
        'online_time_timestamp': None,       
        'first_online_timestamp': None,       
        'last_offline_timestamp': None,       
        'total_time_online': 0,               
        'online_message_sent': False         
    }

def load_data():
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
        if user_id_str not in user_tracker or user_tracker[user_id_str]['last_reset_day'] != current_day:
            print(f"Initializing/Resetting data for user {user_id_str}")
            reset_user_data(user_id_str)
            
    save_data()
    return user_tracker

# --- Background Task for Midnight Report (Modified for better clarity) ---

async def midnight_reporter():
    await client.wait_until_ready()
    channel = client.get_channel(NOTIFICATION_CHANNEL_ID)
    
    if not channel:
        print(f"Error: Notification channel (ID: {NOTIFICATION_CHANNEL_ID}) not found. Midnight reports disabled.")
        return

    while not client.is_closed():
        now = get_local_now()
        tomorrow = now.date() + timedelta(days=1)
        # Target is 12:00:00 AM in the local time zone
        target_time = TARGET_TIMEZONE.localize(datetime.combine(tomorrow, time(0, 0, 0)))

        # Handle case where bot was started after midnight
        if now > target_time:
            target_time += timedelta(days=1)

        sleep_seconds = (target_time - now).total_seconds()
        
        print(f"Midnight Reporter: Sleeping for {sleep_seconds/3600:.2f} hours until {target_time.strftime('%I:%M:%S %p %Z')}")
        await asyncio.sleep(sleep_seconds)

        # --- Report Generation Logic (Fires exactly at 12:00 AM Local Time) ---
        print("Midnight Reporter: Triggered. Generating reports.")
        
        for user_id_str, user_data in user_tracker.items():
            
            # Skip if user never came online today
            if user_data['first_online_timestamp'] is None:
                continue

            # Load the schedule that was relevant for the day that just ended
            # NOTE: get_schedule_for_user() uses the current time, but since it's 12:00 AM, 
            # we need to check the schedule for the DAY BEFORE (now - 1 day)
            day_before = now.date() - timedelta(days=1)
            day_name_before = day_before.strftime('%A')
            
            # Temporarily override time to check yesterday's schedule
            temp_schedule_check_time = TARGET_TIMEZONE.localize(datetime.combine(day_before, time(12, 0, 0))) 
            user_schedule = get_schedule_for_user_on_day(user_id_str, day_name_before)

            first_online = datetime.fromtimestamp(user_data['first_online_timestamp'], tz=TARGET_TIMEZONE)
            last_offline = datetime.fromtimestamp(user_data['last_offline_timestamp'], tz=TARGET_TIMEZONE)
            
            # Calculate duration between first online and last offline
            total_duration_raw = last_offline - first_online
            formatted_duration = format_elapsed_time(total_duration_raw.total_seconds())
            
            # Get member to use mention in report
            member = client.get_user(int(user_id_str))
            
            # Calculate expected duration and check for "extra time"
            extra_time_message = ""
            if user_schedule and user_schedule['in'] and user_schedule['out']:
                
                # Combine schedule times with yesterday's date
                in_time = datetime.strptime(user_schedule['in'], '%H:%M').time()
                out_time = datetime.strptime(user_schedule['out'], '%H:%M').time()
                
                # Assuming the in/out times are within the same day
                scheduled_start = TARGET_TIMEZONE.localize(datetime.combine(day_before, in_time))
                scheduled_end = TARGET_TIMEZONE.localize(datetime.combine(day_before, out_time))

                expected_duration_raw = scheduled_end - scheduled_start
                
                # Calculate the difference between actual elapsed time and expected time
                time_difference = total_duration_raw - expected_duration_raw
                
                if time_difference.total_seconds() > 60:
                    formatted_extra_time = format_elapsed_time(time_difference.total_seconds())
                    extra_time_message = f"\n⚠️ **EXTRA TIME:** They exceeded their scheduled `{user_schedule['in']} - {user_schedule['out']}` window by **{formatted_extra_time}**."
                elif time_difference.total_seconds() < -60:
                    formatted_missing_time = format_elapsed_time(abs(time_difference.total_seconds()))
                    extra_time_message = f"\n⌛ **MISSING TIME:** They were active for **{formatted_missing_time}** less than their scheduled `{user_schedule['in']} - {user_schedule['out']}` window."

            if member:
                message = f"""
                🌙 **MIDNIGHT ATTENDANCE REPORT for {member.mention} ({day_name_before})** 🌙
                ---
                **Scheduled IN:** {user_schedule.get('in', 'N/A')} **OUT:** {user_schedule.get('out', 'N/A')}
                **First Online:** {first_online.strftime('%I:%M:%S %p %Z')}
                **Last Offline:** {last_offline.strftime('%I:%M:%S %p %Z')}
                **Total Time Elapsed (First to Last):** **{formatted_duration}**
                {extra_time_message}
                """
                await channel.send(message)

            # Reset data for the start of the new day
            reset_user_data(user_id_str)

        save_data()
        await asyncio.sleep(1) 

def get_schedule_for_user_on_day(user_id, day_name):
    """Helper function to look up a schedule for a specific day name."""
    user_id_str = str(user_id)
    if user_id_str not in SCHEDULED_USERS:
        return None
    
    user_schedule = SCHEDULED_USERS[user_id_str]
    
    if day_name in user_schedule:
        return user_schedule[day_name]
    elif 'default' in user_schedule:
        return user_schedule['default']
    
    return None

# --- Core Bot Events ---

@client.event
async def on_ready():
    print(f'Bot is ready and logged in as {client.user}')
    load_data()
    client.loop.create_task(midnight_reporter())


@client.event
async def on_presence_update(old_presence, new_presence):
    user_id_str = str(new_presence.id)

    if user_id_str not in SCHEDULED_USERS:
        return

    # Ensure data is loaded/reset for the current day
    user_data = user_tracker.get(user_id_str)
    if not user_data or user_data['last_reset_day'] != get_local_now().strftime('%Y-%m-%d'):
        load_data()
        user_data = user_tracker.get(user_id_str)
        if not user_data: return

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
    
    # 🚨 CHANGE 2: Get today's specific schedule
    current_schedule = get_schedule_for_user(user_id_str)
    if not current_schedule:
        print(f"Warning: No schedule found for {user_id_str} today. Skipping presence update alert.")
        return
    
    scheduled_in_time_str = current_schedule.get('in')

    # --- GOING ONLINE LOGIC (Start session / Record first online time) ---
    if is_going_online:
        
        current_time = get_local_now()
        
        # 1. Start the current session timestamp
        user_data['online_time_timestamp'] = current_time.timestamp() 
        
        # 2. Record the first online time of the day
        if user_data['first_online_timestamp'] is None:
            user_data['first_online_timestamp'] = current_time.timestamp()

        # 3. Report Lateness/Earlyness (only once per day)
        if not user_data['online_message_sent'] and scheduled_in_time_str:
            
            scheduled_time_24hr = datetime.strptime(scheduled_in_time_str, '%H:%M').time()
            scheduled_datetime = TARGET_TIMEZONE.localize(
                datetime.combine(current_time.date(), scheduled_time_24hr)
            )

            lateness = current_time - scheduled_datetime
            tz_abbr = current_time.strftime('%Z')
            formatted_online_time = current_time.strftime(f'%I:%M:%S %p {tz_abbr}')
            message = f"🟢 **ATTENTION!** {member.mention} has just come **ONLINE** at **{formatted_online_time}**."
            
            lateness_seconds = lateness.total_seconds()
            
            if lateness_seconds > 60: 
                # LATE: After scheduled time
                formatted_lateness = format_elapsed_time(lateness_seconds)
                message += f"\n⏰ **LATE:** They were **{formatted_lateness}** late for their scheduled **IN** time of **{scheduled_in_time_str} {tz_abbr}**."
            elif lateness_seconds < -60: 
                # EARLY: Before scheduled time
                formatted_earlyness = format_elapsed_time(abs(lateness_seconds))
                message += f"\n⚠️ **EARLY (Extra Time):** They came **{formatted_earlyness}** early for their scheduled **IN** time of **{scheduled_in_time_str} {tz_abbr}**."
            else:
                message += f"\n✅ **ON TIME:** They were on time for their scheduled **IN** time of **{scheduled_in_time_str} {tz_abbr}**."

            await channel.send(message)
            user_data['online_message_sent'] = True
        
        save_data()


    # --- GOING OFFLINE LOGIC (End session / Record last offline time) ---
    elif is_going_offline_or_away and user_data['online_time_timestamp'] is not None:
        
        current_time = get_local_now()
        
        # 1. Accumulate session time
        time_online_session = current_time.timestamp() - user_data['online_time_timestamp']
        user_data['total_time_online'] += time_online_session
        
        # 2. Clear session timestamp
        user_data['online_time_timestamp'] = None
        
        # 3. Record the last offline time (used by the midnight reporter)
        user_data['last_offline_timestamp'] = current_time.timestamp() 
        
        save_data()

# --- Run the Bot ---
client.run('bot id here/token')
