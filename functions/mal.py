import os
from enum import Enum

import discord
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

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
    file_address = MAL_STATUSES_TEMPLATE.substitute(status=Statuses.PLAN_TO_WATCH.value)

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

    file_address = MAL_STATUSES_TEMPLATE.substitute(status=status)

    users = load_text_data(MAL_PROFILE_PATH)
    titles = []

    for user in users:
        titles.extend(scrape(user, status))

    save_text_data(file_address, titles)

    channel = bot.get_channel(BOT_CHANNEL_ID)
    name = Statuses(status).name

    await channel.send(f"Finish to update {name} list.")


async def view_anime_list(interaction, status):
    file_address = MAL_STATUSES_TEMPLATE.substitute(status=status)

    anime_list = load_text_data(file_address)
    if len(anime_list) > 0:
        await interaction.response.send_message("\n".join(anime_list)[:MAX_LETTERS])
    else:
        await interaction.response.send_message("No anime.")


def scrape(user, status):
    # Set up Selenium options
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode (no browser window)
    chrome_options.add_argument("--disable-gpu")  # For systems without GPU support
    chrome_options.add_argument("--no-sandbox")

    # Start the WebDriver
    driver = webdriver.Chrome(options=chrome_options)

    # Open the page
    url = f"https://myanimelist.net/animelist/{user}?status={status}"
    driver.get(url)

    # Wait for the page to load (important for JavaScript-rendered content)
    driver.implicitly_wait(10)  # Adjust time if needed

    # Extract anime titles and additional data
    anime_rows = driver.find_elements(By.CSS_SELECTOR, "tr.list-table-data")
    titles = []
    for row in anime_rows:
        try:
            # Extract title
            title = row.find_element(By.CSS_SELECTOR, "td.title").text.split('\n')[0]
            titles.append(title)
        except Exception as e:
            print(f"Error parsing row: {e}")
    print('Finish scrape.')

    return titles

    # Quit the driver
    driver.quit()
