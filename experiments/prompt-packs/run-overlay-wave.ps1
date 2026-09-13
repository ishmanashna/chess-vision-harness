<#
.SYNOPSIS
  Prep launcher for overlay prompt-pack waves (no committee E).

.DESCRIPTION
  Starts prompt-test games, writes briefs under runs/, optionally launches
  Cursor CLI seats. Default packs: a,b,c,d,f,g,h. Opponent default is
  inverse-sf:exclude-top1-d8 (catalog ~500 Elo; same engine as prior waves).

  Does not auto-score. Pack E is rejected.

.EXAMPLE
  .\run-overlay-wave.ps1 -Model composer-2.5

.EXAMPLE
  .\run-overlay-wave.ps1 -Model composer-2.5 -LaunchSeats
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Model,

    [string]$Opponent = "inverse-sf:exclude-top1-d8",

    [string]$Packs = "a,b,c,d,f,g,h",

    [switch]$LaunchSeats,

    [string]$RepoRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $here = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($here)) {
        $here = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $RepoRoot = (Resolve-Path (Join-Path $here "..\..")).Path
}

$packList = @($Packs.Split(",") | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
if ($packList.Count -lt 1) {
    throw "Packs must be a comma list of overlay ids."
}
if ($packList -contains "e") {
    throw "Pack E (committee) is frozen. Use overlay packs only (a,b,c,d,f,g,h)."
}

$pythonDir = Join-Path $RepoRoot "python"
$runsRoot = Join-Path $PSScriptRoot "runs"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$packTag = ($packList -join "")
$runDir = Join-Path $runsRoot ("overlay-{0}-{1}" -f $packTag, $stamp)
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$jsonPath = Join-Path $runDir "start.json"
$packsArg = ($packList -join ",")

Write-Host "Run folder: $runDir"
Write-Host "Model: $Model  Opponent: $Opponent  Packs: $packsArg  LaunchSeats: $LaunchSeats"

Push-Location $pythonDir
try {
    python -m chess_harness prompt-test start `
        --model $Model `
        --packs $packsArg `
        --opponent $Opponent | Tee-Object -FilePath $jsonPath
    if ($LASTEXITCODE -ne 0) {
        throw "prompt-test start failed"
    }
}
finally {
    Pop-Location
}

$start = Get-Content $jsonPath -Raw | ConvertFrom-Json
if (-not $start.ok) {
    throw "prompt-test start returned error: $($start.error)"
}

$manifest = @()
foreach ($game in $start.games) {
    $pack = $game.prompt_pack
    $briefPath = Join-Path $runDir ("brief-{0}.txt" -f $pack)
    $game.brief | Set-Content -Path $briefPath -Encoding utf8
    $row = [pscustomobject]@{
        pack = $pack
        game_id = $game.game_id
        board_path = $game.board_path
        brief_path = $briefPath
        opponent_id = $game.opponent_id
    }
    $manifest += $row

    Write-Host ("Pack {0}: {1}" -f $pack, $game.game_id)

    if ($LaunchSeats) {
        $outerPrompt = @"
Play this prompt-test overlay seat until the game is over (result is not *).
Use only chess-harness CLI or MCP chess_* from the brief. Do not read state.json.
Pack H: observe with board-text only, not board.png.
When status says game_over, stop unless told to keep going.

Brief:
$($game.brief)
"@
        $promptPath = Join-Path $runDir ("seat-{0}.prompt.txt" -f $pack)
        $outerPrompt | Set-Content -Path $promptPath -Encoding utf8
        $worktreeName = "overlay-{0}-{1}" -f $pack, ($game.game_id -replace '[^a-zA-Z0-9_-]', '-')
        Write-Host "Launch seat pack=$pack game=$($game.game_id) worktree=$worktreeName"
        Start-Process -FilePath "agent" -ArgumentList @(
            "-p", "--trust", "--force",
            "--worktree", $worktreeName,
            (Get-Content $promptPath -Raw)
        ) -WorkingDirectory $RepoRoot
    }
}

$manifest | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $runDir "manifest.json") -Encoding utf8
Write-Host "Done. Briefs are under $runDir"
Write-Host "Paste each brief into one Composer overlay seat, or re-run with -LaunchSeats."
