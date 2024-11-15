import discord
from discord.ext import commands
import random
import yt_dlp
from discord import FFmpegPCMAudio
import asyncio
import matplotlib.pyplot as plt
import io

# testing webhook2
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
@bot.tree.command(name="roulette", description="Choose one of the provided options with count support and display a pie chart")
async def roulette(interaction: discord.Interaction, options: str):
    expanded_options = []
    counts = {}

    # Parse options and expand based on count
    for item in options.split(','):
        item = item.strip()
        if '|' in item:
            name, count_str = item.split('|', 1)
            count = int(count_str) if count_str.isdigit() else 1
        else:
            name, count = item, 1
        expanded_options.extend([name.strip()] * count)

        # Count occurrences of each item for the chart
        counts[name.strip()] = counts.get(name.strip(), 0) + count

    # Select a random choice and calculate its percentage
    choice = random.choice(expanded_options)
    choice_count = expanded_options.count(choice)
    total_count = len(expanded_options)
    win_percentage = (choice_count / total_count) * 100

    # Generate a pie chart
    labels = list(counts.keys())
    sizes = list(counts.values())
    colors = ['#ff9999','#66b3ff','#99ff99','#ffcc99']  # Add more colors as needed

    plt.figure(figsize=(6,6))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors)
    plt.title(f'Rolling for {interaction.user.name}')
    plt.gca().axis("equal")  # Equal aspect ratio ensures that pie is drawn as a circle.

    # Save chart to a BytesIO object
    image_bytes = io.BytesIO()
    plt.savefig(image_bytes, format='png')
    image_bytes.seek(0)

    # Send the result message along with the pie chart image
    await interaction.response.send_message(
        f'Congratulations! The chosen option is: **{choice}**\n'
        f'with a chance of **{win_percentage:.2f}%**',
        file=discord.File(fp=image_bytes, filename="roulette_result.png")
    )

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
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['formats'][0]['url']

            source = FFmpegPCMAudio(
                audio_url,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
            )

            def after_play(error):
                if error:
                    print(f"Error: {error}")
                if voice_client.is_connected():
                    asyncio.run_coroutine_threadsafe(voice_client.disconnect(), bot.loop)

            voice_client.play(source, after=after_play)
            await interaction.followup.send(f"Now playing: {info['title']}")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}")