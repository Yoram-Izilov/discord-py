import requests
from utils.utils import *
from utils.tracing import trace_function
from utils.db import rss_get_all_episodes, rss_update_episode, rss_add_feed, rss_get_series_list
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
    responseJson    = None
    try:
        resp            = requests.post(apiUrl, json=data, timeout=10)
        responseJson    = json.loads(resp.text)
    except (requests.RequestException, ValueError) as e:
        botLogger.error("tormag conversion failed: %s", e)

    # Check if the response contains the magnet entries
    if responseJson and "magnetEntries" in responseJson and responseJson["magnetEntries"]:
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
        message = (responseJson or {}).get('message', 'tormag unreachable')
        formatted_message = (f"Error for {title}: {message} \nhere is the magnet instead :D : \n{magnet_link}")
        await channel.send(formatted_message)
    botLogger.info('finished announcing new episode')


# Task to check for new episodes in saved RSS feed subscriptions
@trace_function
async def check_for_new_episodes(bot):
    botLogger.info('searching for new episodes from the RSS feed')
    feed_entries = fetch_rss_feed()
    saved_entries = await rss_get_all_episodes()

    for feed_entry in feed_entries:
        matching_entry = next(
            (entry for entry in saved_entries if entry["series"] == feed_entry["series"]), None
        )
        if matching_entry:
            saved_pub_date = parse_pub_date(matching_entry["pubDate"])
            new_pub_date = parse_pub_date(feed_entry["pubDate"])

            if new_pub_date > saved_pub_date:
                await rss_update_episode(
                    feed_entry["series"],
                    feed_entry["pubDate"],
                    feed_entry["title"],
                    feed_entry["link"],
                    feed_entry["size"],
                )
                await announce_new_episode(feed_entry["title"], feed_entry["link"], matching_entry["subs"], bot)

    botLogger.info('rss_check_complete')

# The actual task loop
@tasks.loop(hours=1)
async def _run_new_episode_check_logic(bot):
    await check_for_new_episodes(bot)

# Task to check for new anime to add to the RSS feed subscriptions.
@tasks.loop(hours=24)
@trace_function
async def check_for_new_anime(bot):
    channel = bot.get_channel(BOT_CHANNEL_ID)
    update_anime_list_by_status(Statuses.CURRENTLY_WATCHING.value)

    rss_data = fetch_rss_feed()
    existing_series = await rss_get_series_list()
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
            await rss_add_feed(selected_entry)
            await channel.send('I find a treasure: ' + selected_entry['series'] +' ,I added this to the RSS for you ;)')

    botLogger.info('anime_check_complete')

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




