# Lane B - sealed one game: create game, write Composer paste brief + manifest.
# From repo root: .\experiments\composer-load-and-burn\lane-b\run-game.ps1

$ErrorActionPreference = 'Stop'

$LaneBDir = $PSScriptRoot
$ExpRoot = (Resolve-Path -LiteralPath (Join-Path $LaneBDir '..')).Path
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $LaneBDir '..\..\..')).Path
$ChPs1 = Join-Path $ExpRoot 'bin\ch.ps1'
$PromptTemplate = Join-Path $ExpRoot 'prompts\lane-b-player.txt'

if (-not (Test-Path -LiteralPath $ChPs1)) {
    Write-Error "Harness wrapper not found: $ChPs1"
}

if (-not (Test-Path -LiteralPath $PromptTemplate)) {
    Write-Error "Prompt template not found: $PromptTemplate"
}

function Get-MadridLocalTime {
    param(
        [datetime]$When = (Get-Date)
    )
    $madridTz = [System.TimeZoneInfo]::FindSystemTimeZoneById('Romance Standard Time')
    $madrid = [System.TimeZoneInfo]::ConvertTime($When, $madridTz)
    return $madrid.ToString('yyyy-MM-dd HH:mm:ss')
}

function Test-HarnessHealth {
    try {
        $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/health' -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -ne 200) {
            return $false
        }
        $body = $resp.Content | ConvertFrom-Json
        return ($body.ok -eq $true)
    }
    catch {
        return $false
    }
}

function Ensure-HarnessUp {
    if (Test-HarnessHealth) {
        Write-Host "Harness health: ok"
        return
    }

    Write-Host "Harness not healthy - starting serve --force..."
    & $ChPs1 serve --force
    if ($LASTEXITCODE -ne 0) {
        Write-Error "ch.ps1 serve --force failed with exit code $LASTEXITCODE"
    }

    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        if (Test-HarnessHealth) {
            Write-Host "Harness health: ok"
            return
        }
        Start-Sleep -Seconds 2
    }

    Write-Error "Harness did not become healthy within 45 seconds."
}

function Invoke-ChNewGame {
    $output = & $ChPs1 new --model composer-2.5 --opponent random --agent-color white 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()
    if ($exitCode -ne 0) {
        throw "ch.ps1 new failed (exit $exitCode): $text"
    }
    try {
        return ($text | ConvertFrom-Json)
    }
    catch {
        throw "ch.ps1 new returned non-JSON: $text"
    }
}

function Substitute-PlayerPrompt {
    param(
        [string]$Template,
        [string]$GameId,
        [string]$BoardPath,
        [string]$AgentColor = 'white'
    )
    $spectatorUrl = "http://127.0.0.1:8765/g/$GameId"
    $boardPngUrl = "http://127.0.0.1:8765/g/$GameId/board.png"
    $result = $Template
    $result = $result.Replace('{{GAME_ID}}', $GameId)
    $result = $result.Replace('{{BOARD_PATH}}', $BoardPath)
    $result = $result.Replace('{{SPECTATOR_URL}}', $spectatorUrl)
    $result = $result.Replace('{{BOARD_PNG_URL}}', $boardPngUrl)
    $result = $result.Replace('{{MODEL_ID}}', 'composer-2.5')
    $result = $result.Replace('{{AGENT_COLOR}}', $AgentColor)
    return $result
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$RunDir = Join-Path $LaneBDir "runs\$stamp"
New-Item -ItemType Directory -Path $RunDir -Force | Out-Null
$startMadrid = Get-MadridLocalTime

Write-Host ""
Write-Host "=== Lane B - sealed Composer game ==="
Write-Host "  stamp:     $stamp"
Write-Host "  run dir:   $RunDir"
Write-Host "  repo root: $RepoRoot"
Write-Host ""

Ensure-HarnessUp

Write-Host ""
Write-Host "Creating game (composer-2.5 vs random, agent white)..."
$newJson = Invoke-ChNewGame
if ($newJson.ok -ne $true) {
    $err = if ($newJson.error) { $newJson.error } else { 'unknown error' }
    Write-Error "ch.ps1 new returned ok=false: $err"
}

$gameId = [string]$newJson.game_id
$boardPath = [string]$newJson.board_path
$agentColor = if ($newJson.agent_color) { [string]$newJson.agent_color } else { 'white' }

if ([string]::IsNullOrWhiteSpace($gameId)) {
    Write-Error "ch.ps1 new missing game_id in JSON."
}

if ([string]::IsNullOrWhiteSpace($boardPath)) {
    Write-Error "ch.ps1 new missing board_path in JSON."
}

if (-not (Test-Path -LiteralPath $boardPath)) {
    Write-Error "board_path does not exist on disk: $boardPath"
}

$spectatorUrl = "http://127.0.0.1:8765/g/$gameId"
$boardPngUrl = "http://127.0.0.1:8765/g/$gameId/board.png"

$template = Get-Content -LiteralPath $PromptTemplate -Raw -Encoding UTF8
$paste = Substitute-PlayerPrompt -Template $template -GameId $gameId -BoardPath $boardPath -AgentColor $agentColor

$pastePath = Join-Path $RunDir 'PASTE.txt'
Set-Content -LiteralPath $pastePath -Value $paste -Encoding UTF8

$manifestLines = @(
    "# Lane B run manifest"
    ""
    "- **stamp:** $stamp"
    "- **arm:** B"
    "- **start (Europe/Madrid):** $startMadrid"
    "- **game_id:** $gameId"
    "- **board_path:** $boardPath"
    ""
    "## Spectator"
    ""
    "- **spectator:** $spectatorUrl"
    "- **board_png:** $boardPngUrl"
    ""
    "## End time"
    ""
    "When the game ends, add a line here:"
    ""
    '- **end (Europe/Madrid):** yyyy-MM-dd HH:mm:ss'
)
$manifestPath = Join-Path $RunDir 'manifest.md'
Set-Content -LiteralPath $manifestPath -Value ($manifestLines -join "`n") -Encoding UTF8

Write-Host ""
Write-Host "Game created:"
Write-Host "  game_id:    $gameId"
Write-Host "  board_path: $boardPath"
Write-Host "  manifest:   $manifestPath"
Write-Host "  paste file: $pastePath"
Write-Host ""
Write-Host "----- PASTE INTO COMPOSER -----"
Write-Host $paste
Write-Host "----- END PASTE -----"
Write-Host ""
Write-Host "Spectator URLs:"
Write-Host "  $spectatorUrl"
Write-Host "  $boardPngUrl"
Write-Host ""
Write-Host "When the game ends, edit manifest.md and add the end time (Europe/Madrid)."
Write-Host "Do not auto-launch Composer from this script - paste the block above manually."
Write-Host ""

if (-not (Test-HarnessHealth)) {
    Write-Error "Health check failed after game creation."
}

Write-Host "Health: ok"
