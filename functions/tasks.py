import requests
from utils.utils import *
from utils.tracing import trace_function
from utils.db import (
    rss_get_all_episodes, rss_update_episode, rss_add_feed, rss_get_series_list,
    episode_announcement_record,
    mal_get_users, mal_get_discord_for_username, mal_snapshot_get,
    mal_activity_episodes_by_month, mal_activity_leaderboard, mal_alltime_leader,
)
from fuzzywuzzy import fuzz
from datetime import datetime, timezone, timedelta
from discord.ext import tasks
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

# Helper function to parse pubDate
@trace_function
def parse_pub_date(date_str):
    return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S +0000")

# Creates magnet url for the new rss episode
@trace_function
async def announce_new_episode(title, magnet_link, subs, bot, series=None):
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

    sent_message = None
    # Check if the response contains the magnet entries
    if responseJson and "magnetEntries" in responseJson and responseJson["magnetEntries"]:
        magnet_url = responseJson["magnetEntries"][0]  # Get the first magnet URL
        # Mentions live in `content` so they actually ping subscribers; the embed is just the formatted link
        user_mentions = " ".join([f"<@{user_id}>" for user_id in subs])
        embed = make_embed(f"New Episode Available: [{title}]({magnet_url})", kind="success")
        sent_message = await channel.send(content=user_mentions, embed=embed)
    else:
        # If no magnet URL is available or URL limit reached, log the error
        message = (responseJson or {}).get('message', 'tormag unreachable')
        formatted_message = (f"Error for {title}: {message} \nhere is the magnet instead :D : \n{magnet_link}")
        await channel.send(embed=make_embed(formatted_message, kind="error"))

    if sent_message is not None and series:
        # Map the announcement message back to its series so an on_raw_reaction_add
        # listener can resolve series for reaction-based subscription.
        await episode_announcement_record(sent_message.id, series)

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
                await announce_new_episode(
                    feed_entry["title"],
                    feed_entry["link"],
                    matching_entry["subs"],
                    bot,
                    series=feed_entry["series"],
                )

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
    await update_anime_list_by_status(Statuses.CURRENTLY_WATCHING.value)

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
            await channel.send(
                embed=make_embed(
                    'I find a treasure: ' + selected_entry['series'] + ' ,I added this to the RSS for you ;)',
                    kind="success",
                )
            )

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


# ---------------------------------------------------------------------------
# Phase 5: per-user snapshot refresh + leaderboard + milestone announcements
# ---------------------------------------------------------------------------

MONTHLY_EPISODES_MILESTONE = 100


async def _user_mention_or_name(username: str) -> str:
    discord_id = await mal_get_discord_for_username(username)
    return f"<@{discord_id}>" if discord_id else f"**{username}**"


async def _monthly_total(username: str) -> int:
    months = await mal_activity_episodes_by_month(username, months=1)
    return sum(v for _, v in months) if months else 0


@tasks.loop(hours=6)
@trace_function
async def refresh_all_mal_snapshots(bot):
    """Refresh every linked user's MAL snapshot and emit milestone announcements
    from each diff. Runs every 6h."""
    # Lazy import - functions/mal.py imports from this module, so a top-level
    # import would be circular.
    from functions.mal import _refresh_user_snapshot

    channel = bot.get_channel(OTAKU_CHANNEL_ID)
    users = await mal_get_users()
    botLogger.info("refresh_all_mal_snapshots: %d users", len(users))

    for username in users:
        try:
            # First-ingest guard: if we have no snapshot for this user yet, the
            # diff returned by _refresh_user_snapshot below treats every entry
            # as a status change (mal_id not in old → status_changed=True),
            # which would fire a milestone for every completed anime they own.
            # Skip milestone emission on the run that populates the snapshot.
            prior_snapshot = await mal_snapshot_get(username)
            is_first_ingest = not prior_snapshot

            prev_monthly = 0 if is_first_ingest else await _monthly_total(username)
            diff = await _refresh_user_snapshot(username)
            if not diff:
                continue

            if is_first_ingest:
                botLogger.info(
                    "refresh_all_mal_snapshots: first ingest for %s, "
                    "suppressing %d milestone events",
                    username, len(diff),
                )
                continue

            new_monthly = await _monthly_total(username)
            mention = await _user_mention_or_name(username)

            if channel is not None:
                for d in diff:
                    if d.get("new_status") == Statuses.COMPLETED.value:
                        await channel.send(
                            embed=make_embed(
                                f"🎉 {mention} finished **{d['title']}**!",
                                kind="success",
                            )
                        )

                if prev_monthly < MONTHLY_EPISODES_MILESTONE <= new_monthly:
                    await channel.send(
                        embed=make_embed(
                            f"🔥 {mention} just hit **{new_monthly}** episodes this month!",
                            kind="success",
                        )
                    )
        except Exception as e:
            botLogger.error(
                "refresh_all_mal_snapshots failed for %s: %s",
                username, e, exc_info=True,
            )

    botLogger.info("refresh_all_mal_snapshots: done")


@tasks.loop(hours=168)
@trace_function
async def weekly_leaderboard(bot):
    """Post a weekly podium of top episode-watchers + an all-time leader footer."""
    channel = bot.get_channel(OTAKU_CHANNEL_ID)
    if channel is None:
        botLogger.warning("weekly_leaderboard: OTAKU channel not found")
        return

    week_ago = datetime.now(tz=timezone.utc) - timedelta(days=7)
    top = await mal_activity_leaderboard(since=week_ago)
    alltime = await mal_alltime_leader()

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    lines: list[str] = []
    if top:
        for i, (username, total) in enumerate(top[:5]):
            mention = await _user_mention_or_name(username)
            lines.append(f"{medals[i]} {mention} - **{total}** episodes")
    else:
        lines.append("_No tracked MAL activity this week._")

    if alltime:
        alltime_mention = await _user_mention_or_name(alltime[0])
        lines.append("")
        lines.append(f"_All-time leader: {alltime_mention} with **{alltime[1]:,}** episodes_")

    await channel.send(
        embed=make_embed(
            "\n".join(lines),
            kind="info",
            title="📊 Weekly anime leaderboard",
        )
    )




