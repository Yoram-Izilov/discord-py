import asyncio
import aiohttp
import discord
from bs4 import BeautifulSoup
from utils.tracing import trace_function

# nyaa search function - displays top 5 results from nyaa.si based on user query
@trace_function
async def search(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    
    base_url = "https://nyaa.si"
    search_query = f"{query} 1080p"
    full_query = search_query.replace(' ', '+')
    search_url = f"{base_url}/?f=2&c=1_2&q={full_query}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    await interaction.followup.send(f"❌ Failed to fetch results (HTTP {response.status})")
                    return
                
                html = await response.text()
    except asyncio.TimeoutError:
        await interaction.followup.send("❌ Request timed out")
        return
    except Exception as e:
        await interaction.followup.send(f"❌ Error fetching results: {str(e)}")
        return
            
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.select('table tr')[1:11]  # Skip header row, get next 10
    
    if not rows:
        await interaction.followup.send("❌ No results found")
        return
        
    embed = discord.Embed(title=f"Nyaa Search Results for: {query}", 
                        color=discord.Color.blue(),
                        url=search_url)
    
    embed.set_footer(text=f"Showing up to {len(rows)} results")
    
    result_count = 0
    for row in rows:
        try:
            cols = row.select('td')
            if len(cols) < 5:
                continue
            
            # Extract title and link
            title_link = cols[1].select_one('a:not(.comments)')
            if not title_link:
                continue
            
            title = title_link.text.strip()
            torrent_path = title_link.get('href', '#')
            
            # Extract magnet link
            magnet_element = cols[2].select_one('a[href^="magnet:?"]')
            if not magnet_element:
                continue
            
            size = cols[3].text.strip()
            date = cols[4].text.strip()
            
            # Extract seeders/leechers if available
            seeders = cols[5].text.strip() if len(cols) > 5 else "?"
            leechers = cols[6].text.strip() if len(cols) > 6 else "?"
            
            # Create formatted links
            torrent_url = f"{base_url}{torrent_path}"
            magnet_url = f"{base_url}{torrent_path}/magnet"
            
            # Add field for each result
            embed.add_field(
                name=f"",
                value=f"**#{result_count + 1} • [🧲 Magnet]({magnet_url}) • [🔗 Torrent]({torrent_url}) • {size} • 📅 {date} • 🌱{seeders} 🌿{leechers}**\n```{title}```",
                inline=False
            )
            
            result_count += 1
            if result_count >= 5:  # Limit to 5 results per embed
                break
                
        except (IndexError, AttributeError):
            continue
    
    if result_count == 0:
        await interaction.followup.send("❌ No valid results found")
        return
    
    await interaction.followup.send(embed=embed)