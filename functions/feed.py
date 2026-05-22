from utils.utils import *
from utils.config import *
from utils.tracing import trace_function
from functions.tasks import _run_new_episode_check_logic, announce_new_episode
from utils.db import (
    rss_get_series_list, rss_get_subscribed_series, rss_get_unsubscribed_series,
    rss_get_all_with_subs, rss_add_feed, rss_delete_series,
    rss_subscribe, rss_unsubscribe,
)


@trace_function
async def add_rss(interaction: discord.Interaction, search):
    rss_data = fetch_rss_feed()
    sanitized_rss_data = list(set(sanitize_option(entry['series']) for entry in rss_data))
    existing_series = await rss_get_series_list()
    search = search if search is not None else ""
    filtered_series = [
        s for s in sanitized_rss_data
        if s not in existing_series and search.lower() in s.lower()
    ]

    if not filtered_series:
        return await interaction.response.send_message("If you can't spell, DON'T :)")

    picked_option = await dropdown_interactions(
        interaction, filtered_series, "Select a series to add to your feed (only one at a time):"
    )

    if picked_option:
        selected_entry = next((e for e in rss_data if e['series'] == picked_option), None)
        if selected_entry:
            user = interaction.user
            await rss_add_feed(selected_entry, user_id=user.id)
            await announce_new_episode(selected_entry["title"], selected_entry["link"], [str(user.id)], interaction.client)
            return await interaction.followup.send(f'Series "{picked_option}" has been added to the feed!')
        else:
            return await interaction.followup.send(f'Could not find data for the series "{picked_option}".')


@trace_function
async def view_rss(interaction: discord.Interaction, search):
    user = interaction.user
    all_series = await rss_get_series_list()

    if not all_series:
        await interaction.response.send_message("Your RSS feed is empty.")
        return

    subscribed = await rss_get_subscribed_series(user.id)
    subscribed_set = set(subscribed)
    not_subscribed = [s for s in all_series if s not in subscribed_set]

    message = "**Your RSS Feed:**\n```\n"
    if subscribed:
        message += "SUBSCRIBED:\n" + "\n".join(subscribed)
    if not_subscribed:
        message += ("\n\nNOT SUBSCRIBED:\n" if subscribed else "NOT SUBSCRIBED:\n")
        message += "\n".join(not_subscribed)
    message += "\n```"
    await interaction.response.send_message(message)


@trace_function
async def remove_rss(interaction: discord.Interaction, search):
    series_list = await rss_get_series_list()
    if not series_list:
        return await interaction.response.send_message("No series found to remove.", ephemeral=True)

    picked_option = await dropdown_interactions(
        interaction, series_list, "Select an episode to remove from your feed:"
    )

    if picked_option:
        await rss_delete_series(picked_option)
        await interaction.followup.send(f"The series **{picked_option}** has been removed successfully.")


@trace_function
async def sub_to_rss(interaction: discord.Interaction, search):
    user = interaction.user
    all_series = await rss_get_series_list()

    if not all_series:
        return await interaction.response.send_message("No series found to subscribe to :<", ephemeral=True)

    available_series = await rss_get_unsubscribed_series(user.id)

    if not available_series:
        return await interaction.response.send_message("You are already subscribed to all series!", ephemeral=True)

    picked_option = await dropdown_interactions(
        interaction, available_series, "Select a series to subscribe to:"
    )

    if picked_option:
        subscribed = await rss_subscribe(picked_option, user.id)
        if subscribed:
            return await interaction.followup.send(
                f"Successfully subscribed {user.mention} to {picked_option} RSS feed!"
            )
    return await interaction.followup.send(f"Already subscribed to {picked_option} RSS feed!")


@trace_function
async def unsub_from_rss(interaction: discord.Interaction, search):
    user = interaction.user
    subscribed_series = await rss_get_subscribed_series(user.id)

    if not subscribed_series:
        return await interaction.response.send_message(
            "You are not subscribed to any series!", ephemeral=True
        )

    picked_option = await dropdown_interactions(
        interaction, subscribed_series, "Select a series to unsubscribe from:"
    )

    if picked_option:
        unsubbed = await rss_unsubscribe(picked_option, user.id)
        if unsubbed:
            return await interaction.followup.send(
                f"Successfully removed {user.mention} from {picked_option} RSS feed :( but why?"
            )
    return await interaction.followup.send(f"Already unsubscribed from {picked_option}")


@trace_function
async def all_rss_subscribe(interaction: discord.Interaction, search):
    feeds = await rss_get_all_with_subs()

    if not feeds:
        await interaction.response.send_message("No RSS data found.")
        return

    await interaction.response.defer()

    message = "**All RSS Subscriptions:**\n"
    has_subs = False

    for entry in feeds:
        series = entry["series"]
        subs = entry["subs"]

        if subs:
            has_subs = True
            message += f"\n**{series}**:\n"
            for sub_id in subs:
                try:
                    user = interaction.guild.get_member(int(sub_id))
                    if not user:
                        user = await interaction.client.fetch_user(int(sub_id))
                    user_name = user.display_name if user else f"Unknown User ({sub_id})"
                    message += f"- {user_name}\n"
                except Exception:
                    message += f"- Unknown User ({sub_id})\n"

    if not has_subs:
        await interaction.followup.send("No subscriptions found.")
        return

    if len(message) > 2000:
        with io.BytesIO() as file_buffer:
            file_buffer.write(message.encode('utf-8'))
            file_buffer.seek(0)
            await interaction.followup.send(
                "The list is too long, here is a file:",
                file=discord.File(file_buffer, "subscriptions.txt"),
            )
    else:
        await interaction.followup.send(message)


@trace_function
async def check_rss_feed_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await _run_new_episode_check_logic(interaction.client)
    await interaction.followup.send("RSS feed check initiated and completed!", ephemeral=True)


@trace_function
async def rss_menu(interaction: discord.Interaction, action, search):
    action_map = {
        "add_rss":           add_rss,
        "view_rss":          view_rss,
        "remove_rss":        remove_rss,
        "sub_to_rss":        sub_to_rss,
        "unsub_from_rss":    unsub_from_rss,
        "all_rss_subscribe": all_rss_subscribe,
        "check_rss":         check_rss_feed_command,
    }
    action_func = action_map.get(action.value)

    if action_func:
        if action.value == "check_rss":
            await action_func(interaction)
        else:
            await action_func(interaction, search)
    else:
        await interaction.response.send_message("Invalid option selected.", ephemeral=True)
