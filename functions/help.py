import discord

from utils.tracing import trace_function
from utils.utils import make_embed

# Maps command name -> category label. Commands without an entry fall into
# the "Other" group as a soft reminder to register them here.
CATEGORIES: dict[str, str] = {
    "roulette":         "🎲 Roulette",
    "auto_roulette":    "🎲 Roulette",

    "play":             "🎵 Music",
    "queue_play":       "🎵 Music",
    "skip":             "🎵 Music",
    "queue":            "🎵 Music",
    "now_playing":      "🎵 Music",
    "op":               "🎵 Music",
    "leave":            "🎵 Music",

    "mal":              "📺 Anime / MAL",
    "anime_list":       "📺 Anime / MAL",
    "next_anime":       "📺 Anime / MAL",
    "mal_link":         "📺 Anime / MAL",
    "mal_unlink":       "📺 Anime / MAL",
    "next_episode":     "📺 Anime / MAL",
    "mal_compare":      "📺 Anime / MAL",
    "mal_stats":        "📺 Anime / MAL",
    "anime_recommend":  "📺 Anime / MAL",
    "who_is_watching":  "📺 Anime / MAL",

    "rss":              "📡 RSS / torrents",
    "nyaa":             "📡 RSS / torrents",

    "season_anime":     "✨ Discovery",
    "anime_quiz":       "✨ Discovery",

    "help":             "ℹ️ Meta",
}

CATEGORY_ORDER = [
    "📺 Anime / MAL",
    "✨ Discovery",
    "📡 RSS / torrents",
    "🎵 Music",
    "🎲 Roulette",
    "ℹ️ Meta",
    "Other",
]


@trace_function
async def show_help(interaction: discord.Interaction):
    tree = interaction.client.tree
    grouped: dict[str, list[tuple[str, str]]] = {}
    for cmd in tree.get_commands():
        category = CATEGORIES.get(cmd.name, "Other")
        grouped.setdefault(category, []).append((cmd.name, cmd.description or ""))

    lines: list[str] = []
    for category in CATEGORY_ORDER:
        cmds = grouped.get(category)
        if not cmds:
            continue
        lines.append(f"**{category}**")
        for name, desc in sorted(cmds):
            lines.append(f"`/{name}` — {desc}" if desc else f"`/{name}`")
        lines.append("")

    embed = make_embed("\n".join(lines).rstrip(), kind="info", title="🤖 Bot commands")
    embed.set_footer(text="Slash commands work in any channel the bot can see.")
    await interaction.response.send_message(embed=embed, ephemeral=True)
