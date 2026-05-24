import asyncio
from datetime import datetime, timezone, timedelta
from io import BytesIO

import matplotlib.pyplot as plt

from functions.roulettes import roulette
from utils.utils import *
from utils.tracing import trace_function
from utils.db import (
    mal_get_users, mal_add_user, mal_remove_user, anime_list_get,
    mal_link_discord, mal_get_username_for_discord, mal_get_discord_for_username,
    mal_snapshot_replace, mal_snapshot_get, mal_snapshot_updated_at,
    mal_activity_record, mal_activity_episodes_by_month, mal_score_distribution,
    mal_who_has,
)
from utils import anime_api

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


@trace_function
async def mal_menu(interaction: discord.Interaction, action, user: str = None):
    if action.value == "add_user":
        await add_users_mal(interaction, user)
    elif action.value == "view_users":
        await view_users_mal(interaction)
    elif action.value == "remove_user":
        await remove_users_mal(interaction, user)
    else:
        await interaction.response.send_message(
            embed=make_embed("Invalid option selected.", kind="error"), ephemeral=True
        )

@trace_function
async def anime_list_menu(bot, interaction: discord.Interaction, action, user: str = None):
    if action.value == "update_watching_list":
        await update_anime_list(bot, interaction, Statuses.CURRENTLY_WATCHING.value)
    elif action.value == "update_plantowatch_list":
        await update_anime_list(bot, interaction, Statuses.PLAN_TO_WATCH.value)
    elif action.value == "view_watching_list":
        await view_anime_list(interaction, Statuses.CURRENTLY_WATCHING.value)
    elif action.value == "view_plantowatch_list":
        await view_anime_list(interaction, Statuses.PLAN_TO_WATCH.value)
    else:
        await interaction.response.send_message(
            embed=make_embed("Invalid option selected.", kind="error"), ephemeral=True
        )

@trace_function
async def next_anime(interaction: discord.Interaction):
    anime_list = await anime_list_get(Statuses.PLAN_TO_WATCH.value)
    anime_roulete_string = ",".join(anime_list)
    await roulette(interaction, anime_roulete_string)

@trace_function
async def add_users_mal(interaction, user: str):
    await mal_add_user(user.strip())
    await interaction.response.send_message(
        embed=make_embed(f"Added the new user: {user.strip()}", kind="success")
    )

@trace_function
async def view_users_mal(interaction):
    lines = await mal_get_users()
    await interaction.response.send_message(
        embed=make_embed(f"Users: {', '.join(lines)}", kind="info")
    )

@trace_function
async def remove_users_mal(interaction, user: str):
    await mal_remove_user(user.strip())
    await interaction.response.send_message(
        embed=make_embed(f"Removed the new option set: {user.strip()}", kind="success")
    )

@trace_function
async def update_anime_list(bot, interaction, status):
    await interaction.response.send_message(
        embed=make_embed("Will be updated.", kind="info")
    )

    channel = bot.get_channel(BOT_CHANNEL_ID)
    name    = await update_anime_list_by_status(status)

    await channel.send(
        embed=make_embed(f"Finish to update {name} list.", kind="success")
    )


@trace_function
async def view_anime_list(interaction, status):
    anime_list = await anime_list_get(status)
    if len(anime_list) > 0:
        await interaction.response.send_message(
            embed=make_embed("\n".join(anime_list)[:MAX_LETTERS], kind="info")
        )
    else:
        await interaction.response.send_message(
            embed=make_embed("No anime.", kind="info")
        )


# ---------------------------------------------------------------------------
# Per-user MAL snapshot pipeline (Phase 1)
# ---------------------------------------------------------------------------

SNAPSHOT_STALE_SECONDS = 6 * 60 * 60


