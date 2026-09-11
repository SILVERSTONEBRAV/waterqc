# ============================================
# PowerShell: Convert .env.production to Docker-safe format (in-place with backup)
# ============================================

$inputFile = ".env.production"
$backupFile = ".env.production.bak"

if (-not (Test-Path $inputFile)) {
    Write-Error "Input file $inputFile not found."
    exit 1
}

# Backup original
Copy-Item $inputFile $backupFile -Force
Write-Host "🔹 Backup of original .env.production created: $backupFile"

$lines = Get-Content $inputFile
$safeLines = @()

foreach ($line in $lines) {
    $trimmed = $line.Trim()

    # Preserve empty lines and comments
    if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
        $safeLines += $line
        continue
    }

    # Skip invalid lines without '='
    if (-not $trimmed.Contains("=")) {
        Write-Warning "Skipping invalid line: $line"
        continue
    }

    # Split key/value on first '='
    $splitIndex = $trimmed.IndexOf("=")
    $key = $trimmed.Substring(0, $splitIndex).Trim()
    $value = $trimmed.Substring($splitIndex + 1).Trim()

    # Remove surrounding quotes if any
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }

    # Escape single quotes and backslashes safely for Bash
    $escaped = $value -replace '\\', '\\\\'   # escape backslashes
    $escaped = $escaped -replace "'", "'\\''" # escape single quotes
    $escaped = $escaped -replace '!', '\\!'   # escape exclamation marks
    $escaped = $escaped -replace '\$', '\\$'  # escape dollar signs
    $escaped = $escaped -replace '&', '\&'    # escape ampersands

    # Wrap in single quotes for safe Bash export
    $safeValue = "'$escaped'"

    $safeLines += "$key=$safeValue"
}

# Overwrite original file in-place
$safeLines | Set-Content $inputFile -Encoding UTF8
Write-Host "✅ Docker-safe .env.production overwritten in-place"
