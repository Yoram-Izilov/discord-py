import os
import json
import discord
from config.consts import *

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
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4)

# Get all series name fron the JSON file
def get_json_field_as_array(file_path, field):
    json_data = load_json_data(file_path)
    return [item[field] for item in json_data]

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