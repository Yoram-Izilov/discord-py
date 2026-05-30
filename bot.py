import sys
import traceback

import discord
from discord.ext import commands
from discord import app_commands

from utils.config import config
from utils.db import init_pool, ensure_schema
from utils.logger import botLogger
from utils.tracing import trace_function
from utils.utils import make_embed

# all discord user functions
from functions.roulettes import roulette, auto_roulette_menu
from functions.voice import play, leave
from functions.queue import queue_play, skip_track, queue_show, now_playing, op_play
from functions.feed import rss_menu
from functions.nyaa import search
from functions.mal import (
    mal_menu, anime_list_menu, next_anime, mal_link, mal_unlink,
    next_episode, mal_compare, mal_stats, anime_recommend, who_is_watching,
)
from functions.season import season_anime
from functions.quiz import anime_quiz
from functions.help import show_help
from functions.tasks import (
    _run_new_episode_check_logic, check_for_new_anime,
    refresh_all_mal_snapshots, weekly_leaderboard,
)
from utils.db import episode_announcement_get_series, rss_subscribe
from config.consts import OTAKU_CHANNEL_ID

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

if not config.debug:
    # Configure tracer provider
    resource = Resource.create({"service.name": "mydiscordbot"})
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

    # Continuous wall-clock profiling across all threads -> Pyroscope.
    # oncpu=False samples blocking I/O too (Discord WS, HTTP, Selenium);
    # gil_only=False includes native threads (ffmpeg, chromium driver).
    import pyroscope
    pyroscope.configure(
        application_name="mydiscordbot",
        server_address="http://pyroscope:4040",
        sample_rate=100,
        oncpu=False,
        gil_only=False,
        enable_logging=False,
        tags={"service_name": "mydiscordbot"},
    )

# Set up the bot with the required intents and command prefix
intents = discord.Intents.all()
intents.message_content = True  # Required for reading messages
intents.guilds = True           # Required to join voice channels
bot = commands.Bot(command_prefix='/', intents=intents)


@bot.event
@trace_function
async def on_ready():
    await init_pool()
    await ensure_schema()
    print(f"Logged in as {bot.user}")

    await bot.tree.sync()  # Syncs the slash commands with Discord
    print(f'Bot {bot.user} is now online and ready!')
    # starts all the automations (eg rss 1 hour loop check)
    if not config.debug:
        print('tasks running.')
        check_for_new_anime.start(bot)
        _run_new_episode_check_logic.start(bot)
        refresh_all_mal_snapshots.start(bot)
        weekly_leaderboard.start(bot)


@bot.event
async def on_error(event, *args, **kwargs):
    exc_type, exc, tb = sys.exc_info()
    botLogger.error(
        "unhandled event exception in %s: %s\n%s",
        event,
        exc,
        "".join(traceback.format_exception(exc_type, exc, tb)),
    )


REACTION_SUBSCRIBE_EMOJI = "🔔"


@bot.event
@trace_function
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    if payload.channel_id != OTAKU_CHANNEL_ID:
        return
    if str(payload.emoji) != REACTION_SUBSCRIBE_EMOJI:
        return

    series = await episode_announcement_get_series(payload.message_id)
    if not series:
        return

    if not await rss_subscribe(series, payload.user_id):
        return  # already subscribed - no need to DM again

    user = bot.get_user(payload.user_id) or await bot.fetch_user(payload.user_id)
    if user is None:
        return
    try:
        await user.send(
            embed=make_embed(f"✅ Subscribed to **{series}** via 🔔 reaction.", kind="success")
        )
    except discord.HTTPException as e:
        botLogger.info("could not DM %s after reaction-subscribe: %s", payload.user_id, e)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    command_name = interaction.command.name if interaction.command else "<unknown>"
    botLogger.error(
        "unhandled slash command exception in /%s: %s\n%s",
        command_name,
        error,
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    )
    try:
        embed = make_embed("An unexpected error occurred. The incident has been logged.", kind="error")
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException:
        pass

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

@bot.tree.command(name="queue_play", description="Queue a track (joins the queue if something is already playing)")
@app_commands.describe(query="YouTube URL or search query")
@trace_function
async def queue_play_command(interaction: discord.Interaction, query: str):
    botLogger.info('run queue_play_command')
    await queue_play(interaction, query)

