import discord
from discord.ext import commands
from discord import app_commands
import random
import yt_dlp
from discord import FFmpegPCMAudio
import asyncio
import matplotlib.pyplot as plt
import io
import textwrap

# Set up the bot with the required intents and command prefix
intents = discord.Intents.all()
intents.message_content = True  # Required for reading messages
intents.guilds = True  # Required to join voice channels
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()  # Syncs the slash commands with Discord
    print(f'Bot {bot.user} is now online and ready!')

# create roulette bar chart and announce the winner
async def chart_and_annouce(interaction, expanded_options, counts):
    # Select a random choice and calculate its percentage
    choice = random.choice(expanded_options)
    choice_count = expanded_options.count(choice)
    total_count = len(expanded_options)
    win_percentage = (choice_count / total_count) * 100

    # Generate a pie chart
    labels = list(counts.keys())
    colors = ['#66b3ff', '#ff9999','#99ff99','#ffcc99','#c2c2f0'] # Add more colors as needed

    # Add labels and title
    plt.title(f'Rolling for {interaction.user.name}')

    # Create the bar chart
    chart_width = 2 * len(labels)
    if (chart_width == 2): chart_width = chart_width + 1
    plt.figure(figsize=(chart_width, 6), facecolor='transparent')
    
    # Dynamically adjust bottom margin based on maximum text height
    max_chars_per_line = int(20)
    max_height = max(len(textwrap.wrap(label, width=max_chars_per_line)) for label in labels)
    margin_bottom = 0.03 + (max_height * 0.03)
    plt.subplots_adjust(bottom=margin_bottom)

    # Loop to draw bars with special border for the selected choice
    for i, label in enumerate(labels):
        # Determine edge color: gold for the chosen one, none for others
        edge_color = 'gold' if label == choice else 'none'
        bar_color = colors[i % len(colors)]
        # Wrap text based on bar width (approximately 10 characters per bar width)
        
        wrapped_label = '\n'.join(textwrap.wrap(label, width=max_chars_per_line))

        # Create the bar with thicker border for winner
        plt.bar(label, counts[label], 
                color=bar_color, 
                edgecolor=edge_color,
                linewidth=1.5 if label == choice else 1)
            
        # Customize label appearance
        if label == choice:
            # For the selected label: bold, white text with matching background
            plt.text(label, -0.03, wrapped_label, 
                    ha='center', va='top',
                    weight='bold', color='white',
                    bbox=dict(facecolor=bar_color, 
                            edgecolor='gold', 
                            pad=2,
                            linewidth=1.5))
        else:
            # For other labels: normal appearance
            plt.text(label, -0.03, wrapped_label, 
                    ha='center', va='top', weight='bold', color='white')

    # Remove original x-axis labels to avoid overlap
    plt.gca().set_xticklabels([])

    # Remove the border (spines) around the plot
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)
    plt.gca().patch.set_alpha(0.0)
    # Set the y-axis to percentage
    plt.ylim(0, max(counts.values()) * 1.02)  # Add a little margin on top
    plt.yticks(ticks=[i for i in range(0, max(counts.values()) + 1, 1)],
            labels=[f"{i / total_count * 100:.0f}%" for i in range(0, max(counts.values()) + 1, 1)])

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

# Slash command: /roulette
@bot.tree.command(name="roulette", description="Choose one of the provided options with count support and display a pie chart")
async def roulette(interaction: discord.Interaction, options: str):
    expanded_options = []
    counts = {}

    # Parse options and expand based on count
    for item in options.split(','):
        item = item.strip()
        if item:  # Check if item is not empty
            if '|' in item:
                name, count_str = item.split('|', 1)
                count = int(count_str) if count_str.isdigit() else 1
            else:
                name, count = item, 1
            expanded_options.extend([name.strip()] * count)

            # Count occurrences of each item for the chart
            counts[name.strip()] = counts.get(name.strip(), 0) + count

    await chart_and_annouce(interaction, expanded_options, counts)
    
