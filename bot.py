import discord
from discord.ext import commands
import random
import yt_dlp
from discord import FFmpegPCMAudio
import asyncio

# Set up the bot with the required intents and command prefix
intents = discord.Intents.all()
intents.message_content = True  # Required for reading messages
intents.guilds = True  # Required to join voice channels

bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()  # Syncs the slash commands with Discord
    print(f'Bot {bot.user} is now online and ready!')

# Slash command: /roulette
@bot.tree.command(name="roulette", description="Choose one of the provided options")
async def roulette(interaction: discord.Interaction, options: str):
    options_list = options.split(',')
    choice = random.choice(options_list).strip()
    await interaction.response.send_message(f'I choose: {choice}')

# Slash command to leave the voice channel
@bot.tree.command(name="leave", description="Disconnect from the voice channel")
async def leave(interaction: discord.Interaction):
    if interaction.guild.voice_client is not None:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Disconnected from the voice channel.")
    else:
        await interaction.response.send_message("I'm not connected to any voice channel.")

# Slash command to join and play music from a YouTube URL
@bot.tree.command(name="play", description="Play music from a YouTube URL")
async def play(interaction: discord.Interaction, url: str):
    # Acknowledge the interaction quickly to prevent timeout
    await interaction.response.defer()  # This acknowledges the interaction, allowing you to do further work

    # Check if the user is in a voice channel
    voice_channel = interaction.user.voice.channel if interaction.user.voice else None
    if not voice_channel:
        await interaction.followup.send("You need to join a voice channel first!")
        return

    # Check if bot is already connected to the voice channel
    if interaction.guild.voice_client:
        voice_client = interaction.guild.voice_client
    else:
        voice_client = await voice_channel.connect()

    # yt-dlp options to ensure the best audio stream is extracted
    ydl_opts = {
        'format': 'bestaudio/best',   # Get the best audio quality
        'extractaudio': True,         # Only extract audio
        'audioquality': 1,            # Best quality
        'outtmpl': 'downloads/%(id)s.%(ext)s',  # Download location (unused here, but keep it for context)
        'restrictfilenames': True,
        'noplaylist': True,           # Avoid downloading entire playlists
        'quiet': True,                # Less verbose output
        'force_generic_extractor': True,  # Ensure that yt-dlp uses a generic extractor
    }

    try:
        # Extract the video info using yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'formats' in info:
                # We will now grab the URL for the best audio format
                audio_url = None
                for f in info['formats']:
                    if f.get('acodec') == 'mp4a.40.2':  # We want AAC audio codec
                        audio_url = f['url']
                        break

                if not audio_url:
                    # If no valid audio URL found, fallback to the first available
                    audio_url = info['formats'][0]['url']

                # Set FFmpegPCMAudio with more reconnect options for streaming stability
                source = FFmpegPCMAudio(
                    audio_url,
                    before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                    options="-vn"
                )
                # Play the audio in the voice channel
                voice_client.play(source, after=lambda e: print(f'Finished playing: {e}'))

                # Send a follow-up message indicating the song is now playing
                await interaction.followup.send(f"Now playing: {info['title']}")
            else:
                await interaction.followup.send("Could not extract audio from the given URL.")
    except Exception as e:
        # If something goes wrong, send a follow-up message
        await interaction.followup.send(f"An error occurred: {e}")

