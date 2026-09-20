<#
.SYNOPSIS
  Launch Cursor CLI overlay seats as Composer 2.5 (non-fast) with resumable chats.

.DESCRIPTION
  Reads a run folder manifest.json (from run-overlay-wave.ps1). Creates one
  chat per pack, launches agent -p --model composer-2.5 --resume, writes
  session-ids.json for overlay-keepalive.ps1.

  Never uses composer-2.5-fast or auto.

.EXAMPLE
  .\launch-overlay-cli.ps1 -RunDir experiments\prompt-packs\runs\overlay-abcdfgh-20260913-221457
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunDir,

    [string]$AgentModel = "composer-2.5",

    [string]$RepoRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($AgentModel -match 'fast' -or $AgentModel -eq 'auto') {
    throw "Seats must be Composer non-fast. Got '$AgentModel'. Use composer-2.5."
}
if ($AgentModel -ne "composer-2.5") {
    throw "Locked CLI model is composer-2.5 (non-fast). Got '$AgentModel'."
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $here = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($here)) {
        $here = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $RepoRoot = (Resolve-Path (Join-Path $here "..\..")).Path
}

$RunDir = (Resolve-Path -LiteralPath $RunDir).Path
$ManifestPath = Join-Path $RunDir "manifest.json"
if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "manifest.json not found in $RunDir"
}

$AgentCmd = Join-Path $env:LOCALAPPDATA "cursor-agent\agent.cmd"
if (-not (Test-Path -LiteralPath $AgentCmd)) {
    throw "agent.cmd not found: $AgentCmd"
}

# Windows PowerShell 5.1: ConvertFrom-Json emits a JSON array as one pipeline
# object. Do not wrap that pipeline in @() or foreach sees one mega-row.
$parsed = ConvertFrom-Json -InputObject (Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8)
$manifest = @()
if ($parsed -is [System.Array]) {
    $manifest = @($parsed | ForEach-Object { $_ })
} else {
    $manifest = @($parsed)
}

$sessionPath = Join-Path $RunDir "session-ids.json"
$existing = $null
if (Test-Path -LiteralPath $sessionPath) {
    $existing = ConvertFrom-Json -InputObject (Get-Content -LiteralPath $sessionPath -Raw -Encoding UTF8)
}

$sessions = [ordered]@{}

foreach ($row in $manifest) {
    $pack = [string]$row.pack
    $gameId = [string]$row.game_id
    $briefPath = [string]$row.brief_path
    if ([string]::IsNullOrWhiteSpace($pack) -or $pack -match '\s') {
        throw "manifest parse failed: pack='$pack' (expected one letter). Rows=$($manifest.Count)"
    }
    if (-not (Test-Path -LiteralPath $briefPath)) {
        throw "brief missing for pack $pack : $briefPath"
    }
    $brief = Get-Content -LiteralPath $briefPath -Raw -Encoding UTF8
    $worktree = "overlay-cli-$pack"
    $chatId = $null
    if ($existing -and $existing.PSObject.Properties[$pack] -and $existing.$pack.chat_id) {
        $chatId = [string]$existing.$pack.chat_id
        Write-Host ("Reuse pack={0} chat={1}" -f $pack, $chatId)
    }
    if (-not $chatId) {
        $chatId = (& $AgentCmd create-chat).Trim()
    }
    if ($chatId -notmatch '^[0-9a-f-]{36}$') {
        throw "create-chat did not return a UUID for pack $pack : $chatId"
    }

    $boot = @"
PLAY NOW. Do not acknowledge. Do not discuss the model. Make chess moves.

You are overlay pack $pack, White vs inverse-sf:exclude-top1-d8.
Current game: $gameId
CLI model: composer-2.5 (Composer 2.5 non-fast). Never composer-2.5-fast. Never auto.

1. chess-harness status $gameId
2. If in progress and your_turn: observe (PNG, or board-text for pack H) and send a move.
3. Keep going until game_over is true. That includes idle no-result * as well as 1-0 / 0-1 / 1/2-1/2. Then start the NEXT game:
   chess-harness new --model composer-2.5 --prompt-pack $pack --opponent inverse-sf:exclude-top1-d8 --color white --agent-color white
   Use only the game_id from that JSON. Same pack. Do not reuse the finished id. Do not invent a game_id.
4. Pack H: board-text only, never board.png. Do not read state.json. Do not resign to skip.

Brief:
$brief
"@
    $promptPath = Join-Path $RunDir ("seat-$pack.prompt.txt")
    Set-Content -LiteralPath $promptPath -Value $boot -Encoding UTF8

    $wrap = Join-Path $RunDir ("seat-$pack-runner.ps1")
    $wrapLines = @(
        '$ErrorActionPreference = ''Stop'''
        ('$AgentCmd = ''{0}''' -f $AgentCmd.Replace("'", "''"))
        ('$ChatId = ''{0}''' -f $chatId)
        ('$WorktreeName = ''{0}''' -f $worktree)
        ('$PromptPath = ''{0}''' -f $promptPath.Replace("'", "''"))
        '$Prompt = Get-Content -LiteralPath $PromptPath -Raw -Encoding UTF8'
        '& $AgentCmd @(''-p'',''--trust'',''--force'',''--model'',''composer-2.5'',''--resume'',$ChatId,''--worktree'',$WorktreeName,$Prompt)'
        'exit $LASTEXITCODE'
    )
    Set-Content -LiteralPath $wrap -Value ($wrapLines -join "`n") -Encoding UTF8

    $out = Join-Path $RunDir ("seat-$pack.stdout.tmp")
    $err = Join-Path $RunDir ("seat-$pack.stderr.tmp")
    # Path has spaces; ArgumentList array would split -File at "coding stuff".
    $argLine = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $wrap
    $proc = Start-Process -FilePath "powershell.exe" `
        -ArgumentList $argLine `
        -WorkingDirectory $RepoRoot `
        -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $out `
        -RedirectStandardError $err

    Write-Host ("Launch pack={0} game={1} chat={2} model=composer-2.5 pid={3}" -f $pack, $gameId, $chatId, $proc.Id)

    $sessions[$pack] = [ordered]@{
        pack = $pack
        game_id = $gameId
        chat_id = $chatId
        worktree = $worktree
        model = "composer-2.5"
        pid = $proc.Id
        prompt_path = $promptPath
    }
}

$sessionPath = Join-Path $RunDir "session-ids.json"
ConvertTo-Json -InputObject $sessions -Depth 6 | Set-Content -LiteralPath $sessionPath -Encoding UTF8
Write-Host "Wrote $sessionPath"
Write-Host "Start keepalive: .\overlay-keepalive.ps1 -RunDir `"$RunDir`""
