import discord, feedparser, requests, json
from discord.ext import tasks
from datetime import datetime

from utils.utils import *
from config.consts import *

# Fetch the RSS feed and parse it
def fetch_rss_feed():
    feed = feedparser.parse(RSS_URL)
    return [
        {
            "title": entry.title,
            "link": entry.link,
            "guid": entry.guid,
            "pubDate": entry.published,
            "series": entry.category,
            "size": entry.get("subsplease_size", "N/A")  # Handling custom namespace field
        }
        for entry in feed.entries
    ]

# Add rss to json file
async def add_rss(interaction: discord.Interaction, search):
    rss_data = fetch_rss_feed()  # Fetch RSS feed
    # Only sanitize the series name (not the entire dictionary)
    sanitized_rss_data = [sanitize_option(entry['series']) for entry in rss_data]
    sanitized_rss_data = list(set(sanitized_rss_data)) # removes dupes
    # Get the list of existing series from the JSON file
    existing_series = get_json_field_as_array(RSS_FILE_PATH, "series")
    # Filter out series that are already in the JSON file
    search          = search if search is not None else ""
    filtered_series = [series for series in sanitized_rss_data if series not in existing_series and search.lower() in series.lower()]

    select_menus    = create_select_menus(filtered_series)

    async def select_callback(interaction: discord.Interaction):
        selected_series = interaction.data['values'][0]
        # Find the full entry that matches the selected series
        selected_entry = next((entry for entry in rss_data if entry['series'] == selected_series), None)
        if selected_entry:
            # Add the selected full entry to the JSON file
            json_data = load_json_data(RSS_FILE_PATH)
            json_data.append(selected_entry)  # Append the entire entry
            save_json_data(RSS_FILE_PATH, json_data)
            # Respond with a confirmation message
            await interaction.response.send_message(f'Series "{selected_series}" has been added to the feed!')
        else:
            await interaction.response.send_message(f'Could not find data for the series "{selected_series}".')

    # Create a view for the select menus
    view = discord.ui.View()
    for select_menu in select_menus:
        select_menu.callback = select_callback
        view.add_item(select_menu)

    if len(filtered_series) > 0:
        await interaction.response.send_message("Select a series to add to your feed:", view=view)
    else:
        await interaction.response.send_message("If you can't spell, DON'T :)")

# View current rss feeds
async def view_rss(interaction):
    my_series = get_json_field_as_array(RSS_FILE_PATH, "series")
    if not my_series:
        await interaction.response.send_message("Your RSS feed is empty.")
    else:
        rss_list = "\n".join(my_series)
        await interaction.response.send_message(f"Your RSS subscriptions:\n```\n{rss_list}\n```")

# Remove a series from the JSON file
def remove_series(series_to_remove):
    json_data = load_json_data(RSS_FILE_PATH)
    # Remove all items where the series matches the one to delete
    updated_data = [item for item in json_data if item["series"] != series_to_remove]
    save_json_data(RSS_FILE_PATH, updated_data)

# Remove a series from the JSON file
async def remove_rss(interaction):
    series_list = get_json_field_as_array(RSS_FILE_PATH, "series")
    if not series_list:
        await interaction.response.send_message("No series found to remove.", ephemeral=True)
        return

    # take just the series names from the JSON file
    options     = [discord.SelectOption(label=series, value=series) for series in series_list]
    select_menu = discord.ui.Select(placeholder="Choose a series to remove", options=options[:25]) # limit to 25 lines

    async def select_callback(interaction: discord.Interaction):
        selected_series = interaction.data['values'][0]
        remove_series(selected_series)
        await interaction.response.send_message(f"The series **{selected_series}** has been removed successfully.")

    select_menu.callback = select_callback
    view                 = discord.ui.View()
    view.add_item(select_menu)
    await interaction.response.send_message("Select an episode to remove from your feed:", view=view)

# Creates magnet url for the new rss episode
async def announce_new_episode(title, magnet_link, bot):
    channel = bot.get_channel(OTAKU_CHANNEL_ID) 
    # Insert magnet link into API (if required)
    apiUrl          = "https://tormag.ezpz.work/api/api.php?action=insertMagnets"
    data            = { "magnets": [magnet_link] }
    resp            = requests.post(apiUrl, json=data)
    responseJson    = json.loads(resp.text)

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

# Helper function to parse pubDate
def parse_pub_date(date_str):
    return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S +0000")

# Task to check for new episodes in saved RSS feed subscriptions
@tasks.loop(hours=1)
async def check_for_new_episodes(bot):
    feed_entries    = fetch_rss_feed()                  # RSS feed entries from URL
    saved_entries   = load_json_data(RSS_FILE_PATH)    # Current subscriptions from the JSON file

    # Iterate through each feed entry and compare it with saved entries
    for feed_entry in feed_entries:
        # Find the corresponding saved entry by series name and GUID
        matching_entry = next(
            (entry for entry in saved_entries if entry["series"] == feed_entry["series"]), None
        )
        if matching_entry:
            # If the saved entry exists, compare the pubDate to see if it has been updated
            saved_pub_date  = parse_pub_date(matching_entry["pubDate"])
            new_pub_date    = parse_pub_date(feed_entry["pubDate"])

            # If the pubDate is newer, update the saved entry
            if new_pub_date > saved_pub_date:
                # Update the fields (you can add more fields as needed)
                matching_entry["title"]     = feed_entry["title"]
                matching_entry["link"]      = feed_entry["link"]
                matching_entry["pubDate"]   = feed_entry["pubDate"]
                matching_entry["size"]      = feed_entry["size"]
                
                await announce_new_episode(matching_entry["title"], matching_entry["link"], bot)
    # Save the updated subscriptions back to the JSON file
    save_json_data(RSS_FILE_PATH, saved_entries)

async def rss_menu(interaction: discord.Interaction, action, search):
    if action.value     == "add_rss":
        await add_rss(interaction, search)
    elif action.value   == "view_rss":
        await view_rss(interaction)
    elif action.value   == "remove_rss":
        await remove_rss(interaction)
    else:
        await interaction.response.send_message("Invalid option selected.", ephemeral=True)