import os
from enum import Enum

import discord
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

class Statuses(Enum):
    ALL_ANIME = 0
    CURRENTLY_WATCHING = 1
    COMPLETED = 2
    ON_HOLD = 3
    DROPPED = 4
    PLAN_TO_WATCH = 6

bot_channel_id = 571462116612112384    # Channel ID where announcements will be sent

mal_profiles = 'data/mal_profile.txt'
currently_watching = f'data/anime_list/{Statuses.CURRENTLY_WATCHING.value}.txt'
plan_to_watch = f'data/anime_list/{Statuses.PLAN_TO_WATCH.value}.txt'
files = [mal_profiles, currently_watching, plan_to_watch]

def check_if_file_exist(file_path):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            pass

for file in files:
    check_if_file_exist(file)

def read_options(file_path):
    with open(file_path, "r", encoding='utf-8') as file:
        return [line.strip() for line in file.readlines()]

def write_options(file_path, options):
    with open(file_path, "w", encoding='utf-8') as file:
        file.write("\n".join(options))

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

async def add_users_mal(interaction, user: str):
    lines = read_options(mal_profiles)
    lines.append(user.strip())
    write_options(mal_profiles, lines)
    await interaction.response.send_message(f"Added the new user: `{user.strip()}`")

async def view_users_mal(interaction):
    lines = read_options(mal_profiles)
    await interaction.response.send_message(f"Users: `{", ".join(lines)}`")

async def remove_users_mal(interaction, user: str):
    lines = read_options(mal_profiles)
    lines.remove(user.strip())
    write_options(mal_profiles, lines)
    await interaction.response.send_message(f"Removed the new option set: `{user.strip()}`")

async def update_anime_list(bot, interaction, status):
    await interaction.response.send_message(f"Will be updated.")

    file_address = f'data/anime_list/{status}.txt'
    users = read_options(mal_profiles)
    titles = []

    for user in users:
        titles.extend(scrape(user, status))

    write_options(file_address, titles)

    channel = bot.get_channel(bot_channel_id)
    name = Statuses(status).name

    await channel.send(f"Finish to update {name} list.")


async def view_anime_list(interaction, status):
    max_letters = 2000
    file_address = f'data/anime_list/{status}.txt'
    anime_list = read_options(file_address)
    if len(anime_list) > 0:
        await interaction.response.send_message("\n".join(anime_list)[:max_letters])
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