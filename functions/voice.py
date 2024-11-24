import yt_dlp
import discord
from discord import FFmpegPCMAudio

async def play(interaction: discord.Interaction, url: str, bot):
    # Acknowledge the interaction quickly to prevent timeout
    await interaction.response.defer()  # This acknowledges the interaction, allowing you to do further work

    # Check if the user is in a voice channel
    voice_channel = interaction.user.voice.channel if interaction.user.voice else None
    if not voice_channel:
        await interaction.followup.send("You need to join a voice channel first!")
        return

    # Check if bot is already connected to the voice channel
    if interaction.guild.voice_client:
        voice_client = interaction.guild.voice_client
    else:
        voice_client = await voice_channel.connect()

    # yt-dlp options to ensure the best audio stream is extracted
    ydl_opts = {
        'format': 'bestaudio/best',
        'extractaudio': True, 
        'quiet': True,
        'noplaylist': True,
    }

    try:
        # Extract the video info using yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'formats' in info:
                # We will now grab the URL for the best audio format
                audio_url = None
                for f in info['formats']:
                    if f.get('acodec') == 'mp4a.40.2':  # We want AAC audio codec
                        audio_url = f['url']
                        break

                if not audio_url:
                    # If no valid audio URL found, fallback to the first available
                    audio_url = info['formats'][0]['url']

                # Set FFmpegPCMAudio with more reconnect options for streaming stability
                source = FFmpegPCMAudio(
                    audio_url,
                    before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                    options="-vn"
                )
                def after_playback(error):
                        if error:
                            print(f"Error during playback: {error}")
                        bot.loop.create_task(voice_client.disconnect())

                # Play the audio and set the `after` parameter
                voice_client.play(source, after=after_playback)
            
                # Send a follow-up message indicating the song is now playing
                await interaction.followup.send(f"Now playing: {info['title']}")
            else:
                await interaction.followup.send("Could not extract audio from the given URL.")

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}")

async def leave(interaction: discord.Interaction):
    if interaction.guild.voice_client is not None:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Disconnected from the voice channel.")
    else:
        await interaction.response.send_message("I'm not connected to any voice channel.")
