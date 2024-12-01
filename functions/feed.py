from utils.utils import *
from utils.config import *

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

    if len(filtered_series) == 0:
        return await interaction.response.send_message("If you can't spell, DON'T :)")

    initial_text = "Select a series to add to your feed (only one at a time):"
    picked_option = await dropdown_interactions(interaction, filtered_series, initial_text)

    if picked_option:
        selected_entry = next((entry for entry in rss_data if entry['series'] == picked_option), None)
        if selected_entry:
            # Add the selected full entry to the JSON file
            json_data = load_json_data(RSS_FILE_PATH)
            json_data.append(selected_entry)  # Append the entire entry
            save_json_data(RSS_FILE_PATH, json_data)
            return await interaction.followup.send(f'Series "{picked_option}" has been added to the feed!') 
        else:
            return await interaction.followup.send(f'Could not find data for the series "{picked_option}".')
        
# View current rss feeds
async def view_rss(interaction: discord.Interaction, search):
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
async def remove_rss(interaction: discord.Interaction, search):
    series_list = get_json_field_as_array(RSS_FILE_PATH, "series")
    if not series_list:
        return await interaction.response.send_message("No series found to remove.", ephemeral=True)
        
    initial_text = "Select an episode to remove from your feed:"
    picked_option = await dropdown_interactions(interaction, series_list, initial_text)

    if picked_option:
        remove_series(picked_option)
        await interaction.followup.send(f"The series **{picked_option}** has been removed successfully.")

async def sub_to_rss(interaction: discord.Interaction, search):
    user        = interaction.user
    rss_data    = load_json_data(RSS_FILE_PATH)
    series_list = get_json_field_as_array(RSS_FILE_PATH, "series")

    if not series_list:
        return await interaction.response.send_message("No series found to subscribe to :<", ephemeral=True)
    
    initial_text = "Select a series to subscribe to:"
    picked_option = await dropdown_interactions(interaction, series_list, initial_text)

    if picked_option:
        for item in rss_data:
            if item["series"] == picked_option and str(user.id) not in item["subs"]:
                item["subs"].append(str(user.id))  # Update the subs array
                save_json_data(RSS_FILE_PATH,rss_data)
                return await interaction.followup.send(f"Successfully subscribed {user.mention} to {picked_option} RSS feed!") 
            else:
                return await interaction.followup.send(f"Already subscribed to {picked_option} RSS feed!")

async def unsub_from_rss(interaction: discord.Interaction, search):
    user        = interaction.user
    rss_data    = load_json_data(RSS_FILE_PATH)
    series_list = get_json_field_as_array(RSS_FILE_PATH, "series")

    if not series_list:
        return await interaction.response.send_message("No series found to unsub from :<.", ephemeral=True)
    
    initial_text = "Select a series to unsubscribe from:"
    picked_option = await dropdown_interactions(interaction, series_list, initial_text)

    if picked_option:
        # Modify the subs array if series matches
        for item in rss_data:
            if item["series"] == picked_option and str(user.id) in item["subs"]:
                item["subs"].remove(str(user.id))
                save_json_data(RSS_FILE_PATH,rss_data)
                return await interaction.followup.send(f"Successfully removed {user.mention} from {picked_option} RSS feed :( but why?")
            else:
                return await interaction.followup.send(f"Already unsubscribed from {picked_option}")

async def rss_menu(interaction: discord.Interaction, action, search):
    action_map = {
        "add_rss": add_rss,
        "view_rss": view_rss,
        "remove_rss": remove_rss,
        "sub_to_rss": sub_to_rss,
        "unsub_from_rss": unsub_from_rss
    }
    action_func = action_map.get(action.value)

    if action_func:
        await action_func(interaction, search)
    else:
        await interaction.response.send_message("Invalid option selected.", ephemeral=True)