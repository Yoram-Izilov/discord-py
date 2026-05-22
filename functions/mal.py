
from functions.roulettes import roulette
from functions.roulettes import roulette
from utils.utils import *
from utils.tracing import trace_function
from utils.db import mal_get_users, mal_add_user, mal_remove_user, anime_list_get


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
