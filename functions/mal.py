
from functions.roulettes import roulette
from functions.roulettes import roulette
from utils.utils import *
from utils.tracing import trace_function
from utils.db import (
    mal_get_users, mal_add_user, mal_remove_user, anime_list_get,
    mal_link_discord, mal_get_username_for_discord,
    mal_snapshot_replace, mal_snapshot_updated_at, mal_activity_record,
)
from utils import anime_api


@trace_function
async def mal_menu(interaction: discord.Interaction, action, user: str = None):
    if action.value == "add_user":
        await add_users_mal(interaction, user)
    elif action.value == "view_users":
        await view_users_mal(interaction)
    elif action.value == "remove_user":
        await remove_users_mal(interaction, user)
    else:
        await interaction.response.send_message(
            embed=make_embed("Invalid option selected.", kind="error"), ephemeral=True
        )

@trace_function
async def anime_list_menu(bot, interaction: discord.Interaction, action, user: str = None):
    if action.value == "update_watching_list":
        await update_anime_list(bot, interaction, Statuses.CURRENTLY_WATCHING.value)
    elif action.value == "update_plantowatch_list":
        await update_anime_list(bot, interaction, Statuses.PLAN_TO_WATCH.value)
    elif action.value == "view_watching_list":
        await view_anime_list(interaction, Statuses.CURRENTLY_WATCHING.value)
    elif action.value == "view_plantowatch_list":
        await view_anime_list(interaction, Statuses.PLAN_TO_WATCH.value)
    else:
        await interaction.response.send_message(
            embed=make_embed("Invalid option selected.", kind="error"), ephemeral=True
        )

@trace_function
async def next_anime(interaction: discord.Interaction):
    anime_list = await anime_list_get(Statuses.PLAN_TO_WATCH.value)
    anime_roulete_string = ",".join(anime_list)
    await roulette(interaction, anime_roulete_string)

@trace_function
async def add_users_mal(interaction, user: str):
    await mal_add_user(user.strip())
    await interaction.response.send_message(
        embed=make_embed(f"Added the new user: {user.strip()}", kind="success")
    )

@trace_function
async def view_users_mal(interaction):
    lines = await mal_get_users()
    await interaction.response.send_message(
        embed=make_embed(f"Users: {', '.join(lines)}", kind="info")
    )

@trace_function
async def remove_users_mal(interaction, user: str):
    await mal_remove_user(user.strip())
    await interaction.response.send_message(
        embed=make_embed(f"Removed the new option set: {user.strip()}", kind="success")
    )

@trace_function
async def update_anime_list(bot, interaction, status):
    await interaction.response.send_message(
        embed=make_embed("Will be updated.", kind="info")
    )

    channel = bot.get_channel(BOT_CHANNEL_ID)
    name    = await update_anime_list_by_status(status)

    await channel.send(
        embed=make_embed(f"Finish to update {name} list.", kind="success")
    )


@trace_function
async def view_anime_list(interaction, status):
    anime_list = await anime_list_get(status)
    if len(anime_list) > 0:
        await interaction.response.send_message(
            embed=make_embed("\n".join(anime_list)[:MAX_LETTERS], kind="info")
        )
    else:
        await interaction.response.send_message(
            embed=make_embed("No anime.", kind="info")
        )


# ---------------------------------------------------------------------------
# Per-user MAL snapshot pipeline (Phase 1)
# ---------------------------------------------------------------------------

SNAPSHOT_STALE_SECONDS = 6 * 60 * 60


@trace_function
async def _refresh_user_snapshot(username: str) -> int:
    """Pull `username`'s full MAL list, replace their snapshot, write activity
    rows for the diff. Returns the entry count fetched (0 = list private/empty)."""
    entries = await anime_api.get_user_list(username)
    if not entries:
        return 0
    diff = await mal_snapshot_replace(username, entries)
    if diff:
        await mal_activity_record([dict(d, username=username) for d in diff])
    return len(entries)


@trace_function
async def _refresh_if_stale(username: str) -> None:
    from datetime import datetime, timezone, timedelta
    ts = await mal_snapshot_updated_at(username)
    if ts is None or ts < datetime.now(tz=timezone.utc) - timedelta(seconds=SNAPSHOT_STALE_SECONDS):
        await _refresh_user_snapshot(username)


@trace_function
async def mal_link(interaction: discord.Interaction, mal_username: str):
    await interaction.response.defer(ephemeral=True)
    mal_username = (mal_username or "").strip()
    if not mal_username:
        await interaction.followup.send(
            embed=make_embed("❌ Please provide your MAL username.", kind="error"),
            ephemeral=True,
        )
        return

    existing = await mal_get_username_for_discord(interaction.user.id)
    if existing and existing.lower() == mal_username.lower():
        await interaction.followup.send(
            embed=make_embed(f"Already linked to **{existing}**.", kind="info"),
            ephemeral=True,
        )
        return

    # Validate the MAL username exists and has a public list by trying a fetch.
    entries = await anime_api.get_user_list(mal_username)
    if not entries:
        await interaction.followup.send(
            embed=make_embed(
                f"❌ Could not load **{mal_username}**'s list. "
                "Username may be misspelled or the list is set to private.",
                kind="error",
            ),
            ephemeral=True,
        )
        return

    await mal_add_user(mal_username)
    linked = await mal_link_discord(mal_username, interaction.user.id)
    if not linked:
        await interaction.followup.send(
            embed=make_embed(
                "❌ Your Discord account is already linked to a different MAL "
                "user. Have an admin unbind it first.",
                kind="error",
            ),
            ephemeral=True,
        )
        return

    diff = await mal_snapshot_replace(mal_username, entries)
    if diff:
        await mal_activity_record([dict(d, username=mal_username) for d in diff])

    await interaction.followup.send(
        embed=make_embed(
            f"✅ Linked to **{mal_username}** — {len(entries)} entries cached.",
            kind="success",
        ),
        ephemeral=True,
    )
