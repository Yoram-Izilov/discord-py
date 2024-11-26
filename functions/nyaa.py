import aiohttp
import discord
import urllib.parse
from bs4 import BeautifulSoup

async def search(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    
    base_url = "https://nyaa.si"
    search_url = f"{base_url}/?f=2&c=1_2&q={query.replace(' ', '+')}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(search_url) as response:
            if response.status != 200:
                await interaction.followup.send("Failed to fetch results from Nyaa")
                return
            
            html = await response.text()
            
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.select('table tr')[1:6]  # Skip header row, get next 5
    
    if not rows:
        await interaction.followup.send("No results found")
        return
        
    embed = discord.Embed(title=f"Nyaa Search Results for: {query}", 
                        color=discord.Color.blue(),
                        url=search_url)
                        
    for row in rows:
        cols = row.select('td')
        if len(cols) >= 2:
            title_link = cols[1].select_one('a:not(.comments)')
            title = title_link.text.strip()
            torrent_path = title_link['href']
            magnet_link = cols[2].select_one('a[href^="magnet:?"]')['href']
            size = cols[3].text.strip()
            date = cols[4].text.strip()
            
            # Create formatted links
            torrent_url = f"{base_url}{torrent_path}"
            # Convert magnet to web URL
            magnet_url = f"{base_url}{torrent_path}/magnet"
            
            # Add field for each result
            embed.add_field(
                name=f"📥 {size} | 📅 {date}",
                value=f"```{title[:200]}```\n" + 
                        f"[🔗 Torrent]({torrent_url}) | [🧲 Web Magnet]({magnet_url})",
                inline=False
            )
    
    await interaction.followup.send(embed=embed)