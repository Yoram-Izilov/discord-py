
from functions.roulettes import roulette
from utils.utils import *


async def mal_menu(interaction: discord.Interaction, action, user: str = None):
    if action.value == "add_user":
        await add_users_mal(interaction, user)
    elif action.value == "view_users":
        await view_users_mal(interaction)
    elif action.value == "remove_user":
        await remove_users_mal(interaction, user)
    else:
        await interaction.response.send_message("Invalid option selected.", ephemeral=True)

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
        await interaction.response.send_message("Invalid option selected.", ephemeral=True)

async def next_anime(interaction: discord.Interaction):
    file_address = MAL_STATUSES_FORMAT.format(Statuses.PLAN_TO_WATCH.value)

    anime_list = load_text_data(file_address)
    anime_roulete_string = ",".join(anime_list)
    await roulette(interaction, anime_roulete_string)

async def add_users_mal(interaction, user: str):
    lines = load_text_data(MAL_PROFILE_PATH)
    lines.append(user.strip())
    save_text_data(MAL_PROFILE_PATH, lines)
    await interaction.response.send_message(f"Added the new user: {user.strip()}")

async def view_users_mal(interaction):
    lines = load_text_data(MAL_PROFILE_PATH)
    await interaction.response.send_message(f"Users: {', '.join(lines)}")

async def remove_users_mal(interaction, user: str):
    lines = load_text_data(MAL_PROFILE_PATH)
    lines.remove(user.strip())
    save_text_data(MAL_PROFILE_PATH, lines)
    await interaction.response.send_message(f"Removed the new option set: {user.strip()}")

async def update_anime_list(bot, interaction, status):
    await interaction.response.send_message(f"Will be updated.")

    channel = bot.get_channel(BOT_CHANNEL_ID)
    name    = update_anime_list_by_status(status)

    await channel.send(f"Finish to update {name} list.")


async def view_anime_list(interaction, status):
    file_address = MAL_STATUSES_FORMAT.format(status)

    anime_list = load_text_data(file_address)
    if len(anime_list) > 0:
        await interaction.response.send_message("\n".join(anime_list)[:MAX_LETTERS])
    else:
        await interaction.response.send_message("No anime.")



