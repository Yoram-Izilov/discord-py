import os, discord, feedparser, requests, json
from discord.ext import tasks

rss_titles = 'data/rss_feed.txt'                     # File to store RSS feed subscriptions
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
def create_select_menus(all_series_and_guid, current_rss_feed=None):
    # Create sanitized series from the tuples (series, guid)
    if current_rss_feed is None:
        current_rss_feed = []

    sanitized_series_and_guid = [(sanitize_option(series), guid) for series, guid in all_series_and_guid]

    # Filter out series and guid that already exist in current_rss_feed
    sanitized_series_and_guid_filtered = []

    for series, guid in sanitized_series_and_guid:
        if series not in current_rss_feed:
            obj = (series, guid)
            sanitized_series_and_guid_filtered.append(obj)

    menus = []
    max_options = 25  # Discord's limit per select menu
    # Loop over the series and guid tuples in chunks of max_options to create paginated select menus
    for i in range(0, len(sanitized_series_and_guid_filtered), max_options):

        options = [
            discord.SelectOption(
                label=series,  # Display the sanitized series name
                value= f"{series}|RSS|{guid}"  # Use the corresponding GUID as the value
            )
            for series, guid in sanitized_series_and_guid_filtered[i:i + max_options]
        ]
        select_menu = discord.ui.Select(placeholder="Choose an series to add", options=options)
        menus.append(select_menu)
    return menus

# add rss (data taken from subsplease website)
async def add_rss(interaction):
    rss = fetch_rss_feed()  # Fetch RSS feed
    all_series_and_guid = [(entry["series"], entry["guid"]) for entry in rss] # Extract series and guid as tuples
    saved_rss = read_saved_rss()
    saved_rss_filtered = []

    for rss_obj in saved_rss:
        saved_rss_filtered.append(rss_obj.split('|RSS|')[0])

    # Create select menus with sanitized titles and pagination if needed
    select_menus = create_select_menus(all_series_and_guid, saved_rss_filtered)
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

async def view_rss(interaction):
    saved_rss = read_saved_rss()
    if not saved_rss:
        await interaction.response.send_message("Your RSS feed is empty.", ephemeral=True)
    else:
        rss_list = "\n".join(saved_rss)
        await interaction.response.send_message(f"Your RSS subscriptions:\n```\n{rss_list}\n```", ephemeral=True)

async def remove_rss(interaction):
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

async def announce_new_episode(title, magnet_link, bot):
    channel = bot.get_channel(announcement_channel_id) 

    # Insert magnet link into API (if required)
    apiUrl = "https://tormag.ezpz.work/api/api.php?action=insertMagnets"
    data = { "magnets": [magnet_link] }
    resp = requests.post(apiUrl, json=data)
    responseJson = json.loads(resp.text)

    # Check if the response contains the magnet entries
    if "magnetEntries" in responseJson and responseJson["magnetEntries"]:
        magnet_url = responseJson["magnetEntries"][0]  # Get the first magnet URL
        # Format the message with the title as the clickable text
        formatted_message = f"New Episode Available: [{title}]({magnet_url})\n"
        await channel.send(formatted_message)
    else:
        # If no magnet URL is available or URL limit reached, log the error
        formatted_message = (f"Error for {title}: {responseJson.get('message', 'No message in response')} \nhere is the magnet instead :D : \n{magnet_link}")
        await channel.send(formatted_message)

# Task to check for new episodes in saved RSS feed subscriptions
@tasks.loop(hours=1)
async def check_for_new_episodes(bot):
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
                    await announce_new_episode(matching_entry[0], matching_entry[2], bot)
                    # Replace the old title with the new one
                    if line in saved_rss:
                        index = saved_rss.index(line)
                        saved_rss[index] = f"{parts[0]}|RSS|{parts[1]}|RSS|{matching_entry[0]}" 
    write_saved_rss(saved_rss)

async def rss_menu(interaction: discord.Interaction, action):
    if action.value == "add_rss":
        await add_rss(interaction)
    elif action.value == "view_rss":
        await view_rss(interaction)
    elif action.value == "remove_rss":
        await remove_rss(interaction)
    else:
        await interaction.response.send_message("Invalid option selected.", ephemeral=True)
