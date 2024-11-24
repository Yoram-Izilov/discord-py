import os
import json
import discord
from discord.ext import commands
from discord import app_commands
# all discord user functions
from functions.roulettes import roulette, auto_roulette_menu
from functions.voice import play, leave
from functions.feed import add_rss, view_rss, remove_rss, check_for_new_episodes
from functions.nyaa import search
from functions.mal import scrape

# Set up the bot with the required intents and command prefix
intents = discord.Intents.all()
intents.message_content = True  # Required for reading messages
intents.guilds = True           # Required to join voice channels
bot = commands.Bot(command_prefix='/', intents=intents)

def load_config():
    local_config = 'config-local.json'
    default_config = 'config.json'
    if os.path.exists(local_config):
        config_file = local_config
        print(f"Using local configuration: {local_config}")
    elif os.path.exists(default_config):
        config_file = default_config
        print(f"Using default configuration: {default_config}")
    else:
        raise FileNotFoundError("Neither config-local.json nor config.json was found.")
    with open(config_file, 'r') as file:
        return json.load(file)
    
config = load_config()

@bot.event
async def on_ready():
    await bot.tree.sync()  # Syncs the slash commands with Discord
    print(f'Bot {bot.user} is now online and ready!')
    # starts all the automations (eg rss 1 hour loop check)
    check_for_new_episodes.start(bot)

#region roullete

# Slash command: /roulette
@bot.tree.command(name="roulette", description="Choose one of the provided options with count support and display a pie chart")
async def roulette_command(interaction: discord.Interaction, options: str):
    await roulette(interaction, options)

# Slash command: auto_roulette
@bot.tree.command(name="auto_roulette", description="Manage auto roulettes")
@app_commands.describe(action="Choose an action for the auto roulette", add_option="Optional string for 'Add Roulette'")
@app_commands.choices(action=[
    app_commands.Choice(name="Start Roulette", value="start_roulette"),
    app_commands.Choice(name="Add Roulette", value="add_roulette"),
    app_commands.Choice(name="Remove Roulette", value="remove_roulette"),
])
async def auto_roulette_command(interaction: discord.Interaction, action: app_commands.Choice[str], add_option: str = None):
    await auto_roulette_menu(interaction, action, add_option)

#endregion

#region voice & play

# Slash command to leave the voice channel
@bot.tree.command(name="leave", description="Disconnect from the voice channel")
async def leave_command(interaction: discord.Interaction):
    await leave(interaction)

# Slash command to join and play music from a YouTube URL
@bot.tree.command(name="play", description="Play music from a YouTube URL or search term")
@app_commands.describe(url="URL of the YouTube video", search="Search query for music")
async def play_command(interaction: discord.Interaction, url: str = None, search: str = None):
    # Ensure that only one of the options is provided
    provided_options = [url, search]
    await play(interaction, url, bot)

#endregion

#region rss

# Command to add an episode to the RSS feed
@bot.tree.command(name="add_rss", description="Add an episode to your RSS feed")
async def add_rss_command(interaction: discord.Interaction):
    await add_rss(interaction)

# Command to view all saved RSS subscriptions
@bot.tree.command(name="view_rss", description="View all your saved RSS subscriptions")
async def view_rss_command(interaction: discord.Interaction):
    await view_rss(interaction)

# Command to remove an episode from the RSS feed
@bot.tree.command(name="remove_rss", description="Remove an episode from your RSS feed")
async def remove_rss_command(interaction: discord.Interaction):
    await remove_rss(interaction)
     
#endregion

#region Nyaa

@bot.tree.command(name="nyaa", description="Search for torrents on Nyaa")
async def search_command(interaction: discord.Interaction, query: str):
    await search(interaction, query)

#endregion

#region MAL

@bot.tree.command(name="mal", description="test lazy")
async def scrape_command(interaction: discord.Interaction):
    await scrape(interaction)

#endregion 

bot.run(config['discord']['token'])