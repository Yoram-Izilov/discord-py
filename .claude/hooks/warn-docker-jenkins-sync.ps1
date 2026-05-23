$ErrorActionPreference = 'Stop'
try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $data = $raw | ConvertFrom-Json
    $filePath = $data.tool_input.file_path
    if (-not $filePath) { exit 0 }

    $name = Split-Path -Leaf $filePath
    if ($name -notin @('Dockerfile', 'Jenkinsfile', 'docker-compose.yml')) { exit 0 }

    [Console]::Error.WriteLine("REMINDER: you edited $name.")
    [Console]::Error.WriteLine("Per CLAUDE.md, these values must stay in sync across Dockerfile, Jenkinsfile, and docker-compose.yml:")
    [Console]::Error.WriteLine("  - image / container name (mydiscordbot)")
    [Console]::Error.WriteLine("  - external network (monitoring_monitoring)")
    [Console]::Error.WriteLine("  - OTel endpoint (tempo:4317 -- also referenced in bot.py)")
    [Console]::Error.WriteLine("  - mount paths (/app/data, /app/config/config.json)")
    [Console]::Error.WriteLine("  - restart policy (unless-stopped)")
    [Console]::Error.WriteLine("Run the sync-docker-jenkins skill to audit.")
    exit 0
} catch {
    exit 0
}
