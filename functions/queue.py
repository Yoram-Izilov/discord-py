import asyncio
from dataclasses import dataclass

import discord
import yt_dlp
from discord import FFmpegPCMAudio

from utils.logger import botLogger
from utils.tracing import trace_function
from utils.utils import make_embed

IDLE_DISCONNECT_SECONDS = 300

_queues: dict[int, list["QueueEntry"]] = {}
_now_playing: dict[int, "QueueEntry"] = {}
_player_tasks: dict[int, asyncio.Task] = {}
_queue_events: dict[int, asyncio.Event] = {}


@dataclass
class QueueEntry:
    title: str
    audio_url: str
    webpage_url: str
    requested_by: int
    duration: int | None = None


def _yt_extract(query: str) -> dict | None:
    """Synchronous yt-dlp extraction. Returns the best audio info dict or None.
    Run via asyncio.to_thread to keep the event loop responsive."""
    ydl_opts = {"format": "bestaudio/best", "quiet": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        is_url = "https://" in query or "youtube.com" in query or "youtu.be" in query
        if is_url:
            info = ydl.extract_info(query, download=False)
        else:
            results = ydl.extract_info(f"ytsearch:{query}", download=False)
            if not results or not results.get("entries"):
                return None
            first = results["entries"][0]
            video_id = first.get("id")
            if not video_id:
                return None
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        return info


def _pick_audio_url(info: dict) -> str | None:
    if info.get("url"):
        return info["url"]
    formats = info.get("formats") or []
    best = None
    for fmt in formats:
        if fmt.get("acodec") and fmt["acodec"] != "none" and fmt.get("url"):
            if not best or fmt.get("abr", 0) > best.get("abr", 0):
                best = fmt
    return best["url"] if best else None


@trace_function
async def build_entry(query: str, requested_by: int) -> QueueEntry | None:
    info = await asyncio.to_thread(_yt_extract, query)
    if not info:
        return None
    audio_url = _pick_audio_url(info)
    if not audio_url:
        return None
    return QueueEntry(
        title=info.get("title", "Unknown"),
        audio_url=audio_url,
        webpage_url=info.get("webpage_url", ""),
        requested_by=requested_by,
        duration=info.get("duration"),
    )


@trace_function
async def enqueue(guild: discord.Guild, voice_channel: discord.VoiceChannel, entry: QueueEntry) -> int:
    """Append entry to guild's queue; start player loop if not running.
    Returns the queue position (0 = playing now / next up)."""
    gid = guild.id
    queue = _queues.setdefault(gid, [])
    queue.append(entry)
    position = len(queue) - 1 + (1 if gid in _now_playing else 0)

    event = _queue_events.setdefault(gid, asyncio.Event())
    event.set()

    task = _player_tasks.get(gid)
    if task is None or task.done():
        loop = asyncio.get_running_loop()
        _player_tasks[gid] = loop.create_task(_player_loop(guild, voice_channel))

    return position


async def _wait_next(guild_id: int) -> QueueEntry | None:
    while True:
        queue = _queues.get(guild_id)
        if queue:
            return queue.pop(0)
        event = _queue_events.setdefault(guild_id, asyncio.Event())
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout=IDLE_DISCONNECT_SECONDS)
        except asyncio.TimeoutError:
            return None


async def _player_loop(guild: discord.Guild, voice_channel: discord.VoiceChannel):
    gid = guild.id
    loop = asyncio.get_running_loop()
    voice_client = None
    try:
        voice_client = guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            voice_client = await voice_channel.connect()
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        while True:
            entry = await _wait_next(gid)
            if entry is None:
                botLogger.info("queue idle timeout for guild %s, disconnecting", gid)
                break

            _now_playing[gid] = entry
            done = asyncio.Event()

            def after_playback(error, _done=done, _loop=loop):
                if error:
                    botLogger.error("ffmpeg playback failed in queue: %s", error)
                _loop.call_soon_threadsafe(_done.set)

            source = FFmpegPCMAudio(
                entry.audio_url,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn",
            )

            try:
                voice_client.play(source, after=after_playback)
            except discord.ClientException as e:
                botLogger.warning("voice_client.play raised: %s", e)
                _now_playing.pop(gid, None)
                continue

            await done.wait()
            _now_playing.pop(gid, None)
    except Exception as e:
        botLogger.error("player loop crashed for guild %s: %s", gid, e, exc_info=True)
    finally:
        if voice_client and voice_client.is_connected():
            try:
                await voice_client.disconnect()
            except Exception as e:
                botLogger.warning("voice disconnect on player loop exit failed: %s", e)
        _player_tasks.pop(gid, None)
        _now_playing.pop(gid, None)
        _queues.pop(gid, None)
        _queue_events.pop(gid, None)


