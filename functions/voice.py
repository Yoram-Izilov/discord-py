import yt_dlp
import discord
from discord import FFmpegPCMAudio
from utils.tracing import trace_function

@trace_function
async def play(interaction: discord.Interaction, query: str, bot):
    """Play audio from a URL or search term"""
    await interaction.response.defer()

    # Validate input
    if not query or query is None:
        await interaction.followup.send("❌ Please provide a valid URL or search query.")
        return

    # Check if the user is in a voice channel
    voice_channel = interaction.user.voice.channel if interaction.user.voice else None
    if not voice_channel:
        await interaction.followup.send("❌ You need to join a voice channel first!")
        return

    # Check if bot is already connected to the voice channel
    if interaction.guild.voice_client:
        voice_client = interaction.guild.voice_client
    else:
        voice_client = await voice_channel.connect()

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Determine if it's a URL or search query
            is_url = "https://" in query or "youtube.com" in query or "youtu.be" in query
            
            if is_url:
                # Direct URL playback
                print(f"Playing from URL: {query}")
                info = ydl.extract_info(query, download=False)
            else:
                # Search for the query on YouTube
                print(f"Searching for: {query}")
                search_results = ydl.extract_info(f"ytsearch:{query}", download=False)
                
                if not search_results or 'entries' not in search_results or len(search_results['entries']) == 0:
                    await interaction.followup.send("❌ No results found for that query.")
                    return
                
                # Get the first video from search results
                video_info = search_results['entries'][0]
                video_id = video_info.get('id')
                
                if not video_id:
                    await interaction.followup.send("❌ Could not extract video ID from search result.")
                    return
                
                # Build YouTube URL from video ID
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                print(f"Found video, extracting: {video_url}")
                
                # Extract full info from the actual video
                info = ydl.extract_info(video_url, download=False)
            
            if not info:
                await interaction.followup.send("❌ Could not retrieve video information.")
                return
            
            # Try to get URL directly, or construct it from format data
            if info.get('url'):
                audio_url = info['url']
            elif info.get('formats'):
                # Find best audio format
                best_audio = None
                for fmt in info['formats']:
                    if fmt.get('acodec') and fmt['acodec'] != 'none' and fmt.get('url'):
                        if not best_audio or fmt.get('abr', 0) > best_audio.get('abr', 0):
                            best_audio = fmt
                
                if best_audio:
                    audio_url = best_audio['url']
                else:
                    audio_url = None
            else:
                audio_url = None
            
            print(f"Audio URL: {audio_url}")
            
            if not audio_url:
                await interaction.followup.send("❌ Could not extract audio URL.")
                return

            source = FFmpegPCMAudio(
                audio_url,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
            )

            def after_playback(error):
                if error:
                    print(f"Error during playback: {error}")
                # Disconnect after playback finishes
                import asyncio
                asyncio.run_coroutine_threadsafe(
                    voice_client.disconnect(),
                    voice_client.client.loop
                )

            voice_client.play(source, after=after_playback)
            title = info.get('title', 'Unknown')
            await interaction.followup.send(f"🎵 Now playing: **{title}**")

    except Exception as e:
        print(f"Play error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        await interaction.followup.send(f"❌ An error occurred: {str(e)}")

@trace_function
async def leave(interaction: discord.Interaction):
    """Disconnect from the voice channel"""
    await interaction.response.defer()
    
    if interaction.guild.voice_client is not None:
        # Stop playback if anything is playing
        if interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.stop()
        
        await interaction.guild.voice_client.disconnect()
        await interaction.followup.send("👋 Disconnected from the voice channel.")
    else:
        await interaction.followup.send("❌ I'm not connected to any voice channel.")
