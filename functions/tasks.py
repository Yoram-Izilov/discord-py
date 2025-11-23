import requests
from utils.utils import *
from utils.tracing import trace_function
from fuzzywuzzy import fuzz
from datetime import datetime
from discord.ext import tasks
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

# Helper function to parse pubDate
@trace_function
def parse_pub_date(date_str):
    return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S +0000")

# Creates magnet url for the new rss episode
@trace_function
async def announce_new_episode(title, magnet_link, subs, bot):
    channel = bot.get_channel(OTAKU_CHANNEL_ID)
    # Insert magnet link into API (if required)
    apiUrl          = "https://tormag.ezpz.work/api/api.php?action=insertMagnets"
    data            = { "magnets": [magnet_link] }
    resp            = requests.post(apiUrl, json=data)
    responseJson    = json.loads(resp.text)

    # Check if the response contains the magnet entries
    if "magnetEntries" in responseJson and responseJson["magnetEntries"]:
        magnet_url = responseJson["magnetEntries"][0]  # Get the first magnet URL
        # Format the title as the clickable text and mention all subscribers
        formatted_message = f"New Episode Available: [{title}]({magnet_url})\n"
        # Mention all the users
        user_mentions = " ".join([f"<@{user_id}>" for user_id in subs])
        # Add the mentions to the formatted message
        formatted_message += f"\n{user_mentions}"
        await channel.send(formatted_message)
    else:
        # If no magnet URL is available or URL limit reached, log the error
        formatted_message = (f"Error for {title}: {responseJson.get('message', 'No message in response')} \nhere is the magnet instead :D : \n{magnet_link}")
        await channel.send(formatted_message)

# Task to check for new episodes in saved RSS feed subscriptions
@tasks.loop(hours=1)
@trace_function
async def check_for_new_episodes(bot):
    botLogger.info('searching for new episodes from the RSS feed')
    feed_entries = fetch_rss_feed()  # RSS feed entries from URL
    saved_entries = load_json_data(RSS_FILE_PATH)  # Current subscriptions from the JSON file

    # Iterate through each feed entry and compare it with saved entries
    for feed_entry in feed_entries:
        # Find the corresponding saved entry by series name
        matching_entry = next(
            (entry for entry in saved_entries if entry["series"] == feed_entry["series"]), None
        )
        if matching_entry:
            # If the saved entry exists, compare the pubDate to see if it has been updated
            saved_pub_date = parse_pub_date(matching_entry["pubDate"])
            new_pub_date = parse_pub_date(feed_entry["pubDate"])

            # If the pubDate is newer, update the saved entry
            if new_pub_date > saved_pub_date:
                # Update the fields (you can add more fields as needed)
                matching_entry["pubDate"]   = feed_entry["pubDate"]
                matching_entry["title"]     = feed_entry["title"]
                matching_entry["link"]      = feed_entry["link"]
                matching_entry["size"]      = feed_entry["size"]

                await announce_new_episode(matching_entry["title"], matching_entry["link"], matching_entry["subs"], bot)
    # Save the updated subscriptions back to the JSON file
    save_json_data(RSS_FILE_PATH, saved_entries)


# Task to check for new anime to add to the RSS feed subscriptions.
@tasks.loop(hours=24)
@trace_function
async def check_for_new_anime(bot):
    channel = bot.get_channel(BOT_CHANNEL_ID)
    update_anime_list_by_status(Statuses.CURRENTLY_WATCHING.value)

    rss_data = fetch_rss_feed()
    existing_series = get_json_field_as_array(RSS_FILE_PATH, "series")
    feed_names = list(map(lambda x: x["series"], rss_data))
    filtered_series = [series for series in feed_names if series not in existing_series]
    filtered_series = list(map(lambda x: x.strip().lower(), filtered_series))
    filtered_series = list(set(filtered_series))

    currently_watching = load_text_data(MAL_STATUSES_FORMAT.format(Statuses.CURRENTLY_WATCHING.value))
    currently_watching_airing = [x[:-6].strip().lower() for x in currently_watching if x.endswith('Airing')]
    currently_watching_airing = list(set(currently_watching_airing))
    similarity_list = []
    for rss_anime in filtered_series:
        for canime in currently_watching_airing:
            if string_similar(canime, rss_anime[:-6].strip()):
                similarity_list.append(rss_anime)
    for anime in similarity_list:
        selected_entry = next((entry for entry in rss_data if entry['series'].strip().lower() == anime), None)
        if selected_entry:
            # Add the selected full entry to the JSON file
            json_data = load_json_data(RSS_FILE_PATH)
            json_data.append(selected_entry)  # Append the entire entry
            save_json_data(RSS_FILE_PATH, json_data)

            await channel.send('I find a treasure: ' + selected_entry['series'] +' ,I added this to the RSS for you ;)')

@trace_function
def fuzz_similarity(str1, str2):
    similarity = fuzz.ratio(str1, str2) / 100
    return  similarity

@trace_function
def vector_similarity(str1, str2):
    vectorizer = TfidfVectorizer()
    vectors = vectorizer.fit_transform([str1, str2])
    similarity = cosine_similarity(vectors[0], vectors[1])

    return similarity[0][0]

@trace_function
def string_similar(str1, str2):
    return fuzz_similarity(str1, str2) > 0.85 or vector_similarity(str1, str2) > 0.37