@trace_function
async def _refresh_user_snapshot(username: str) -> list[dict]:
    """Pull `username`'s full MAL list, replace their snapshot, and write
    activity rows for the diff — but ONLY when there was a prior snapshot.

    On the first ingest for a user, mal_snapshot_replace produces fake diffs
    (delta_episodes = total episodes ever watched per anime, new_status set
    for everything). Writing those to mal_activity would pollute the weekly
    leaderboard and /mal_stats with a one-time burst that equals the user's
    all-time totals. We populate the snapshot but skip the activity dump.

    Returns the diff rows so callers can still inspect them — milestone
    emitters separately gate on a `is_first_ingest` flag (see
    refresh_all_mal_snapshots) so spurious new_status=COMPLETED rows from
    first ingest don't trigger announcements either."""
    entries = await anime_api.get_user_list(username)
    if not entries:
        return []
    prior_existed = bool(await mal_snapshot_updated_at(username))
    diff = await mal_snapshot_replace(username, entries)
    if diff and prior_existed:
        await mal_activity_record([dict(d, username=username) for d in diff])
    return diff


@trace_function
async def _refresh_if_stale(username: str) -> None:
    from datetime import datetime, timezone, timedelta
    ts = await mal_snapshot_updated_at(username)
    if ts is None or ts < datetime.now(tz=timezone.utc) - timedelta(seconds=SNAPSHOT_STALE_SECONDS):
        await _refresh_user_snapshot(username)


