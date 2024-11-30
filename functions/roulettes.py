import discord
from utils.utils import *
from config.consts import *

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
    if len(dict_options.keys()) < 7: 
        embed, file = chart_and_annouce(dict_options, winner, interaction.user.name)
        await interaction.response.send_message(embed=embed, file=file)
    else:
        await interaction.response.send_message(
            f"The winner is:{winner[RouletteObject.name.value]}"
        )
    return winner[RouletteObject.name.value]

# updates the current auto roulette after roulette
def update_options(options, winner):
    updated_auto_roulette = []
    for option in options.split(','):
        name, count = process_option(option)
        if name == winner:
            updated_auto_roulette.append(f"{name}")
        elif count != 0:
            updated_auto_roulette.append(f"{name}|{count + 1}")
    return updated_auto_roulette

# choosing one from the user saved roulette 
async def auto_roulette(interaction: discord.Interaction):
    lines = load_text_data(AUTO_ROULETTE_PATH)
    if not lines:
        await interaction.response.send_message("No options are available. Please add some using `/roulette`.")
        return
    
    # Create dropdown menu options
    select_menus = create_select_menus(lines)
    async def select_callback(interaction: discord.Interaction):
        selected_roulette = interaction.data['values'][0]
        winner = await roulette(interaction, selected_roulette)
        new_roulette = update_options(selected_roulette, winner) 

        if selected_roulette.strip() not in lines:
            index = next((i for i, line in enumerate(lines) if line == selected_roulette), None)
            lines[index] = ",".join(new_roulette)
            save_text_data(AUTO_ROULETTE_PATH, lines)

    # Create a view for the select menus
    view = discord.ui.View()
    for select_menu in select_menus:
        select_menu.callback = select_callback
        view.add_item(select_menu)

    await interaction.response.send_message("Choose an option from the dropdown.", view=view)

async def remove_auto_roulette(interaction: discord.Interaction):
    lines = load_text_data(AUTO_ROULETTE_PATH)
    if not lines:
        return await interaction.response.send_message("No options are available. Please add some using `/add_auto_roulette`.")
    
    # Create dropdown menu options
    select_menus = create_select_menus(lines)
    async def select_callback(interaction: discord.Interaction):
        selected_roulette = interaction.data['values'][0]
        index = next((i for i, line in enumerate(lines) if line == selected_roulette), None)
        removed_line = lines.pop(index)
        save_text_data(AUTO_ROULETTE_PATH, lines)
        return await interaction.response.send_message(f"Removed the option set: `{removed_line}`")

     # Create a view for the select menus
    view = discord.ui.View()
    for select_menu in select_menus:
        select_menu.callback = select_callback
        view.add_item(select_menu)

    return await interaction.response.send_message("Choose an option from the dropdown.", view=view)

async def add_auto_roulette(interaction: discord.Interaction, option_line: str):
    lines = load_text_data(AUTO_ROULETTE_PATH)
    # Check if the option_line already exists in the file
    if option_line.strip() in lines:
        return await interaction.response.send_message(f"The option set `{option_line.strip()}` already exists.")
    lines.append(option_line.strip())
    save_text_data(AUTO_ROULETTE_PATH, lines)
    return await interaction.response.send_message(f"Added the new option set: `{option_line.strip()}`")

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
