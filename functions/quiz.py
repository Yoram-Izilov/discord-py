import asyncio
import random
import re

import discord

from utils import anime_api
from utils.db import mal_random_anime_id
from utils.tracing import trace_function
from utils.utils import make_embed
from functions.tasks import string_similar

QUIZ_TIMEOUT_SECONDS = 60
MASK = "█████"
MIN_SYNOPSIS_LEN = 80
MAX_SYNOPSIS_LEN = 1500


def _title_candidates(anime: dict) -> list[str]:
    """All title variations to mask in the synopsis (long form first)."""
    candidates: set[str] = set()
    for key in ("title", "title_english", "title_japanese"):
        v = anime.get(key)
        if v and isinstance(v, str):
            candidates.add(v.strip())
    for syn in (anime.get("title_synonyms") or []):
        if syn and isinstance(syn, str):
            candidates.add(syn.strip())
    for t in (anime.get("titles") or []):
        if isinstance(t, dict):
            title = t.get("title")
            if title and isinstance(title, str):
                candidates.add(title.strip())
    # Sort longest first so compound titles are masked before their substrings.
    return sorted((c for c in candidates if len(c) >= 3), key=len, reverse=True)


def _mask_title_in_text(text: str, anime: dict) -> str:
    result = text
    for cand in _title_candidates(anime):
        result = re.compile(re.escape(cand), re.IGNORECASE).sub(MASK, result)
    return result


async def _pick_random_anime() -> dict | None:
    """Pick a random anime that has a usable synopsis. Tries snapshots first
    (up to 5 attempts), falls back to current season."""
    for _ in range(5):
        sample_id = await mal_random_anime_id()
        if not sample_id:
            break
        full = await anime_api.get_anime_full(sample_id)
        if full and (full.get("synopsis") or "").strip():
            return full
    season = await anime_api.get_current_season()
    candidates = [a for a in season if (a.get("synopsis") or "").strip()]
    return random.choice(candidates) if candidates else None


@trace_function
async def anime_quiz(interaction: discord.Interaction):
    await interaction.response.defer()

    anime = await _pick_random_anime()
    if anime is None:
        await interaction.followup.send(
            embed=make_embed(
                "Couldn't find an anime to quiz on right now. Link a MAL account "
                "with `/mal_link` to grow the pool.",
                kind="error",
            )
        )
        return

    title = (anime.get("title") or "").strip()
    synopsis = anime.get("synopsis") or ""
    if len(synopsis) < MIN_SYNOPSIS_LEN or not title:
        await interaction.followup.send(
            embed=make_embed("Picked anime has no usable synopsis. Try again.", kind="info")
        )
        return

    masked = _mask_title_in_text(synopsis[:MAX_SYNOPSIS_LEN], anime)
    embed = make_embed(
        f"{masked}\n\n_Reply with the anime's title - you have {QUIZ_TIMEOUT_SECONDS} seconds!_",
        kind="info",
        title="🎮 Anime Quiz",
    )
    await interaction.followup.send(embed=embed)

    title_norm = title.lower()

    def check(m: discord.Message) -> bool:
        if m.channel.id != interaction.channel_id or m.author.bot:
            return False
        guess = (m.content or "").strip().lower()
        if not guess:
            return False
        return string_similar(guess, title_norm)

    try:
        winner_msg = await interaction.client.wait_for(
            "message", check=check, timeout=QUIZ_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        reveal = make_embed(
            f"⏰ Time's up! The answer was **{title}**.",
            kind="info",
        )
        image = ((anime.get("images") or {}).get("jpg") or {}).get("image_url")
        if image:
            reveal.set_thumbnail(url=image)
        await interaction.followup.send(embed=reveal)
        return

    win_embed = make_embed(
        f"🎉 {winner_msg.author.mention} got it! It was **{title}**.",
        kind="success",
    )
    image = ((anime.get("images") or {}).get("jpg") or {}).get("image_url")
    if image:
        win_embed.set_thumbnail(url=image)
    score = anime.get("score")
    url = anime.get("url")
    if score or url:
        extras = []
        if score:
            extras.append(f"**Score:** {score}/10")
        if url:
            extras.append(f"[MyAnimeList]({url})")
        win_embed.description += "\n\n" + "\n".join(extras)
    await interaction.followup.send(embed=win_embed)