@trace_function
async def mal_link(interaction: discord.Interaction, mal_username: str):
    await interaction.response.defer(ephemeral=True)
    mal_username = (mal_username or "").strip()
    if not mal_username:
        await interaction.followup.send(
            embed=make_embed("❌ Please provide your MAL username.", kind="error"),
            ephemeral=True,
        )
        return

    existing = await mal_get_username_for_discord(interaction.user.id)
    if existing and existing.lower() == mal_username.lower():
        await interaction.followup.send(
            embed=make_embed(f"Already linked to **{existing}**.", kind="info"),
            ephemeral=True,
        )
        return

    # Validate the MAL username exists and has a public list by trying a fetch.
    entries = await anime_api.get_user_list(mal_username)
    if not entries:
        await interaction.followup.send(
            embed=make_embed(
                f"❌ Could not load **{mal_username}**'s list. "
                "Username may be misspelled or the list is set to private.",
                kind="error",
            ),
            ephemeral=True,
        )
        return

    await mal_add_user(mal_username)
    linked = await mal_link_discord(mal_username, interaction.user.id)
    if not linked:
        await interaction.followup.send(
            embed=make_embed(
                "❌ Your Discord account is already linked to a different MAL "
                "user. Have an admin unbind it first.",
                kind="error",
            ),
            ephemeral=True,
        )
        return

    # First ingest by definition — don't write activity rows. The initial
    # diff's delta_episodes equals each anime's total episodes_watched, which
    # would otherwise pollute the weekly leaderboard with a one-off burst
    # equal to the user's all-time totals.
    await mal_snapshot_replace(mal_username, entries)

    await interaction.followup.send(
        embed=make_embed(
            f"✅ Linked to **{mal_username}** — {len(entries)} entries cached.",
            kind="success",
        ),
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Phase 2 helpers — picker + caller-username resolver
# ---------------------------------------------------------------------------

WEEKDAYS = {
    "monday": 0, "mondays": 0,
    "tuesday": 1, "tuesdays": 1,
    "wednesday": 2, "wednesdays": 2,
    "thursday": 3, "thursdays": 3,
    "friday": 4, "fridays": 4,
    "saturday": 5, "saturdays": 5,
    "sunday": 6, "sundays": 6,
}


@trace_function
async def _resolve_caller_mal(interaction: discord.Interaction) -> str | None:
    """Returns the caller's MAL username, or None after sending an error embed."""
    username = await mal_get_username_for_discord(interaction.user.id)
    if username is None:
        await interaction.followup.send(
            embed=make_embed(
                "❌ You haven't linked a MAL account yet. Run `/mal_link <username>` first.",
                kind="error",
            ),
            ephemeral=True,
        )
    return username


@trace_function
async def _pick_anime(interaction: discord.Interaction, query: str) -> dict | None:
    """Search Jikan for `query` and let the user disambiguate. Returns the chosen
    raw Jikan entry, or None on no-match / timeout. Caller must have deferred."""
    results = await anime_api.search_anime(query, limit=10)
    if not results:
        await interaction.followup.send(
            embed=make_embed(f"❌ No anime matched **{query}**.", kind="error")
        )
        return None
    if len(results) == 1:
        return results[0]

    options: list[discord.SelectOption] = []
    by_value: dict[str, dict] = {}
    for r in results[:25]:
        title = (r.get("title") or "Unknown")[:DROPDOWN_TEXT_MAX_LEN]
        year = (r.get("aired") or {}).get("from", "")
        year_suffix = f" ({year[:4]})" if year else ""
        value = str(r.get("mal_id"))
        label = f"{title}{year_suffix}"[:DROPDOWN_TEXT_MAX_LEN]
        options.append(discord.SelectOption(label=label, value=value))
        by_value[value] = r

    future: asyncio.Future = asyncio.Future()
    view = discord.ui.View(timeout=60)
    select = discord.ui.Select(placeholder="Pick the right anime:", options=options)

    async def _cb(i: discord.Interaction):
        if not future.done():
            future.set_result(i.data["values"][0])
        await i.response.defer()

    select.callback = _cb
    view.add_item(select)

    await interaction.followup.send(
        embed=make_embed(f"Multiple matches for **{query}** — pick one:", kind="info"),
        view=view,
    )

    try:
        choice = await asyncio.wait_for(future, timeout=60)
    except asyncio.TimeoutError:
        return None
    return by_value.get(choice)


def _format_next_episode(anime: dict) -> str:
    """Render a one-line description of when the next episode airs."""
    airing = anime.get("airing")
    status = anime.get("status") or ""
    broadcast = anime.get("broadcast") or {}
    day = (broadcast.get("day") or "").lower()
    time_str = broadcast.get("time") or ""
    tz_name = broadcast.get("timezone") or "Asia/Tokyo"

    if not airing:
        return f"📺 **{status or 'Not currently airing'}**"

    if not (day and time_str and day in WEEKDAYS and ZoneInfo):
        broadcast_str = broadcast.get("string") or "Schedule unknown"
        return f"📺 Currently airing — broadcast: {broadcast_str}"

    try:
        hour, minute = (int(x) for x in time_str.split(":"))
        tz = ZoneInfo(tz_name)
        now_tz = datetime.now(tz)
        target_weekday = WEEKDAYS[day]
        days_ahead = (target_weekday - now_tz.weekday()) % 7
        candidate = now_tz.replace(hour=hour, minute=minute, second=0, microsecond=0) \
                          + timedelta(days=days_ahead)
        if candidate <= now_tz:
            candidate += timedelta(days=7)
        unix_ts = int(candidate.astimezone(timezone.utc).timestamp())
        return f"📺 Next episode <t:{unix_ts}:R> (<t:{unix_ts}:F>)"
    except Exception:
        broadcast_str = broadcast.get("string") or "Schedule unknown"
        return f"📺 Currently airing — broadcast: {broadcast_str}"


# ---------------------------------------------------------------------------
# Phase 2 commands
# ---------------------------------------------------------------------------

@trace_function
async def next_episode(interaction: discord.Interaction, anime: str):
    await interaction.response.defer()
    if not anime:
        await interaction.followup.send(
            embed=make_embed("❌ Please name an anime.", kind="error")
        )
        return

    picked = await _pick_anime(interaction, anime)
    if not picked:
        return

    full = await anime_api.get_anime_full(int(picked["mal_id"]))
    if not full:
        await interaction.followup.send(
            embed=make_embed("❌ Could not fetch anime details.", kind="error")
        )
        return

    desc_lines = [
        _format_next_episode(full),
        f"**Status:** {full.get('status') or 'Unknown'}",
    ]
    score = full.get("score")
    if score:
        desc_lines.append(f"**Score:** {score}/10")
    url = full.get("url")
    if url:
        desc_lines.append(f"[MyAnimeList]({url})")

    embed = make_embed("\n".join(desc_lines), kind="info", title=full.get("title"))
    image = ((full.get("images") or {}).get("jpg") or {}).get("image_url")
    if image:
        embed.set_thumbnail(url=image)
    await interaction.followup.send(embed=embed)


@trace_function
async def mal_compare(interaction: discord.Interaction, other: discord.Member):
    await interaction.response.defer()
    if other.id == interaction.user.id:
        await interaction.followup.send(
            embed=make_embed("Compare yourself to yourself? Try someone else.", kind="info")
        )
        return

    me = await _resolve_caller_mal(interaction)
    if not me:
        return

    them = await mal_get_username_for_discord(other.id)
    if not them:
        await interaction.followup.send(
            embed=make_embed(
                f"❌ {other.display_name} hasn't linked a MAL account yet.",
                kind="error",
            )
        )
        return

    await _refresh_if_stale(me)
    await _refresh_if_stale(them)

    my_list = await mal_snapshot_get(me)
    their_list = await mal_snapshot_get(them)

    my_by_id = {e["mal_id"]: e for e in my_list}
    their_by_id = {e["mal_id"]: e for e in their_list}

    completed = Statuses.COMPLETED.value
    watching = Statuses.CURRENTLY_WATCHING.value

    shared_completed = sorted(
        (e["title"] for mid, e in their_by_id.items()
         if e["status"] == completed
         and mid in my_by_id and my_by_id[mid]["status"] == completed),
    )[:10]

    shared_watching = sorted(
        (e["title"] for mid, e in their_by_id.items()
         if e["status"] == watching
         and mid in my_by_id and my_by_id[mid]["status"] == watching),
    )[:10]

    recommendations = sorted(
        (e for mid, e in their_by_id.items()
         if e["status"] == completed and mid not in my_by_id),
        key=lambda e: -(e.get("score") or 0),
    )[:10]

    def fmt(items, getter=lambda x: x):
        if not items:
            return "_none_"
        return "\n".join(f"• {getter(i)}" for i in items)

    embed = make_embed(
        f"You ↔ **{them}**",
        kind="info",
        title=f"MAL comparison",
    )
    embed.add_field(name="🤝 Shared completed", value=fmt(shared_completed), inline=False)
    embed.add_field(name="📺 Shared watching", value=fmt(shared_watching), inline=False)
    embed.add_field(
        name="💡 Their top picks you haven't seen",
        value=fmt(recommendations,
                  getter=lambda e: f"{e['title']} ({e['score']}/10)" if e.get("score") else e["title"]),
        inline=False,
    )
    await interaction.followup.send(embed=embed)


def _render_stats_chart(months: list[tuple[str, int]], dist: dict[int, int]) -> BytesIO | None:
    if not months and not dist:
        return None
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    if months:
        labels = [m for m, _ in months]
        values = [v for _, v in months]
        ax1.bar(labels, values, color="#66b3ff")
        ax1.set_title("Episodes watched per month")
        ax1.tick_params(axis="x", rotation=45)
        for tick in ax1.get_xticklabels():
            tick.set_horizontalalignment("right")
    else:
        ax1.text(0.5, 0.5, "no activity yet", ha="center", va="center")
        ax1.set_axis_off()

    if dist:
        scores = sorted(dist.keys())
        counts = [dist[s] for s in scores]
        ax2.bar([str(s) for s in scores], counts, color="#FFAA1D")
        ax2.set_title("Score distribution")
        ax2.set_xlabel("score")
    else:
        ax2.text(0.5, 0.5, "no scores yet", ha="center", va="center")
        ax2.set_axis_off()

    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", transparent=False)
    plt.close(fig)
    buf.seek(0)
    return buf


@trace_function
async def mal_stats(interaction: discord.Interaction):
    await interaction.response.defer()
    username = await _resolve_caller_mal(interaction)
    if not username:
        return

    await _refresh_if_stale(username)

    months = await mal_activity_episodes_by_month(username, months=12)
    dist = await mal_score_distribution(username)

    if not months and not dist:
        await interaction.followup.send(
            embed=make_embed(
                "No stats yet — try again later once activity has been tracked.",
                kind="info",
            )
        )
        return

    buf = await asyncio.to_thread(_render_stats_chart, months, dist)
    if buf is None:
        await interaction.followup.send(
            embed=make_embed("Could not render stats chart.", kind="error")
        )
        return

    total_eps = sum(v for _, v in months)
    embed = make_embed(
        f"Episodes tracked over the last 12 months: **{total_eps}**",
        kind="info",
        title=f"📊 MAL stats — {username}",
    )
    embed.set_image(url="attachment://mal_stats.png")
    await interaction.followup.send(
        embed=embed,
        file=discord.File(buf, filename="mal_stats.png"),
    )


@trace_function
async def anime_recommend(interaction: discord.Interaction):
    await interaction.response.defer()
    username = await _resolve_caller_mal(interaction)
    if not username:
        return

    await _refresh_if_stale(username)
    plan = await mal_snapshot_get(username, status=Statuses.PLAN_TO_WATCH.value)
    if not plan:
        await interaction.followup.send(
            embed=make_embed(
                "Your plan-to-watch list is empty. Add something on MAL first!",
                kind="info",
            )
        )
        return

    weighted = [(e["title"], (e.get("score") or 1)) for e in plan]
    winner_title, _ = choose_winner(weighted)
    pick = next((e for e in plan if e["title"] == winner_title), plan[0])

    full = await anime_api.get_anime(int(pick["mal_id"]))
    title = (full or {}).get("title") or pick["title"]

    desc_lines = [f"🎯 You should watch **{title}** next!"]
    synopsis = (full or {}).get("synopsis")
    if synopsis:
        desc_lines.append("")
        desc_lines.append(synopsis[:600] + ("…" if len(synopsis) > 600 else ""))
    score = (full or {}).get("score")
    if score:
        desc_lines.append("")
        desc_lines.append(f"**Community score:** {score}/10")
    url = (full or {}).get("url")
    if url:
        desc_lines.append(f"[MyAnimeList]({url})")

    embed = make_embed("\n".join(desc_lines), kind="success", title="Anime recommendation")
    image = (((full or {}).get("images") or {}).get("jpg") or {}).get("image_url")
    if image:
        embed.set_thumbnail(url=image)
    await interaction.followup.send(embed=embed)


@trace_function
async def who_is_watching(interaction: discord.Interaction, anime: str):
    await interaction.response.defer()
    if not anime:
        await interaction.followup.send(
            embed=make_embed("❌ Please name an anime.", kind="error")
        )
        return

    picked = await _pick_anime(interaction, anime)
    if not picked:
        return

    mal_id = int(picked["mal_id"])
    title = picked.get("title") or "Unknown"

    watchers = await mal_who_has(mal_id, [Statuses.CURRENTLY_WATCHING.value])
    if not watchers:
        await interaction.followup.send(
            embed=make_embed(
                f"Nobody on this server is currently watching **{title}**.",
                kind="info",
            )
        )
        return

    rendered: list[str] = []
    for mal_name in watchers:
        discord_id = await mal_get_discord_for_username(mal_name)
        if discord_id:
            rendered.append(f"• <@{discord_id}> ({mal_name})")
        else:
            rendered.append(f"• {mal_name}")

    await interaction.followup.send(
        embed=make_embed(
            "\n".join(rendered),
            kind="info",
            title=f"👀 Watching — {title}",
        )
    )
