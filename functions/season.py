import asyncio

import discord

from utils import anime_api
from utils.db import (
    rss_add_feed, rss_subscribe, rss_unsubscribe,
    rss_get_series_list, rss_get_subscribed_series,
)
from utils.tracing import trace_function
from utils.utils import make_embed, fetch_rss_feed
from functions.tasks import string_similar

SEASON_VIEW_TIMEOUT = 900  # 15 minutes
SYNOPSIS_MAX = 350


async def _find_existing_rss_series(anime_title: str) -> str | None:
    """Return the rss_feeds.series that fuzzy-matches `anime_title`, or None."""
    anime_norm = (anime_title or "").strip().lower()
    if not anime_norm:
        return None
    for series in await rss_get_series_list():
        if string_similar(series.strip().lower(), anime_norm):
            return series
    return None


async def _try_auto_add_rss(anime_title: str, user_id: int) -> str | None:
    """Pull the live SubsPlease RSS, find an entry fuzzy-matching `anime_title`,
    add the feed and subscribe `user_id` in one shot. Returns the matched series
    name or None if the live feed also doesn't have it."""
    anime_norm = (anime_title or "").strip().lower()
    if not anime_norm:
        return None
    feed_entries = await asyncio.to_thread(fetch_rss_feed)
    for entry in feed_entries:
        series = (entry.get("series") or "").strip()
        if not series:
            continue
        if string_similar(series.lower(), anime_norm):
            await rss_add_feed(entry, user_id=user_id)
            return series
    return None


async def _is_subscribed(user_id: int, series: str) -> bool:
    subs = await rss_get_subscribed_series(user_id)
    return series in subs


class SeasonView(discord.ui.View):
    def __init__(self, anime_list: list[dict], owner_id: int):
        super().__init__(timeout=SEASON_VIEW_TIMEOUT)
        self.anime_list = anime_list
        self.owner_id = owner_id
        self.page = 0
        self._matched_series: str | None = None
        self._user_subscribed: bool = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=make_embed(
                    "Only the user who ran `/season_anime` can use these buttons. "
                    "Run your own to interact.",
                    kind="info",
                ),
                ephemeral=True,
            )
            return False
        return True

    async def refresh_state(self) -> None:
        title = (self.anime_list[self.page].get("title") or "")
        self._matched_series = await _find_existing_rss_series(title)
        self._user_subscribed = (
            await _is_subscribed(self.owner_id, self._matched_series)
            if self._matched_series else False
        )
        self._rebuild_buttons()

    def _rebuild_buttons(self) -> None:
        self.clear_items()

        prev_btn = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary)
        prev_btn.callback = self._on_prev
        self.add_item(prev_btn)

        if self._user_subscribed:
            toggle = discord.ui.Button(label="🔕 Unsubscribe", style=discord.ButtonStyle.danger)
            toggle.callback = self._on_unsubscribe
        else:
            toggle = discord.ui.Button(label="🔔 Subscribe", style=discord.ButtonStyle.success)
            toggle.callback = self._on_subscribe
        self.add_item(toggle)

        next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary)
        next_btn.callback = self._on_next
        self.add_item(next_btn)

    def render_embed(self) -> discord.Embed:
        anime = self.anime_list[self.page]
        title = anime.get("title") or "Unknown"
        broadcast = ((anime.get("broadcast") or {}).get("string")) or "—"
        score = anime.get("score")
        score_str = f"{score}/10" if score else "—"
        genres_list = [g["name"] for g in (anime.get("genres") or [])[:4]]
        genres_str = ", ".join(genres_list) if genres_list else "—"
        url = anime.get("url")
        mal_link = f"[MyAnimeList]({url})" if url else "—"

        synopsis_full = anime.get("synopsis") or ""
        if synopsis_full:
            synopsis = synopsis_full[:SYNOPSIS_MAX]
            if len(synopsis_full) > SYNOPSIS_MAX:
                synopsis += "…"
        else:
            synopsis = "_No synopsis available._"

        body = (
            f"**Broadcast:** {broadcast}\n"
            f"**Score:** {score_str}\n"
            f"**Genres:** {genres_str}\n"
            f"{mal_link}\n"
            f"\n"
            f"{synopsis}"
        )

        embed = make_embed(body, kind="info", title=title)
        image = (((anime.get("images") or {}).get("jpg") or {}).get("large_image_url")
                 or ((anime.get("images") or {}).get("jpg") or {}).get("image_url"))
        if image:
            embed.set_thumbnail(url=image)
        embed.set_footer(
            text=f"Page {self.page + 1}/{len(self.anime_list)} • Only the invoker can use these buttons • 15 min"
        )
        return embed

    async def _on_prev(self, interaction: discord.Interaction):
        self.page = (self.page - 1) % len(self.anime_list)
        await self.refresh_state()
        await interaction.response.edit_message(embed=self.render_embed(), view=self)

    async def _on_next(self, interaction: discord.Interaction):
        self.page = (self.page + 1) % len(self.anime_list)
        await self.refresh_state()
        await interaction.response.edit_message(embed=self.render_embed(), view=self)

    async def _on_subscribe(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        anime_title = self.anime_list[self.page].get("title") or ""

        if not self._matched_series:
            auto_added = await _try_auto_add_rss(anime_title, interaction.user.id)
            if not auto_added:
                await interaction.followup.send(
                    embed=make_embed(
                        "📡 No matching SubsPlease entry yet — the show hasn't started releasing. "
                        "Try again once episode 1 is out.",
                        kind="info",
                    ),
                    ephemeral=True,
                )
                return
            self._matched_series = auto_added
            self._user_subscribed = True
            self._rebuild_buttons()
            await interaction.message.edit(view=self)
            await interaction.followup.send(
                embed=make_embed(
                    f"✅ Added the SubsPlease feed for **{auto_added}** and subscribed you.",
                    kind="success",
                ),
                ephemeral=True,
            )
            return

        ok = await rss_subscribe(self._matched_series, interaction.user.id)
        self._user_subscribed = True
        self._rebuild_buttons()
        await interaction.message.edit(view=self)
        msg = (f"✅ Subscribed to **{self._matched_series}**."
               if ok else f"You're already subscribed to **{self._matched_series}**.")
        await interaction.followup.send(
            embed=make_embed(msg, kind="success" if ok else "info"),
            ephemeral=True,
        )

    async def _on_unsubscribe(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not self._matched_series:
            await interaction.followup.send(
                embed=make_embed("Nothing to unsubscribe from.", kind="info"),
                ephemeral=True,
            )
            return
        ok = await rss_unsubscribe(self._matched_series, interaction.user.id)
        self._user_subscribed = False
        self._rebuild_buttons()
        await interaction.message.edit(view=self)
        msg = (f"🔕 Unsubscribed from **{self._matched_series}**."
               if ok else f"You weren't subscribed to **{self._matched_series}**.")
        await interaction.followup.send(
            embed=make_embed(msg, kind="success" if ok else "info"),
            ephemeral=True,
        )


@trace_function
async def season_anime(interaction: discord.Interaction):
    await interaction.response.defer()
    season = await anime_api.get_current_season()
    if not season:
        await interaction.followup.send(
            embed=make_embed("Could not fetch the current season from Jikan.", kind="error")
        )
        return
    view = SeasonView(season, owner_id=interaction.user.id)
    await view.refresh_state()
    await interaction.followup.send(embed=view.render_embed(), view=view)
