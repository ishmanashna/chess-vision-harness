<#
.SYNOPSIS
  Prep launcher for F/G/H prompt-pack CLI seats (does not auto-score a wave).

.DESCRIPTION
  Starts prompt-test games for packs f,g,h, writes briefs to a run folder, and
  optionally launches Cursor CLI agent seats with isolated worktrees.

  Default: one triad (3 seats). Use -Waves N to stack sequential triads.
  Use -ParallelTriads only when you explicitly want multiple triads at once.

.EXAMPLE
  .\run-fgh-cli-wave.ps1 -Model composer-2.5

.EXAMPLE
  .\run-fgh-cli-wave.ps1 -Model composer-2.5 -Waves 2 -LaunchSeats
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Model,

    [string]$Opponent = "inverse-sf:exclude-top1-d8",

    [int]$Waves = 1,

    [switch]$ParallelTriads,

    [switch]$LaunchSeats,

    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Waves -lt 1) {
    throw "Waves must be >= 1"
}

$pythonDir = Join-Path $RepoRoot "python"
$runsRoot = Join-Path $PSScriptRoot "runs"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $runsRoot "fgh-$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

function Invoke-Harness {
    param([string[]]$HarnessArgs)
    Push-Location $pythonDir
    try {
        & python -m chess_harness @HarnessArgs
        if ($LASTEXITCODE -ne 0) {
            throw "chess_harness failed: $($HarnessArgs -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Start-FghTriad {
    param([int]$WaveNumber)

    $waveDir = Join-Path $runDir ("wave-{0:D2}" -f $WaveNumber)
    New-Item -ItemType Directory -Force -Path $waveDir | Out-Null

    $jsonPath = Join-Path $waveDir "start.json"
    Push-Location $pythonDir
    try {
        python -m chess_harness prompt-test start `
            --model $Model `
            --packs f,g,h `
            --opponent $Opponent | Tee-Object -FilePath $jsonPath
        if ($LASTEXITCODE -ne 0) {
            throw "prompt-test start failed for wave $WaveNumber"
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
        $briefPath = Join-Path $waveDir ("brief-{0}-{1}.txt" -f $pack, $game.game_id)
        $game.brief | Set-Content -Path $briefPath -Encoding utf8
        $manifest += [pscustomobject]@{
            wave = $WaveNumber
            pack = $pack
            game_id = $game.game_id
            brief_path = $briefPath
        }

        if ($LaunchSeats) {
            $outerPrompt = @"
Play this prompt-test overlay seat until the game is over (result is not *).
Use only chess-harness CLI commands from the brief. Do not read state.json or board.png for pack H.
When status says game_over, stop unless told to keep going.

Brief:
$($game.brief)
"@
            $promptPath = Join-Path $waveDir ("seat-{0}-{1}.prompt.txt" -f $pack, $game.game_id)
            $outerPrompt | Set-Content -Path $promptPath -Encoding utf8

            $worktreeName = "fgh-w{0}-{1}-{2}" -f $WaveNumber, $pack, ($game.game_id -replace '[^a-zA-Z0-9_-]', '-')
            Write-Host "Launch seat pack=$pack game=$($game.game_id) worktree=$worktreeName"
            Start-Process -FilePath "agent" -ArgumentList @(
                "-p", "--trust",
                "--worktree", $worktreeName,
                (Get-Content $promptPath -Raw)
            ) -WorkingDirectory $RepoRoot
        }
    }

    $manifest | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $waveDir "manifest.json") -Encoding utf8
    return $manifest
}

Write-Host "Run folder: $runDir"
Write-Host "Model: $Model  Opponent: $Opponent  Waves: $Waves  LaunchSeats: $LaunchSeats"

if ($ParallelTriads -and $Waves -gt 1) {
    1..$Waves | ForEach-Object { Start-FghTriad -WaveNumber $_ }
}
else {
    for ($w = 1; $w -le $Waves; $w++) {
        Start-FghTriad -WaveNumber $w | Out-Null
        if ($w -lt $Waves -and -not $ParallelTriads) {
            Write-Host "Wave $w complete. Start the next triad when seats finish."
        }
    }
}

Write-Host "Done. Briefs and manifests are under $runDir"
Write-Host "This script does not start a scored wave automatically."
