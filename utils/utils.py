from functools import reduce
import os
import random
import io
from discord import Embed
import textwrap
import matplotlib.pyplot as plt

from config.consts import *
import feedparser, json
import discord
import asyncio

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

from utils.logger import botLogger
from utils.tracing import trace_function


# region JSON

# Function to load existing data from the JSON file
@trace_function
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
@trace_function
def save_json_data(file_path, data):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4)

# Get all series name fron the JSON file
@trace_function
def get_json_field_as_array(file_path, field):
    json_data = load_json_data(file_path)
    return [item[field] for item in json_data]

# endregion

# region Text

# Function to load existing data from the file
@trace_function
def load_text_data(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
                return [line.strip() for line in file.readlines()]
    else:
        return [] # Return an empty list if the file does not exist

# Function to save data to the file
@trace_function
def save_text_data(file_path, data):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write("\n".join(data))

# endregion

# region Discord

# Helper function to sanitize titles for both label and value (ensure length is between 1 and 100)
@trace_function
def sanitize_option(str):
    if len(str) > DROPDOWN_TEXT_MAX_LEN:
        str = str[:DROPDOWN_TEXT_MAX_LEN]
    return str or "Unknown String"

# Creates multiple dropdown menus
@trace_function
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

# returns the user selected item from the menu
@trace_function
async def select_callback(interaction: discord.Interaction, user_choice: asyncio.Future):
    selected_value = interaction.data['values'][0]
    if not user_choice.done():
        user_choice.set_result(selected_value)
    await interaction.response.defer()  # Acknowledge the interaction

# returns user selected option from dropdown user interaction
@trace_function
async def dropdown_interactions(interaction: discord.Interaction, list, initial_text):
    # creete the dropdown menus from list 
    select_menus = create_select_menus(list)

    # Create a view for the select menus
    view = discord.ui.View()
    # Create an asyncio Future to store the result of the selection
    user_choice = asyncio.Future()
    for select_menu in select_menus:
        select_menu.callback = lambda interaction: select_callback(interaction, user_choice)
        view.add_item(select_menu)

    await interaction.response.send_message(initial_text, view=view)
    return await user_choice

# endregion

# region feed

# Fetch the RSS feed and parse it
@trace_function
def fetch_rss_feed():
    feed = feedparser.parse(RSS_URL)
    return [
        {
            "title": entry.title,
            "link": entry.link,
            "guid": entry.guid,
            "pubDate": entry.published,
            "series": entry.category,
            "size": entry.get("subsplease_size", "N/A"),  # Handling custom namespace field
            "subs": [] # List of users who have subscribed
        }
        for entry in feed.entries
    ]

# endregion

# region anime list

@trace_function
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
            botLogger.error(f"Error parsing row: {e}")

    botLogger.info(f'Finish scrape user: {user} with status: {status}')

    # Quit the driver
    driver.quit()

    return titles


@trace_function
def update_anime_list_by_status(status):
    file_address = MAL_STATUSES_FORMAT.format(status)

    users = load_text_data(MAL_PROFILE_PATH)
    titles = []

    for user in users:
        titles.extend(scrape_mal(user, status))

    save_text_data(file_address, titles)

    name = Statuses(status).name

    return name
# endregion

# region Roulette

# Helper function to handle individual options
@trace_function
def process_option(option):
    option = option.strip()
    if option is None or option == "":
        return None, 0
    # Split by the first '|' and handle count
    if '|' in option:
        name, count_str = option.split('|', 1)
        name = name.strip()
        if name is None or name == "":
            return None, 0
        try:
            count = int(count_str) if count_str.isdigit() else 1
        except ValueError:
            count = 1
    else:
        name = option
        count = 1 
    return name.strip(), count

# choose a winner based on % (gets [(name, count)])   
@trace_function
def choose_winner(arr):
    # total options in roullete 
    total_sum = reduce(lambda x,y: x + y, map(lambda x:x[1], arr))
    # Generate a random number between 1 and total_sum
    random_number = random.randint(1, total_sum)
    # Find the winner based on the random number
    for name, count in arr:
        if random_number <= count:
           return name, count
        random_number -= count

# create roulette bar chart and announce the winner
@trace_function
def chart_and_annouce(dict_options, winner, username):
    total_count = reduce(lambda x,y: x + y, dict_options.values())
    win_percentage = (winner[RouletteObject.count.value] / total_count) * 100
    
    # Generate a pie chart
    labels = list(dict_options.keys())
    # Add labels and title
    plt.title(f'Rolling for {username}')

    # Create the bar chart
    chart_width = 2 * len(labels)
    if (chart_width == 2): chart_width = chart_width + 1
    plt.figure(figsize=(chart_width, 7))
    
    # Dynamically adjust bottom margin based on maximum text height
    max_height = max(len(textwrap.wrap(label, width=MAX_BAR_CHAR)) for label in labels)
    margin_bottom = 0.03 + (max_height * 0.03)
    plt.subplots_adjust(bottom=margin_bottom)

    # Loop to draw bars with special border for the selected choice
    for i, label in enumerate(labels):
        bar_color = CHART_BAR_COLORS[i % len(CHART_BAR_COLORS)]
        # Wrap text based on bar width (approximately 10 characters per bar width)
        wrapped_label = '\n'.join(textwrap.wrap(label, width=MAX_BAR_CHAR))

        plt.bar(label, dict_options[label], 
                color=WINNER_COLOR
                    if label == winner[RouletteObject.name.value]
                    else bar_color,
                linewidth=1.5)
        
        # For the selected label: bold, white text with matching background
        plt.text(label, -0.03, wrapped_label, 
                ha='center', va='top', fontsize=14,
                weight='bold', color='black',
                bbox=dict(
                    facecolor=WINNER_COLOR
                    if label == winner[RouletteObject.name.value]
                    else bar_color))

    # Remove original x-axis labels to avoid overlap
    plt.gca().set_xticklabels([])
    # Remove the border (spines) around the plot
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)
    plt.gca().spines['left'].set_color('white')
    plt.gca().spines['bottom'].set_color('white')
    plt.gca().patch.set_alpha(0.0)
    # Set the y-axis to percentage
    plt.ylim(0, max(dict_options.values()) * 1.02)  # Add a little margin on top
    plt.yticks(ticks=[i for i in range(0, max(dict_options.values()) + 1, 1)],
            labels=[f"{i / total_count * 100:.0f}%" for i in range(0, max(dict_options.values()) + 1, 1)],
            color='white')

    # Save chart to a BytesIO object
    image_bytes = io.BytesIO()
    plt.savefig(image_bytes, format='png', transparent=True)
    image_bytes.seek(0)

    # Create the embed object
    embed = Embed(
        title="Roulette Result",  # Title of the embed
        description=f'Congratulations! The chosen option is: **{winner[RouletteObject.name.value]}**\n'
                    f'with a chance of **{win_percentage:.2f}%**',
        color=discord.Color.green()  # Optional, you can change the color as you like
    )

    # Add the image to the embed (image_bytes should be the byte data of the image)
    embed.set_image(url="attachment://roulette_result.png")
    file = discord.File(fp=image_bytes, filename="roulette_result.png") 
    # Send the embed message along with the pie chart image
    return embed, file 

# endregion