@trace_function
def skip(guild: discord.Guild) -> bool:
    vc = guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        return True
    return False


@trace_function
def get_queue(guild: discord.Guild) -> list[QueueEntry]:
    return list(_queues.get(guild.id, []))


@trace_function
def get_now_playing(guild: discord.Guild) -> QueueEntry | None:
    return _now_playing.get(guild.id)


@trace_function
async def stop_and_clear(guild: discord.Guild) -> None:
    """Hard-stop: clear queue, cancel player task, disconnect."""
    gid = guild.id
    _queues.pop(gid, None)
    _now_playing.pop(gid, None)
    event = _queue_events.get(gid)
    if event:
        event.set()
    task = _player_tasks.get(gid)
    if task and not task.done():
        task.cancel()
    vc = guild.voice_client
    if vc and vc.is_connected():
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        try:
            await vc.disconnect()
        except Exception as e:
            botLogger.warning("stop_and_clear disconnect failed: %s", e)


# ---------------------------------------------------------------------------
# Slash command handlers (used by bot.py in Phase 4)
# ---------------------------------------------------------------------------

@trace_function
async def queue_play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    if not query:
        await interaction.followup.send(
            embed=make_embed("❌ Please provide a URL or search query.", kind="error")
        )
        return

    voice_channel = interaction.user.voice.channel if interaction.user.voice else None
    if not voice_channel:
        await interaction.followup.send(
            embed=make_embed("❌ You need to join a voice channel first!", kind="error")
        )
        return

    entry = await build_entry(query, interaction.user.id)
    if entry is None:
        await interaction.followup.send(
            embed=make_embed("❌ Could not find audio for that query.", kind="error")
        )
        return

    position = await enqueue(interaction.guild, voice_channel, entry)
    if position <= 0:
        msg = f"🎵 Now playing: **{entry.title}**"
    else:
        msg = f"➕ Queued **{entry.title}** (position {position})"
    await interaction.followup.send(embed=make_embed(msg, kind="success"))


@trace_function
async def skip_track(interaction: discord.Interaction):
    if skip(interaction.guild):
        await interaction.response.send_message(
            embed=make_embed("⏭️ Skipped.", kind="success")
        )
    else:
        await interaction.response.send_message(
            embed=make_embed("Nothing is playing.", kind="info")
        )


@trace_function
async def queue_show(interaction: discord.Interaction):
    np = get_now_playing(interaction.guild)
    upcoming = get_queue(interaction.guild)
    if not np and not upcoming:
        await interaction.response.send_message(
            embed=make_embed("Queue is empty.", kind="info")
        )
        return
    lines: list[str] = []
    if np:
        lines.append(f"**Now playing:** {np.title}")
    if upcoming:
        lines.append("")
        lines.append("**Up next:**")
        for i, e in enumerate(upcoming[:20], start=1):
            lines.append(f"`{i}.` {e.title}")
        if len(upcoming) > 20:
            lines.append(f"_…and {len(upcoming) - 20} more_")
    await interaction.response.send_message(
        embed=make_embed("\n".join(lines), kind="info", title="🎶 Queue")
    )


@trace_function
async def now_playing(interaction: discord.Interaction):
    np = get_now_playing(interaction.guild)
    if not np:
        await interaction.response.send_message(
            embed=make_embed("Nothing is playing.", kind="info")
        )
        return
    desc = f"**{np.title}**"
    if np.webpage_url:
        desc += f"\n{np.webpage_url}"
    await interaction.response.send_message(
        embed=make_embed(desc, kind="info", title="▶️ Now playing")
    )


@trace_function
async def op_play(interaction: discord.Interaction, anime: str):
    if not anime:
        await interaction.response.send_message(
            embed=make_embed("❌ Please name an anime.", kind="error")
        )
        return
    await queue_play(interaction, f"{anime} opening")
