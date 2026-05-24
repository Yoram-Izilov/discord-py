import discord

from utils import anime_api
from utils.db import rss_get_series_list, rss_subscribe
from utils.tracing import trace_function
from utils.utils import make_embed
from functions.tasks import string_similar

SEASON_VIEW_TIMEOUT = 900  # 15 minutes


async def _try_subscribe(user_id: int, anime_title: str) -> str:
    """Subscribe `user_id` to whichever rss_feeds series fuzzy-matches
    `anime_title`. Returns a user-facing message."""
    all_series = await rss_get_series_list()
    anime_norm = (anime_title or "").strip().lower()
    if not anime_norm:
        return "❌ Anime title is empty."

    for series in all_series:
        if string_similar(series.strip().lower(), anime_norm):
            ok = await rss_subscribe(series, user_id)
            if ok:
                return f"✅ Subscribed to **{series}** — you'll be pinged on new episodes."
            return f"You're already subscribed to **{series}**."

    return (
        "📡 No RSS feed exists for this series yet. The bot auto-detects feeds "
        "once SubsPlease starts releasing episodes — come back and run "
        "`/rss sub_to_rss` then."
    )


class SeasonView(discord.ui.View):
    def __init__(self, anime_list: list[dict]):
        super().__init__(timeout=SEASON_VIEW_TIMEOUT)
        self.anime_list = anime_list
        self.page = 0

    def render_embed(self) -> discord.Embed:
        anime = self.anime_list[self.page]
        title = anime.get("title") or "Unknown"
        score = anime.get("score")
        broadcast = ((anime.get("broadcast") or {}).get("string")) or "Schedule unknown"
        synopsis_full = anime.get("synopsis") or ""
        synopsis = synopsis_full[:400] + ("…" if len(synopsis_full) > 400 else "")
        genres = ", ".join(g["name"] for g in (anime.get("genres") or [])[:4]) or None
        url = anime.get("url")

        lines = [f"**Broadcast:** {broadcast}"]
        if score:
            lines.append(f"**Score:** {score}/10")
        if genres:
            lines.append(f"**Genres:** {genres}")
        if url:
            lines.append(f"[MyAnimeList]({url})")
        lines.append("")
        lines.append(synopsis or "_No synopsis available._")

        embed = make_embed("\n".join(lines), kind="info", title=title)
        image = (((anime.get("images") or {}).get("jpg") or {}).get("large_image_url")
                 or ((anime.get("images") or {}).get("jpg") or {}).get("image_url"))
        if image:
            embed.set_thumbnail(url=image)
        embed.set_footer(
            text=f"Page {self.page + 1}/{len(self.anime_list)} • Buttons expire after 15 min"
        )
        return embed

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = (self.page - 1) % len(self.anime_list)
        await interaction.response.edit_message(embed=self.render_embed(), view=self)

    @discord.ui.button(label="🔔 Subscribe", style=discord.ButtonStyle.success)
    async def subscribe(self, interaction: discord.Interaction, button: discord.ui.Button):
        anime = self.anime_list[self.page]
        msg = await _try_subscribe(interaction.user.id, anime.get("title") or "")
        kind = "success" if msg.startswith("✅") else "info"
        await interaction.response.send_message(
            embed=make_embed(msg, kind=kind), ephemeral=True
        )

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = (self.page + 1) % len(self.anime_list)
        await interaction.response.edit_message(embed=self.render_embed(), view=self)


@trace_function
async def season_anime(interaction: discord.Interaction):
    await interaction.response.defer()
    season = await anime_api.get_current_season()
    if not season:
        await interaction.followup.send(
            embed=make_embed("Could not fetch the current season from Jikan.", kind="error")
        )
        return
    view = SeasonView(season)
    await interaction.followup.send(embed=view.render_embed(), view=view)
