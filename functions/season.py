import asyncio

import discord

from utils import anime_api
from utils.db import (
    rss_add_feed, rss_subscribe, rss_unsubscribe,
    rss_get_series_list, rss_get_subscribed_series,
)
from utils.tracing import trace_function
from utils.utils import make_embed, fetch_rss_feed
from functions.tasks import fuzz_similarity, string_similar

SEASON_VIEW_TIMEOUT = 900  # 15 minutes
SYNOPSIS_MAX = 350


def _quick_match(a: str, b: str) -> bool:
    """Lightweight matcher used for the season -> rss_feeds precompute.
    Drops the TF-IDF fallback in functions.tasks.string_similar because each
    TfidfVectorizer.fit_transform allocates significant numpy work, and for
    MAL-title vs SubsPlease-series matching fuzz.ratio is plenty."""
    return fuzz_similarity(a, b) > 0.85


def _build_match_map(anime_list: list[dict], all_series: list[str]) -> dict[int, str]:
    """For each season anime, find the first existing rss_feeds.series that
    fuzzy-matches its title. Runs once on /season_anime invocation."""
    lowered = [(s, s.strip().lower()) for s in all_series]
    matched: dict[int, str] = {}
    for anime in anime_list:
        mal_id = anime.get("mal_id")
        if mal_id is None:
            continue
        title = (anime.get("title") or "").strip().lower()
        if not title:
            continue
        for series, series_norm in lowered:
            if _quick_match(series_norm, title):
                matched[int(mal_id)] = series
                break
    return matched


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


class SeasonView(discord.ui.View):
    def __init__(
        self,
        anime_list: list[dict],
        owner_id: int,
        matched_by_mal_id: dict[int, str],
        subscribed_set: set[str],
    ):
        super().__init__(timeout=SEASON_VIEW_TIMEOUT)
        self.anime_list = anime_list
        self.owner_id = owner_id
        self.page = 0
        self._matched_by_mal_id = matched_by_mal_id
        self._subscribed_set = subscribed_set
        self._matched_series: str | None = None
        self._user_subscribed: bool = False
        self.refresh_state()

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

    def _current_mal_id(self) -> int | None:
        mal_id = self.anime_list[self.page].get("mal_id")
        return int(mal_id) if mal_id is not None else None

    def refresh_state(self) -> None:
        mal_id = self._current_mal_id()
        self._matched_series = self._matched_by_mal_id.get(mal_id) if mal_id is not None else None
        self._user_subscribed = bool(
            self._matched_series and self._matched_series in self._subscribed_set
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
        self.refresh_state()
        await interaction.response.edit_message(embed=self.render_embed(), view=self)

    async def _on_next(self, interaction: discord.Interaction):
        self.page = (self.page + 1) % len(self.anime_list)
        self.refresh_state()
        await interaction.response.edit_message(embed=self.render_embed(), view=self)

    async def _on_subscribe(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        anime_title = self.anime_list[self.page].get("title") or ""
        mal_id = self._current_mal_id()

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
            if mal_id is not None:
                self._matched_by_mal_id[mal_id] = auto_added
            self._subscribed_set.add(auto_added)
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
        self._subscribed_set.add(self._matched_series)
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
        self._subscribed_set.discard(self._matched_series)
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

    all_series = await rss_get_series_list()
    subscribed_set = set(await rss_get_subscribed_series(interaction.user.id))
    matched_by_mal_id = _build_match_map(season, all_series)

    view = SeasonView(
        season,
        owner_id=interaction.user.id,
        matched_by_mal_id=matched_by_mal_id,
        subscribed_set=subscribed_set,
    )
    await interaction.followup.send(embed=view.render_embed(), view=view)