# Helper functions to read and write to the options file
FILE_PATH = "roulette_options.txt"

def read_options(file_path):
    with open(file_path, "r") as file:
        return [line.strip() for line in file.readlines()]

def write_options(file_path, options):
    with open(file_path, "w") as file:
        file.write("\n".join(options))

def parse_options(option_line):
    options = []
    for item in option_line.split(","):
        item = item.strip()
        if "|" in item:
            name, count_str = item.split("|", 1)
            count = int(count_str)
        else:
            name, count = item, 1
        options.append((name.strip(), count))
    return options

def update_options(options, winner):
    updated_options = []
    for name, count in options:
        if name == winner:
            updated_options.append(f"{name}")
        else:
            updated_options.append(f"{name}|{count + 1}")
    return updated_options

# Slash command: auto_roulette
@bot.tree.command(name="auto_roulette", description="Choose from saved options and update them automatically")
async def auto_roulette(interaction: discord.Interaction):
    lines = read_options(FILE_PATH)
    if not lines:
        await interaction.response.send_message("No options are available. Please add some using `/add_auto_roulette`.")
        return
    
    # Create dropdown menu options
    class OptionSelect(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(label=line, value=f"{i}")
                for i, line in enumerate(lines)
            ]
            super().__init__(placeholder="Choose an option set...", options=options)

        async def callback(self, interaction: discord.Interaction):
            index = int(self.values[0])
            option_line = lines[index]
            options = parse_options(option_line)
            
            # Perform roulette logic
            expanded_options = [name for name, count in options for _ in range(count)]
            winner = random.choice(expanded_options)

            # Update options based on the winner
            updated_options = update_options(options, winner)
            lines[index] = ",".join(updated_options)
            write_options(FILE_PATH, lines)

            # Create a pie chart
            counts = {name: count for name, count in options}
            await chart_and_annouce(interaction, expanded_options, counts)

    class OptionSelectView(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(OptionSelect())

    await interaction.response.send_message("Select an option set:", view=OptionSelectView())

# Slash command: remove_auto_roulette
@bot.tree.command(name="remove_auto_roulette", description="Remove an option set from the file")
async def remove_auto_roulette(interaction: discord.Interaction):
    lines = read_options(FILE_PATH)
    if not lines:
        await interaction.response.send_message("No options are available. Please add some using `/add_auto_roulette`.")
        return

    class RemoveOptionSelect(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(label=line, value=f"{i}")
                for i, line in enumerate(lines)
            ]
            super().__init__(placeholder="Select a set to remove...", options=options)

        async def callback(self, interaction: discord.Interaction):
            index = int(self.values[0])
            removed_line = lines.pop(index)
            write_options(FILE_PATH, lines)
            await interaction.response.send_message(f"Removed the option set: `{removed_line}`")

    class RemoveOptionView(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(RemoveOptionSelect())

    await interaction.response.send_message("Select an option set to remove:", view=RemoveOptionView())

# Slash command: add_auto_roulette
@bot.tree.command(name="add_auto_roulette", description="Add a new option set to the file")
@app_commands.describe(option_line="A comma-separated list of options (e.g., yoram,uriel|1,ofek|2)")
async def add_auto_roulette(interaction: discord.Interaction, option_line: str):
    lines = read_options(FILE_PATH)
    lines.append(option_line.strip())
    write_options(FILE_PATH, lines)
    await interaction.response.send_message(f"Added the new option set: `{option_line.strip()}`")

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
        'extractaudio': True, 
        'quiet': True,
        'noplaylist': True,
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
                voice_client.play(source, after=lambda e: asyncio.create_task(leave(interaction)))
                
                # Send a follow-up message indicating the song is now playing
                await interaction.followup.send(f"Now playing: {info['title']}")
            else:
                await interaction.followup.send("Could not extract audio from the given URL.")

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}")

