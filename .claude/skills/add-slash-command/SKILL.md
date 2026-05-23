---
name: add-slash-command
description: Scaffold a new Discord slash command end-to-end -- adds a handler in functions/<module>.py (decorated with @trace_function, using make_embed for responses) and registers it in bot.py with the standard @bot.tree.command wrapper. Use when the user asks to add, create, or scaffold a new /slash command.
---

# Add slash command

Use this skill when the user asks to add a new Discord slash command to the bot.

## What to collect from the user

1. **Command name** -- kebab-case (e.g., `ping`, `weather`). Becomes the `/<name>` users type in Discord.
2. **Description** -- one sentence shown in Discord's command picker.
3. **Parameters** (zero or more) -- for each: name, Python type (`str`, `int`, etc.), short description.
4. **Target module** -- usually a new `functions/<name>.py`. If the command logically extends an existing module (e.g., a new `/rss` subaction in `functions/feed.py`), add it there instead.

Ask via AskUserQuestion if any of these are ambiguous. Don't proceed with placeholders.

## Pattern reference

Three pieces must all be present. See `functions/nyaa.py` and `bot.py` lines 116-120 for the canonical example.

### Handler (in `functions/<module>.py`)

```python
import discord
from utils.tracing import trace_function
from utils.utils import make_embed

@trace_function
async def <name>(interaction: discord.Interaction, <params>):
    # Use interaction.response.defer() for any operation that may take > 3s,
    # then reply via interaction.followup.send(embed=...).
    # For fast replies, use interaction.response.send_message(embed=...).
    # Always build responses with make_embed(text, kind="success"|"error"|"info"|"warning", title=...)
    await interaction.response.send_message(embed=make_embed("...", kind="info"))
```

### Registration (in `bot.py`, inside the relevant `#region` block)

```python
@bot.tree.command(name="<name>", description="<description>")
@trace_function
async def <name>_command(interaction: discord.Interaction, <params>):
    botLogger.info('run <name>_command')
    await <name>(interaction, <params>)
```

For parameters with constrained choices, also add `@app_commands.describe(...)` and `@app_commands.choices(...)` -- see `auto_roulette_command` in `bot.py:123-133`.

### Required decorators

- `@trace_function` on BOTH the wrapper in `bot.py` AND the handler in `functions/`. Forgetting either means missing OpenTelemetry spans in Tempo.
- `@bot.tree.command(...)` must come ABOVE `@trace_function` on the wrapper (decorators are applied bottom-up; Discord.py needs to see the final wrapped callable).

### Import in bot.py

Add to the imports section near the top of `bot.py`:

```python
from functions.<module> import <name>
```

## Steps to execute

1. Confirm the command name doesn't already exist -- grep for `bot.tree.command(name="<name>"` in `bot.py`.
2. Create or edit the handler file in `functions/`.
3. Add the import and the registration block in `bot.py` (place inside the matching `#region` block; create a new region if the command introduces a new domain).
4. Tell the user the verification steps:
   - Set `"debug": true` in `config/config-local.json` (skips OTel + background tasks for quick startup).
   - Run `python bot.py`.
   - In Discord, confirm `/<name>` appears in the command picker and responds correctly.
   - Note: `bot.tree.sync()` runs on startup, but Discord may take up to an hour to propagate new commands globally. For instant testing, sync to a specific guild instead.

## What NOT to do

- Don't use raw `discord.Embed(...)` for simple text responses -- use `make_embed()` from `utils/utils.py` so colors stay consistent.
- Don't put business logic in `bot.py`. The wrapper there should only log and delegate.
- Don't skip `@trace_function`. It fails silently -- no error, just no observability. The `warn-missing-trace` hook will warn but not block.
- Don't add a custom `try/except` that swallows exceptions. The global `on_app_command_error` handler in `bot.py` already converts unhandled exceptions to a user-friendly error embed.
- Don't write the user's commit for them after scaffolding. Let the user review the diff and commit when ready. (If asked, use scope `bot` since the change touches `bot.py` and `functions/`.)
