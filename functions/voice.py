import yt_dlp
import discord
from discord import FFmpegPCMAudio
from utils.logger import botLogger
from utils.tracing import trace_function
from utils.utils import make_embed


async def _ensure_voice_client(guild, voice_channel):
    """Return a live voice client connected to voice_channel, reconnecting if the prior one died."""
    vc = guild.voice_client
    if vc and vc.is_connected() and vc.channel == voice_channel:
        return vc
    if vc:
        try:
            await vc.disconnect(force=True)
        except Exception as e:
            botLogger.warning("voice disconnect during reconnect failed: %s", e)
    return await voice_channel.connect()


@trace_function
async def play(interaction: discord.Interaction, query: str, bot):
    """Play audio from a URL or search term"""
    await interaction.response.defer()

    # Validate input
    if not query or query is None:
        await interaction.followup.send(
            embed=make_embed("❌ Please provide a valid URL or search query.", kind="error")
        )
        return

    # Check if the user is in a voice channel
    voice_channel = interaction.user.voice.channel if interaction.user.voice else None
    if not voice_channel:
        await interaction.followup.send(
            embed=make_embed("❌ You need to join a voice channel first!", kind="error")
        )
        return

    voice_client = await _ensure_voice_client(interaction.guild, voice_channel)

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
                botLogger.info("playing from URL: %s", query)
                info = ydl.extract_info(query, download=False)
            else:
                # Search for the query on YouTube
                botLogger.info("searching for: %s", query)
                search_results = ydl.extract_info(f"ytsearch:{query}", download=False)
                
                if not search_results or 'entries' not in search_results or len(search_results['entries']) == 0:
                    await interaction.followup.send(
                        embed=make_embed("❌ No results found for that query.", kind="error")
                    )
                    return

                # Get the first video from search results
                video_info = search_results['entries'][0]
                video_id = video_info.get('id')

                if not video_id:
                    await interaction.followup.send(
                        embed=make_embed("❌ Could not extract video ID from search result.", kind="error")
                    )
                    return
                
                # Build YouTube URL from video ID
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                botLogger.info("found video, extracting: %s", video_url)
                
                # Extract full info from the actual video
                info = ydl.extract_info(video_url, download=False)
            
            if not info:
                await interaction.followup.send(
                    embed=make_embed("❌ Could not retrieve video information.", kind="error")
                )
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
            
            botLogger.info("audio URL: %s", audio_url)
            
            if not audio_url:
                await interaction.followup.send(
                    embed=make_embed("❌ Could not extract audio URL.", kind="error")
                )
                return

            source = FFmpegPCMAudio(
                audio_url,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
            )

            # Re-verify voice connection after the slow yt-dlp extraction; the WS may have died.
            voice_client = await _ensure_voice_client(interaction.guild, voice_channel)

            def after_playback(error):
                if error:
                    botLogger.error("ffmpeg playback failed: %s", error)
                # Disconnect after playback finishes
                import asyncio
                asyncio.run_coroutine_threadsafe(
                    voice_client.disconnect(),
                    voice_client.client.loop
                )

            voice_client.play(source, after=after_playback)
            title = info.get('title', 'Unknown')
            await interaction.followup.send(
                embed=make_embed(f"🎵 Now playing: **{title}**", kind="success")
            )

    except Exception as e:
        botLogger.error("yt-dlp extraction failed for query %r: %s", query, e, exc_info=True)
        await interaction.followup.send(
            embed=make_embed(f"❌ An error occurred: {str(e)}", kind="error")
        )

@trace_function
async def leave(interaction: discord.Interaction):
    """Disconnect from the voice channel"""
    await interaction.response.defer()
    
    if interaction.guild.voice_client is not None:
        # Stop playback if anything is playing
        if interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.stop()
        
        await interaction.guild.voice_client.disconnect()
        await interaction.followup.send(
            embed=make_embed("👋 Disconnected from the voice channel.", kind="success")
        )
    else:
        await interaction.followup.send(
            embed=make_embed("❌ I'm not connected to any voice channel.", kind="error")
        )
