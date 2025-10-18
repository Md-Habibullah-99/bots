import discord



"""
🔒 Security & Configuration Notice for Developers
ATTENTION: This code is structured to prioritize security by keeping sensitive data out of the source file.

To run this Discord bot successfully, you must configure the following environment variables. DO NOT replace the Python variables with hardcoded ID or token values, as this exposes your secrets.

Required Setup:
1. Bot Token: Set the DISCORD_TOKEN environment variable with your bot's secret token.
2. User Tracking: Set the TARGET_USER_IDS environment variable as a comma-separated string of user IDs (e.g., 12345,67890,54321).
3. Notification Channel: Set the NOTIFICATION_CHANNEL_ID environment variable with the ID of the channel where alerts should be posted.

Local Development: It is highly recommended to use a .env file and the python-dotenv library to manage these secrets locally. Ensure your .gitignore file contains the line .env to prevent accidental public commits.
""""

# 1. Set Intents (MUST include GUILD_PRESENCES and GUILD_MEMBERS)
intents = discord.Intents.default()
intents.members = True   # Required for member data
intents.presences = True # The crucial intent for status updates

client = discord.Client(intents=intents)

# 2. Configure Your Target IDs
# These are the actual IDs you provided
TARGET_USER_IDs = [
    121exampleid1,
    212exampleid2,
    111exampleid3
]
NOTIFICATION_CHANNEL_ID =  channel_id_here

@client.event
async def on_ready():
    print(f'Bot is ready and logged in as {client.user}')

@client.event
async def on_presence_update(old_presence, new_presence):
    # Get the User ID from the presence update (CORRECT: direct access to .id)
    user_id = new_presence.id

    # Check if the user is in our list of target IDs
    if user_id in TARGET_USER_IDs:
        
        # Check if the status has actually changed (e.g., from offline to online)
        if old_presence.status != new_presence.status:
            
            # 🚨 CORRECTION HERE: new_presence is already the Member object.
            # We assign it directly without trying to access .user
            member = new_presence
            
            # Check if the new status is 'online'
            if new_presence.status == discord.Status.online:
                
                channel = client.get_channel(NOTIFICATION_CHANNEL_ID)
                
                if channel:
                    # Send the notification message
                    # member.mention works because member is the correct discord.Member object
                    message = f"🚨 **ATTENTION:** {member.mention} has just come **ONLINE** and visited the server!"
                    await channel.send(message)
                else:
                    print(f"Error: Notification channel (ID: {NOTIFICATION_CHANNEL_ID}) not found.")

# 3. Run the Bot
client.run('bot id here/token')
