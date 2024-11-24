import io
import random
import textwrap
import matplotlib.pyplot as plt
import discord
from discord import Embed

# create roulette bar chart and announce the winner
async def chart_and_annouce(interaction, expanded_options, counts):
    # Select a random choice and calculate its percentage
    choice = random.choice(expanded_options)
    choice_count = expanded_options.count(choice)
    total_count = len(expanded_options)
    win_percentage = (choice_count / total_count) * 100

    # Generate a pie chart
    labels = list(counts.keys())
    colors = ['#66b3ff', '#ff9999','#99ff99','#ffcc99','#c2c2f0'] # Add more colors as needed

    # Add labels and title
    plt.title(f'Rolling for {interaction.user.name}')

    # Create the bar chart
    chart_width = 2 * len(labels)
    if (chart_width == 2): chart_width = chart_width + 1
    plt.figure(figsize=(chart_width, 6), facecolor="black")
    
    # Dynamically adjust bottom margin based on maximum text height
    max_chars_per_line = int(20)
    max_height = max(len(textwrap.wrap(label, width=max_chars_per_line)) for label in labels)
    margin_bottom = 0.03 + (max_height * 0.03)
    plt.subplots_adjust(bottom=margin_bottom)

    # Loop to draw bars with special border for the selected choice
    for i, label in enumerate(labels):
        # Determine edge color: gold for the chosen one, none for others
        edge_color = 'gold' if label == choice else 'none'
        bar_color = colors[i % len(colors)]
        # Wrap text based on bar width (approximately 10 characters per bar width)
        
        wrapped_label = '\n'.join(textwrap.wrap(label, width=max_chars_per_line))

        # Create the bar with thicker border for winner
        plt.bar(label, counts[label], 
                color=bar_color, 
                edgecolor=edge_color,
                linewidth=1.5 if label == choice else 1)
            
        # Customize label appearance
        if label == choice:
            # For the selected label: bold, white text with matching background
            plt.text(label, -0.03, wrapped_label, 
                    ha='center', va='top',
                    weight='bold', color='white',
                    bbox=dict(facecolor=bar_color, 
                            edgecolor='gold', 
                            pad=2,
                            linewidth=1.5))
        else:
            # For other labels: normal appearance
            plt.text(label, -0.03, wrapped_label, 
                    ha='center', va='top',
                    weight='bold', color='white',
                    bbox=dict(facecolor=bar_color))

    # Remove original x-axis labels to avoid overlap
    plt.gca().set_xticklabels([])

    # Remove the border (spines) around the plot
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)
    plt.gca().spines['left'].set_color('white')
    plt.gca().spines['bottom'].set_color('white')
    plt.gca().patch.set_alpha(0.0)
    # Set the y-axis to percentage
    plt.ylim(0, max(counts.values()) * 1.02)  # Add a little margin on top
    plt.yticks(ticks=[i for i in range(0, max(counts.values()) + 1, 1)],
            labels=[f"{i / total_count * 100:.0f}%" for i in range(0, max(counts.values()) + 1, 1)],
            color='white')

    # Save chart to a BytesIO object
    image_bytes = io.BytesIO()
    plt.savefig(image_bytes, format='png')
    image_bytes.seek(0)

    # Create the embed object
    embed = Embed(
        title="Roulette Result",  # Title of the embed
        description=f'Congratulations! The chosen option is: **{choice}**\n'
                    f'with a chance of **{win_percentage:.2f}%**',
        color=discord.Color.green()  # Optional, you can change the color as you like
    )

    # Add the image to the embed (image_bytes should be the byte data of the image)
    embed.set_image(url="attachment://roulette_result.png")
    # Send the embed message along with the pie chart image
    await interaction.response.send_message(
        embed=embed,  # The embed you created
        file=discord.File(fp=image_bytes, filename="roulette_result.png")  # Attach the image
    )

async def roulette(interaction: discord.Interaction, options: str):
    expanded_options = []
    counts = {}

    # Parse options and expand based on count
    for item in options.split(','):
        item = item.strip()
        if item:  # Check if item is not empty
            if '|' in item:
                name, count_str = item.split('|', 1)
                count = int(count_str) if count_str.isdigit() else 1
            else:
                name, count = item, 1
            expanded_options.extend([name.strip()] * count)

            # Count occurrences of each item for the chart
            counts[name.strip()] = counts.get(name.strip(), 0) + count

    await chart_and_annouce(interaction, expanded_options, counts)

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
