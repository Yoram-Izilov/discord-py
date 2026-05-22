from utils.utils import *
from utils.tracing import trace_function
from utils.db import roulette_load_all, roulette_add, roulette_update, roulette_remove

@trace_function
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
@trace_function
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
@trace_function
async def auto_roulette(interaction: discord.Interaction):
    lines = await roulette_load_all()
    if not lines:
        await interaction.response.send_message("No options are available. Please add some using `/roulette`.")
        return

    # Create dropdown menu options
    select_menus = create_select_menus(lines)
    async def select_callback(interaction: discord.Interaction):
        selected_roulette = interaction.data['values'][0]
        winner = await roulette(interaction, selected_roulette)
        new_roulette = update_options(selected_roulette, winner)
        new_line = ",".join(new_roulette)
        await roulette_update(selected_roulette, new_line)

    # Create a view for the select menus
    view = discord.ui.View()
    for select_menu in select_menus:
        select_menu.callback = select_callback
        view.add_item(select_menu)

    await interaction.response.send_message("Choose an option from the dropdown.", view=view)

@trace_function
async def remove_auto_roulette(interaction: discord.Interaction):
    lines = await roulette_load_all()
    if not lines:
        return await interaction.response.send_message("No options are available. Please add some using `/add_auto_roulette`.")

    # Create dropdown menu options
    select_menus = create_select_menus(lines)
    async def select_callback(interaction: discord.Interaction):
        selected_roulette = interaction.data['values'][0]
        await roulette_remove(selected_roulette)
        return await interaction.response.send_message(f"Removed the option set: `{selected_roulette}`")

     # Create a view for the select menus
    view = discord.ui.View()
    for select_menu in select_menus:
        select_menu.callback = select_callback
        view.add_item(select_menu)

    return await interaction.response.send_message("Choose an option from the dropdown.", view=view)

@trace_function
async def add_auto_roulette(interaction: discord.Interaction, option_line: str):
    inserted = await roulette_add(option_line.strip())
    if not inserted:
        return await interaction.response.send_message(f"The option set `{option_line.strip()}` already exists.")
    return await interaction.response.send_message(f"Added the new option set: `{option_line.strip()}`")

@trace_function
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
