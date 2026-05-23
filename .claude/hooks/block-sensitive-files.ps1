$ErrorActionPreference = 'Stop'
try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $data = $raw | ConvertFrom-Json
    $cmd = $data.tool_input.command
    if (-not $cmd) { exit 0 }

    # Only inspect commands that START with `git add`. This is intentionally
    # narrow: shell-level chaining ("cd foo && git add bar") is not handled,
    # but the alternative -- regex-matching `git add` anywhere -- false-
    # positives on commit message bodies, echo strings, etc. that mention
    # the phrase. `git commit` is not checked here because gitignored files
    # can't enter the index without an earlier `git add -f`, which this
    # blocks. To bypass intentionally, run from a subshell.
    $trimmed = $cmd.Trim()
    if ($trimmed -notmatch '^git\s+add\b') { exit 0 }

    $patterns = @(
        @{ pattern = 'config[/\\]config-local\.json'; label = 'config/config-local.json (Discord token)' },
        @{ pattern = '(^|[\s/\\])config-local\.json(\s|$)'; label = 'config-local.json' },
        @{ pattern = '(^|[\s/\\])\.env(\s|$|[/\\])'; label = '.env' },
        @{ pattern = '(^|[\s/\\])data[/\\]'; label = 'data/ (runtime state)' },
        @{ pattern = '(^|\s)data($|\s)'; label = 'data (directory)' }
    )
    foreach ($p in $patterns) {
        if ($trimmed -match $p.pattern) {
            [Console]::Error.WriteLine("BLOCKED: 'git add' references gitignored / sensitive path: $($p.label)")
            [Console]::Error.WriteLine("These paths hold the Discord token or runtime state and must not be staged.")
            [Console]::Error.WriteLine("Stage specific safe files by name instead (e.g. git add bot.py functions/feed.py).")
            exit 2
        }
    }
    exit 0
} catch {
    exit 0
}
