$ErrorActionPreference = 'Stop'
try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $data = $raw | ConvertFrom-Json
    $filePath = $data.tool_input.file_path
    if (-not $filePath) { exit 0 }

    $norm = $filePath -replace '\\', '/'

    if ($norm -notmatch '/(functions|utils)/[^/]+\.py$') { exit 0 }
    if ($norm -match '__init__\.py$') { exit 0 }
    if (-not (Test-Path -LiteralPath $filePath)) { exit 0 }

    $lines = Get-Content -LiteralPath $filePath
    $missing = @()
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        if ($line -match '^(async\s+)?def\s+(\w+)\s*\(') {
            $funcName = $Matches[2]
            if ($funcName -match '^__.*__$') { continue }

            $hasTrace = $false
            for ($j = $i - 1; $j -ge 0; $j--) {
                $prev = $lines[$j].Trim()
                if ($prev -eq '') { continue }
                if ($prev -match '^@trace_function\b') { $hasTrace = $true; break }
                if ($prev -match '^@') { continue }
                break
            }
            if (-not $hasTrace) {
                $lineNum = $i + 1
                $missing += "  line ${lineNum}: $funcName"
            }
        }
    }

    if ($missing.Count -gt 0) {
        [Console]::Error.WriteLine("WARNING: $filePath has function(s) missing @trace_function:")
        $missing | ForEach-Object { [Console]::Error.WriteLine($_) }
        [Console]::Error.WriteLine("Add 'from utils.tracing import trace_function' if needed, then decorate each function.")
        [Console]::Error.WriteLine("Skipping the decorator fails silently -- no error, just missing spans in Tempo.")
    }
    exit 0
} catch {
    exit 0
}
