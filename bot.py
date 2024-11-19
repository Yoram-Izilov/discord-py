import random
import requests
import yt_dlp
import asyncio
import matplotlib.pyplot as plt
import io
import os
import textwrap
import feedparser
import discord
import json
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
from discord import FFmpegPCMAudio
from discord.ext  import commands, tasks
from discord import app_commands
from discord import Embed
# from function.feed import *

# Set up the bot with the required intents and command prefix
intents = discord.Intents.all()
intents.message_content = True  # Required for reading messages
intents.guilds = True  # Required to join voice channels
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()  # Syncs the slash commands with Discord
    print(f'Bot {bot.user} is now online and ready!')
    check_for_new_episodes.start()

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
    plt.figure(figsize=(chart_width, 6), facecolor="black")
    
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
                    ha='center', va='top',
                    weight='bold', color='white',
                    bbox=dict(facecolor=bar_color))

    # Remove original x-axis labels to avoid overlap
    plt.gca().set_xticklabels([])

    # Remove the border (spines) around the plot
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)
    plt.gca().spines['left'].set_color('white')
    plt.gca().spines['bottom'].set_color('white')
    plt.gca().patch.set_alpha(0.0)
    # Set the y-axis to percentage
    plt.ylim(0, max(counts.values()) * 1.02)  # Add a little margin on top
    plt.yticks(ticks=[i for i in range(0, max(counts.values()) + 1, 1)],
            labels=[f"{i / total_count * 100:.0f}%" for i in range(0, max(counts.values()) + 1, 1)],
            color='white')

    # Save chart to a BytesIO object
    image_bytes = io.BytesIO()
    plt.savefig(image_bytes, format='png')
    image_bytes.seek(0)

    # Create the embed object
    embed = Embed(
        title="Roulette Result",  # Title of the embed
        description=f'Congratulations! The chosen option is: **{choice}**\n'
                    f'with a chance of **{win_percentage:.2f}%**',
        color=discord.Color.green()  # Optional, you can change the color as you like
    )

    # Add the image to the embed (image_bytes should be the byte data of the image)
    embed.set_image(url="attachment://roulette_result.png")
    # Send the embed message along with the pie chart image
    await interaction.response.send_message(
        embed=embed,  # The embed you created
        file=discord.File(fp=image_bytes, filename="roulette_result.png")  # Attach the image
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


rss_titles = 'rss_feed.txt'                     # File to store RSS feed subscriptions
rss_url = "https://subsplease.org/rss/?r=1080"  # The URL of the RSS feed
announcement_channel_id = 571380049044045826    # Channel ID where announcements will be sent

# Ensure the RSS file exists
if not os.path.exists(rss_titles):
    with open(rss_titles, 'w') as f:
        pass

# Helper function to sanitize titles for both label and value (ensure length is between 1 and 100)
def sanitize_option(title):
    max_length = 100
    if len(title) > max_length:
        title = title[:max_length]
    return title or "Unknown Title"

# Fetch the RSS feed and parse it
def fetch_rss_feed():
    feed = feedparser.parse(rss_url)
    return [
        {
            "guid": entry.get("id", entry.title),
            "title": entry.title,
            "link": entry.link,
            "series": entry.category
        }
        for entry in feed.entries
    ]

# Read the saved RSS subscriptions
def read_saved_rss():
    with open(rss_titles, 'r') as f:
        # return set(line.strip() for line in f.readlines())
        return [line.strip() for line in f.readlines()]

# Write the RSS subscriptions to the text file
def write_saved_rss(subscriptions):
    with open(rss_titles, 'w') as f:
        for title in subscriptions:
            f.write(f"{title}\n")

# Helper function to sanitize titles for both label and value (ensure length is between 1 and 100)
def sanitize_option(title):
    max_length = 60  # Discord's limit for labels and values
    if len(title) > max_length:
        title = title[:max_length - 3] + '...' # Truncate and append '...' only if truncation happens
    if len(title) < 1:
        title = "Invalid Title" # Provide a default fallback for invalid titles
    return title

# Helper function to create select menus with sanitized titles and GUIDs as values
def create_select_menus(all_series_and_guid):
    # Create sanitized series from the tuples (series, guid)
    sanitized_series_and_guid = [(sanitize_option(series), guid) for series, guid in all_series_and_guid]
    menus = []
    max_options = 25  # Discord's limit per select menu
    # Loop over the series and guid tuples in chunks of max_options to create paginated select menus
    for i in range(0, len(sanitized_series_and_guid), max_options):
        options = [
            discord.SelectOption(
                label=series,  # Display the sanitized series name
                value= f"{series}|RSS|{guid}"  # Use the corresponding GUID as the value
            )
            for series, guid in sanitized_series_and_guid[i:i + max_options]
        ]
        select_menu = discord.ui.Select(placeholder="Choose an series to add", options=options)
        menus.append(select_menu)
    return menus

# Command to add an episode to the RSS feed
@bot.tree.command(name="add_rss", description="Add an episode to your RSS feed")
async def add_rss(interaction: discord.Interaction):
    rss = fetch_rss_feed()  # Fetch RSS feed
    all_series_and_guid = [(entry["series"], entry["guid"]) for entry in rss] # Extract series and guid as tuples

    # Create select menus with sanitized titles and pagination if needed
    select_menus = create_select_menus(all_series_and_guid )
    async def select_callback(interaction: discord.Interaction):
        value = interaction.data['values'][0]  # Ensure we access 'values' as a dictionary key
        series, guid = value.split("|RSS|") 

        saved_rss = read_saved_rss()
        # Check if the value is already part of any line in saved_rss
        if any(value in line for line in saved_rss):
            await interaction.response.send_message(f"'{series}' is already in your RSS feed. No changes made.", ephemeral=True)
        else:
            # Append new value and save if it's not already present
            new_value = value + "|RSS| new rss episode after scan"
            saved_rss.append(new_value)
            write_saved_rss(saved_rss)
            await interaction.response.send_message(f"Added '{series}' to your RSS feed.", ephemeral=True)

    # Create a view for the select menus
    view = discord.ui.View()
    for select_menu in select_menus:
        select_menu.callback = select_callback
        view.add_item(select_menu)

    await interaction.response.send_message("Select an episode to add to your feed:", view=view)

# Command to view all saved RSS subscriptions
@bot.tree.command(name="view_rss", description="View all your saved RSS subscriptions")
async def view_rss(interaction: discord.Interaction):
    saved_rss = read_saved_rss()
    if not saved_rss:
        await interaction.response.send_message("Your RSS feed is empty.", ephemeral=True)
    else:
        rss_list = "\n".join(saved_rss)
        await interaction.response.send_message(f"Your RSS subscriptions:\n```\n{rss_list}\n```", ephemeral=True)

# Command to remove an episode from the RSS feed
@bot.tree.command(name="remove_rss", description="Remove an episode from your RSS feed")
async def remove_rss(interaction: discord.Interaction):
    saved_rss = read_saved_rss()
    if not saved_rss:
        await interaction.response.send_message("Your RSS feed is empty. No series to remove.", ephemeral=True)
        return

    options = []
    for line in saved_rss:
        title = line.split("|RSS|")[0]
        options.append(discord.SelectOption(label=title))

    select_menu = discord.ui.Select(placeholder="Choose a series to remove", options=options[:25]) # limit to 25 lines

    async def select_callback(interaction: discord.Interaction):
        title = select_menu.values[0]
        saved_rss = read_saved_rss()
        saved_rss = {line for line in saved_rss if title not in line}
        write_saved_rss(saved_rss)
        await interaction.response.send_message(f"Removed '{title}' from your RSS feed.", ephemeral=True)

    select_menu.callback = select_callback

    view = discord.ui.View()
    view.add_item(select_menu)
    await interaction.response.send_message("Select an episode to remove from your feed:", view=view)

async def announce_new_episode(title, magnet_link):
    channel = bot.get_channel(announcement_channel_id) 

    # Insert magnet link into API (if required)
    apiUrl = "https://tormag.ezpz.work/api/api.php?action=insertMagnets"
    data = { "magnets": [magnet_link] }
    resp = requests.post(apiUrl, json=data)
    responseJson = json.loads(resp.text)

    # Check if the response contains the magnet entries
    if "magnetEntries" in responseJson and responseJson["magnetEntries"]:
        magnet_url = responseJson["magnetEntries"][0]  # Get the first magnet URL
        print("hello")
        # Format the message with the title as the clickable text
        formatted_message = f"New Episode Available: [{title}]({magnet_url})\n"
        await channel.send(formatted_message)
    else:
        print('not hello')
        # If no magnet URL is available or URL limit reached, log the error
        formatted_message = (f"Error for {title}: {responseJson.get('message', 'No message in response')} \nhere is the magnet instead :D : \n{magnet_link}")
        await channel.send(formatted_message)

# Task to check for new episodes in saved RSS feed subscriptions
@tasks.loop(hours=1)
async def check_for_new_episodes():
    feed_entries = fetch_rss_feed()  # RSS feed entries from URL
    saved_rss = read_saved_rss()     # my RSS
    
    for line in saved_rss:
        # Split the line by "|RSS|" to extract title and GUID
        parts = line.split("|RSS|")
        if len(parts) == 3:  # Ensure there are exactly two parts: title and GUID
            episode_title = parts[2].strip()
            guid = parts[1].strip()  # The GUID is after "|RSS|"

            all_titles_and_guid = [(entry["title"], entry["guid"], entry["link"]) for entry in feed_entries] 
            # Check if the GUID exists in all_titles_and_guid and compare titles
            matching_entry = next((entry for entry in all_titles_and_guid if entry[1] == guid), None)
            if matching_entry:
                # If GUID matches, check if titles don't match
                if matching_entry[0] != episode_title:
                    await announce_new_episode(matching_entry[0], matching_entry[2])
                    # Replace the old title with the new one
                    if line in saved_rss:
                        index = saved_rss.index(line)
                        saved_rss[index] = f"{parts[0]}|RSS|{parts[1]}|RSS|{matching_entry[0]}" 
    write_saved_rss(saved_rss)
     
@bot.tree.command(name="nyaa", description="Search for torrents on Nyaa")
async def search(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    
    base_url = "https://nyaa.si"
    search_url = f"{base_url}/?f=2&c=1_2&q={query.replace(' ', '+')}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(search_url) as response:
            if response.status != 200:
                await interaction.followup.send("Failed to fetch results from Nyaa")
                return
            
            html = await response.text()
            
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.select('table tr')[1:6]  # Skip header row, get next 5
    
    if not rows:
        await interaction.followup.send("No results found")
        return
        
    embed = discord.Embed(title=f"Nyaa Search Results for: {query}", 
                        color=discord.Color.blue(),
                        url=search_url)
                        
    for row in rows:
        cols = row.select('td')
        if len(cols) >= 2:
            title_link = cols[1].select_one('a:not(.comments)')
            title = title_link.text.strip()
            torrent_path = title_link['href']
            magnet_link = cols[2].select_one('a[href^="magnet:?"]')['href']
            size = cols[3].text.strip()
            date = cols[4].text.strip()
            
            # Create formatted links
            torrent_url = f"{base_url}{torrent_path}"
            # Convert magnet to web URL
            encoded_magnet = urllib.parse.quote(magnet_link)
            web_magnet = f"https://magnet2torrent.com/upload/magnet/?magnet={encoded_magnet}"
            
            # Add field for each result
            embed.add_field(
                name=f"📥 {size} | 📅 {date}",
                value=f"```{title[:200]}```\n" + 
                        f"[🔗 Torrent]({torrent_url}) | [🧲 Web Magnet]({web_magnet})",
                inline=False
            )
    
    await interaction.followup.send(embed=embed)
    
# async def search(interaction: discord.Interaction, query: str):
#     await interaction.response.defer()
    
#     base_url = "https://nyaa.si"
#     search_url = f"{base_url}/?f=2&c=1_2&q={query.replace(' ', '+')}"
    
#     async with aiohttp.ClientSession() as session:
#         async with session.get(search_url) as response:
#             if response.status != 200:
#                 await interaction.followup.send("Failed to fetch results from Nyaa")
#                 return
            
#             html = await response.text()
            
#     soup = BeautifulSoup(html, 'html.parser')
#     rows = soup.select('table tr')[1:6]  # Skip header row, get next 5
    
#     if not rows:
#         await interaction.followup.send("No results found")
#         return
        
#     embed = discord.Embed(title=f"Nyaa Search Results for: {query}", 
#                         color=discord.Color.blue(),
#                         url=search_url)
                        
#     for row in rows:
#         cols = row.select('td')
#         if len(cols) >= 2:
#             title_link = cols[1].select_one('a:not(.comments)')
#             title = title_link.text.strip()
#             torrent_path = title_link['href']
#             magnet_link = cols[2].select_one('a[href^="magnet:?"]')['href']
#             size = cols[3].text.strip()
#             date = cols[4].text.strip()
            
#             # Create formatted links
#             torrent_url = f"{base_url}{torrent_path}"
            
#             # Add field for each result
#             embed.add_field(
#                 name=f"📥 {size} | 📅 {date}",
#                 value=f"```{title[:200]}```\n" + 
#                         f"[🔗 Torrent]({torrent_url}) | [🧲 Magnet]({magnet_link})",
#                 inline=False
#             )
    
#     await interaction.followup.send(embed=embed)