@bot.tree.command(name="skip", description="Skip the currently playing track")
@trace_function
async def skip_command(interaction: discord.Interaction):
    botLogger.info('run skip_command')
    await skip_track(interaction)

@bot.tree.command(name="queue", description="Show the current music queue")
@trace_function
async def queue_command(interaction: discord.Interaction):
    botLogger.info('run queue_command')
    await queue_show(interaction)

@bot.tree.command(name="now_playing", description="Show the currently playing track")
@trace_function
async def now_playing_command(interaction: discord.Interaction):
    botLogger.info('run now_playing_command')
    await now_playing(interaction)

@bot.tree.command(name="op", description="Queue an anime opening from YouTube")
@app_commands.describe(anime="Name of the anime")
@trace_function
async def op_command(interaction: discord.Interaction, anime: str):
    botLogger.info('run op_command')
    await op_play(interaction, anime)

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
    app_commands.Choice(name="View all RSS subs", value="all_rss_subscribe"),
    app_commands.Choice(name="Check RSS feed", value="check_rss"),
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

@bot.tree.command(name="mal_link", description="Bind your Discord account to your MAL username")
@app_commands.describe(mal_username="Your MyAnimeList username (case-insensitive)")
@trace_function
async def mal_link_command(interaction: discord.Interaction, mal_username: str):
    botLogger.info('run mal_link_command')
    await mal_link(interaction, mal_username)

@bot.tree.command(name="mal_unlink", description="Remove the link between your Discord and your MAL username")
@trace_function
async def mal_unlink_command(interaction: discord.Interaction):
    botLogger.info('run mal_unlink_command')
    await mal_unlink(interaction)

@bot.tree.command(name="next_episode", description="Next episode for each of your RSS subs (or pass anime: to look up one)")
@app_commands.describe(anime="Optional: look up a specific anime instead of your subscription list")
@trace_function
async def next_episode_command(interaction: discord.Interaction, anime: str = None):
    botLogger.info('run next_episode_command')
    await next_episode(interaction, anime)

@bot.tree.command(name="mal_compare", description="Compare your MAL list with another linked user")
@app_commands.describe(other="The Discord user to compare against")
@trace_function
async def mal_compare_command(interaction: discord.Interaction, other: discord.Member):
    botLogger.info('run mal_compare_command')
    await mal_compare(interaction, other)

@bot.tree.command(name="mal_stats", description="Show your MAL activity charts")
@trace_function
async def mal_stats_command(interaction: discord.Interaction):
    botLogger.info('run mal_stats_command')
    await mal_stats(interaction)

@bot.tree.command(name="anime_recommend", description="Pick a random anime from your plan-to-watch list")
@trace_function
async def anime_recommend_command(interaction: discord.Interaction):
    botLogger.info('run anime_recommend_command')
    await anime_recommend(interaction)

@bot.tree.command(name="who_is_watching", description="See which linked members are currently watching an anime")
@app_commands.describe(anime="Anime title to search for")
@trace_function
async def who_is_watching_command(interaction: discord.Interaction, anime: str):
    botLogger.info('run who_is_watching_command')
    await who_is_watching(interaction, anime)

#endregion

#region Season

@bot.tree.command(name="season_anime", description="Browse this season's airing anime, subscribe with the 🔔 button")
@trace_function
async def season_anime_command(interaction: discord.Interaction):
    botLogger.info('run season_anime_command')
    await season_anime(interaction)

#endregion

#region Quiz

@bot.tree.command(name="anime_quiz", description="Guess the anime from its synopsis (60s, first correct guess wins)")
@trace_function
async def anime_quiz_command(interaction: discord.Interaction):
    botLogger.info('run anime_quiz_command')
    await anime_quiz(interaction)

#endregion

#region Help

@bot.tree.command(name="help", description="List every command the bot exposes, grouped by feature")
@trace_function
async def help_command(interaction: discord.Interaction):
    botLogger.info('run help_command')
    await show_help(interaction)

#endregion

bot.run(config.discord.token)
botLogger.info('bot stop running.')

