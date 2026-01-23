import discord
from discord.ext import commands
from discord import app_commands

from utils.config import config
from utils.logger import botLogger
from utils.tracing import trace_function

# all discord user functions
from functions.roulettes import roulette, auto_roulette_menu
from functions.voice import play, leave
from functions.feed import rss_menu
from functions.nyaa import search
from functions.mal import mal_menu, anime_list_menu, next_anime
from functions.tasks import check_for_new_episodes, check_for_new_anime

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

# Configure tracer provider
resource = Resource.create({"service.name": "discord-bot"})
provider = TracerProvider(resource=resource)
exporter = OTLPSpanExporter(
    endpoint="tempo:4317",
    insecure=True
)  # sends to Grafana / Tempo
processor = BatchSpanProcessor(exporter)
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

# Instrument asyncio (important for Discord.py)
AsyncioInstrumentor().instrument()

tracer = trace.get_tracer(__name__)

# Set up the bot with the required intents and command prefix
intents = discord.Intents.all()
intents.message_content = True  # Required for reading messages
intents.guilds = True           # Required to join voice channels
bot = commands.Bot(command_prefix='/', intents=intents)


@bot.event
@trace_function
async def on_ready():
    print(f"Logged in as {bot.user}")

    await bot.tree.sync()  # Syncs the slash commands with Discord
    print(f'Bot {bot.user} is now online and ready!')
    # starts all the automations (eg rss 1 hour loop check)
    if not config.debug:
        print('tasks running.')
        check_for_new_anime.start(bot)
        check_for_new_episodes.start(bot)

#region roullete

# Slash command: /roulette
@bot.tree.command(name="roulette", description="Choose one of the provided options with count support and display a pie chart")
@trace_function
async def roulette_command(interaction: discord.Interaction, options: str):
    botLogger.info('run roulette_command')
    await roulette(interaction, options)

# Slash command: auto_roulette
@bot.tree.command(name="auto_roulette", description="Manage auto roulettes")
@app_commands.describe(action="Choose an action for the auto roulette", add_option="Optional string for 'Add Roulette'")
@app_commands.choices(action=[
    app_commands.Choice(name="Start Roulette", value="start_roulette"),
    app_commands.Choice(name="Add Roulette", value="add_roulette"),
    app_commands.Choice(name="Remove Roulette", value="remove_roulette"),
])
@trace_function
async def auto_roulette_command(interaction: discord.Interaction, action: app_commands.Choice[str], add_option: str = None):
    botLogger.info('run auto_roulette_command')
    await auto_roulette_menu(interaction, action, add_option)

#endregion

#region voice & play

# Slash command to leave the voice channel
@bot.tree.command(name="leave", description="Disconnect from the voice channel")
@trace_function
async def leave_command(interaction: discord.Interaction):
    botLogger.info('run leave_command')
    await leave(interaction)

# Slash command to join and play music from a YouTube URL or search query
@bot.tree.command(name="play", description="Play music from a YouTube URL or search term")
@app_commands.describe(query="YouTube URL or search query (e.g., 'vinland saga op 1' or 'https://youtu.be/...')")
@trace_function
async def play_command(interaction: discord.Interaction, query: str):
    botLogger.info('run play_command')
    await play(interaction, query, bot)

#endregion

#region rss

# RSS menu
@bot.tree.command(name="rss", description="Manage your RSS feed")
@app_commands.describe(action="choose what to do with the RSS feed")
@app_commands.choices(action=[
    app_commands.Choice(name="Add RSS", value="add_rss"),
    app_commands.Choice(name="View RSS", value="view_rss"),
    app_commands.Choice(name="Sub To RSS", value="sub_to_rss"),
    app_commands.Choice(name="Remove RSS", value="remove_rss"),
    app_commands.Choice(name="Unsub From RSS", value="unsub_from_rss"),
    app_commands.Choice(name="view all RSS subs", value="all_rss_subscribe"),
])
@trace_function
async def rss_command(interaction: discord.Interaction, action: app_commands.Choice[str], search: str = None):
    botLogger.info('run rss_menu')
    await rss_menu(interaction, action, search)
     
#endregion

#region Nyaa

@bot.tree.command(name="nyaa", description="Search for torrents on Nyaa")
@trace_function
async def search_command(interaction: discord.Interaction, query: str):
    botLogger.info('run search_command')
    await search(interaction, query)

#endregion

#region MAL

@bot.tree.command(name="mal", description="Manage mal user")
@app_commands.describe(action="choose what to do with the mal")
@app_commands.choices(action=[
    app_commands.Choice(name="Add user", value="add_user"),
    app_commands.Choice(name="View users", value="view_users"),
    app_commands.Choice(name="Remove user", value="remove_user"),
])
@trace_function
async def mal_command(interaction: discord.Interaction, action: app_commands.Choice[str], user: str = None):
    botLogger.info('run mal_command')
    await mal_menu(interaction, action, user)

@bot.tree.command(name="anime_list", description="Manage anime list")
@app_commands.describe(action="choose what to do with the anime list")
@app_commands.choices(action=[
    app_commands.Choice(name="Update watching list", value="update_watching_list"),
    app_commands.Choice(name="Update plan to watch list", value="update_plantowatch_list"),
    app_commands.Choice(name="View watching list", value="view_watching_list"),
    app_commands.Choice(name="View plan to watch list", value="view_plantowatch_list"),

])
@trace_function
async def anime_list_command(interaction: discord.Interaction, action: app_commands.Choice[str]):
    botLogger.info('run anime_list_command')
    await anime_list_menu(bot, interaction, action)

@bot.tree.command(name="next_anime", description="roulete from plan to watch anime.")
@trace_function
async def next_anime_command(interaction: discord.Interaction):
    botLogger.info('run next_anime_command')
    await next_anime(interaction)

#endregion 

bot.run(config.discord.token)
botLogger.info('bot stop running.')

