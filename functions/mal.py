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

mal_profiles = 'data/mal_profile.txt'
currently_watching = 'data/currently_watching.txt'
plan_to_watch = 'data/plan_to_watch.txt'


if not os.path.exists(mal_profiles):
    with open(mal_profiles, 'w') as f:
        pass
if not os.path.exists(currently_watching):
    with open(currently_watching, 'w') as f:
        pass
if not os.path.exists(plan_to_watch):
    with open(plan_to_watch, 'w') as f:
        pass

def read_options(file_path):
    with open(file_path, "r") as file:
        return [line.strip() for line in file.readlines()]

def write_options(file_path, options):
    with open(file_path, "w") as file:
        file.write("\n".join(options))

async def scrape(interaction):
    titles = scrape()

async def mal_menu(interaction: discord.Interaction, action, user: str = None):
    if action.value == "add_user":
        await add_users_mal(interaction, user)
    elif action.value == "view_users":
        await view_users_mal(interaction)
    elif action.value == "remove_user":
        await remove_users_mal(interaction, user)
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

async def update_watching(interaction):
    await interaction.response.send_message(f"Will be updated.")

    users = read_options(mal_profiles)
    titles = []
    for user in users:
        titles.extend(scrape(user, Statuses.CURRENTLY_WATCHING.value))
    write_options(currently_watching, titles)

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
    return titles

    # Quit the driver
    driver.quit()