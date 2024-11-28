import random
import discord
from utils.utils import *

async def roulette(interaction: discord.Interaction, options: str):
    dict_options    = {}
    # Parse the input options
    for option in options.split(','):
        name, count = process_option(option)
        if name is None:
            continue
        elif name in dict_options:
            dict_options[name] += count
        else:
            dict_options[name] = count

    if len(dict_options.keys()) < 1: # not a single valid choice in roulette
        return await interaction.response.send_message("Insert at least one valid option..")
        
    winner = choose_winner(dict_options.items())
    embed, file = chart_and_annouce(dict_options, winner, interaction.user.name)
    await interaction.response.send_message(embed=embed, file=file)

# Helper functions to read and write to the options file
FILE_PATH = "data/roulette_options.txt"

def read_options(file_path):
    with open(file_path, "r") as file:
        return [line.strip() for line in file.readlines()]

def write_options(file_path, options):
    with open(file_path, "w") as file:
        file.write("\n".join(options))

def parse_options(option_line):
    options = []
    for item in option_line.split(","):
        item = item.strip()
        if "|" in item:
            name, count_str = item.split("|", 1)
            count = int(count_str)
        else:
            name, count = item, 1
        options.append((name.strip(), count))
    return options

def update_options(options, winner):
    updated_options = []
    for name, count in options:
        if name == winner:
            updated_options.append(f"{name}")
        else:
            updated_options.append(f"{name}|{count + 1}")
    return updated_options

async def auto_roulette(interaction: discord.Interaction):
    lines = read_options(FILE_PATH)
    if not lines:
        await interaction.response.send_message("No options are available. Please add some using `/add_auto_roulette`.")
        return
    
    # Create dropdown menu options
    class OptionSelect(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(label=line, value=f"{i}")
                for i, line in enumerate(lines)
            ]
            super().__init__(placeholder="Choose an option set...", options=options)

        async def callback(self, interaction: discord.Interaction):
            index = int(self.values[0])
            option_line = lines[index]
            options = parse_options(option_line)
            
            # Perform roulette logic
            expanded_options = [name for name, count in options for _ in range(count)]
            winner = random.choice(expanded_options)

            # Update options based on the winner
            updated_options = update_options(options, winner)
            lines[index] = ",".join(updated_options)
            write_options(FILE_PATH, lines)

            # Create a pie chart
            counts = {name: count for name, count in options}
            await chart_and_annouce(interaction, expanded_options, counts)

    class OptionSelectView(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(OptionSelect())

    await interaction.response.send_message("Select an option set:", view=OptionSelectView())

async def remove_auto_roulette(interaction: discord.Interaction):
    lines = read_options(FILE_PATH)
    if not lines:
        await interaction.response.send_message("No options are available. Please add some using `/add_auto_roulette`.")
        return

    class RemoveOptionSelect(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(label=line, value=f"{i}")
                for i, line in enumerate(lines)
            ]
            super().__init__(placeholder="Select a set to remove...", options=options)

        async def callback(self, interaction: discord.Interaction):
            index = int(self.values[0])
            removed_line = lines.pop(index)
            write_options(FILE_PATH, lines)
            await interaction.response.send_message(f"Removed the option set: `{removed_line}`")

    class RemoveOptionView(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(RemoveOptionSelect())

    await interaction.response.send_message("Select an option set to remove:", view=RemoveOptionView())

async def add_auto_roulette(interaction: discord.Interaction, option_line: str):
    lines = read_options(FILE_PATH)
    lines.append(option_line.strip())
    write_options(FILE_PATH, lines)
    await interaction.response.send_message(f"Added the new option set: `{option_line.strip()}`")

async def auto_roulette_menu(interaction: discord.Interaction, action, add_option):
    if action.value == "start_roulette":
        await auto_roulette(interaction)
    elif action.value == "add_roulette":
        if add_option is None:
            await interaction.response.send_message("Please provide a string for the new roulette option:", ephemeral=True)
            return
        await add_auto_roulette(interaction, add_option)
    elif action.value == "remove_roulette":
        await remove_auto_roulette(interaction)
    else:
        await interaction.response.send_message("Invalid option selected.", ephemeral=True)
