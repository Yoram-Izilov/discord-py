import os
from config.consts import *
import discord, feedparser, json

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# region JSON

# Function to load existing data from the JSON file
def load_json_data(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            try:
                # Try loading JSON data
                return json.load(file)  
            # Handle case where the file is empty or invalid
            except json.JSONDecodeError:  
                return [] # Return an empty list if the file is invalid or empty
    else:
        return [] # Return an empty list if the file does not exist

# Function to save data to the JSON file
def save_json_data(file_path, data):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4)

# Get all series name fron the JSON file
def get_json_field_as_array(file_path, field):
    json_data = load_json_data(file_path)
    return [item[field] for item in json_data]

# endregion

# region Text

# Function to load existing data from the file
def load_text_data(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
                return [line.strip() for line in file.readlines()]
    else:
        return [] # Return an empty list if the file does not exist

# Function to save data to the file
def save_text_data(file_path, data):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write("\n".join(data))

# endregion

# region Discord

# Helper function to sanitize titles for both label and value (ensure length is between 1 and 100)
def sanitize_option(str):
    if len(str) > DROPDOWN_TEXT_MAX_LEN:
        str = str[:DROPDOWN_TEXT_MAX_LEN]
    return str or "Unknown String"

# Creates multiple dropdown menus
def create_select_menus(items):
    menus = []  
    # Loop over the arr and create select menus in chunks of DROPDOWN_MAX_ITEMS
    for i in range(0, len(items), DROPDOWN_MAX_ITEMS):
        options = [
            discord.SelectOption(
                label = item,   # Display the sanitized item name
                value = item    # Use the corresponding item name as the value
            )
            for item in items[i:i + DROPDOWN_MAX_ITEMS]
        ]
        select_menu = discord.ui.Select(placeholder="Choose an item:", options=options)
        menus.append(select_menu)
    return menus

# endregion

# region feed

# Fetch the RSS feed and parse it
def fetch_rss_feed():
    feed = feedparser.parse(RSS_URL)
    return [
        {
            "title": entry.title,
            "link": entry.link,
            "guid": entry.guid,
            "pubDate": entry.published,
            "series": entry.category,
            "size": entry.get("subsplease_size", "N/A")  # Handling custom namespace field
        }
        for entry in feed.entries
    ]

# endregion

# region anime list

def scrape_mal(user, status):
    # Set up Selenium options
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode (no browser window)
    chrome_options.add_argument("--disable-gpu")  # For systems without GPU support
    chrome_options.add_argument("--no-sandbox")

    # Start the WebDriver
    driver = webdriver.Chrome(options=chrome_options)

    # Open the page
    url = MAL_LIST_FORMAT.format(user, status)
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

    # Quit the driver
    driver.quit()

    return titles



def update_anime_list(status):
    file_address = MAL_STATUSES_FORMAT.format(status)

    users = load_text_data(MAL_PROFILE_PATH)
    titles = []

    for user in users:
        titles.extend(scrape_mal(user, status))

    save_text_data(file_address, titles)

    name = Statuses(status).name

    return name
# endregion

