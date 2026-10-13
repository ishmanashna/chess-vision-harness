<#
.SYNOPSIS
  Poke overlay CLI seats every N minutes (Composer 2.5 non-fast).

.DESCRIPTION
  Reads session-ids.json. Each poke: agent -p --model composer-2.5 --resume.
  Continue the current packed game, or start the next one if it finished.
  Stop: create stop.flag in the run folder.

.EXAMPLE
  .\overlay-keepalive.ps1 -RunDir experiments\prompt-packs\runs\overlay-abcdfgh-20260913-221457

.EXAMPLE
  .\overlay-keepalive.ps1 -RunDir ... -Once
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunDir,

    [int]$IntervalMinutes = 20,

    [string]$Packs = "",

    [string]$SkipPacks = "",

    [switch]$FinishOnly,

    [switch]$Once,

    [string]$RepoRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $here = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($here)) {
        $here = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $RepoRoot = (Resolve-Path (Join-Path $here "..\..")).Path
}

$RunDir = (Resolve-Path -LiteralPath $RunDir).Path
$MapPath = Join-Path $RunDir "session-ids.json"
$LogPath = Join-Path $RunDir "keepalive.log"
$StopFlag = Join-Path $RunDir "stop.flag"
$AgentCmd = Join-Path $env:LOCALAPPDATA "cursor-agent\agent.cmd"
$AgentModel = "composer-2.5"

if (-not (Test-Path -LiteralPath $MapPath)) { throw "missing $MapPath" }
if (-not (Test-Path -LiteralPath $AgentCmd)) { throw "missing $AgentCmd" }

function Write-Log([string]$msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -LiteralPath $LogPath -Value $line -Encoding utf8
    Write-Output $line
}

function Get-PokePrompt([string]$pack, [string]$gameId, [string]$alsoFinish) {
    $alsoLine = ""
    if (-not [string]::IsNullOrWhiteSpace($alsoFinish)) {
        $alsoLine = "After that id is over, finish this already-created game too (do not skip it): $alsoFinish"
    }
    if ($FinishOnly) {
        return @"
FINISH existing games only. Do not acknowledge.

CLI model stays composer-2.5 (Composer 2.5 non-fast). Never composer-2.5-fast. Never auto.

You are overlay pack $pack.
Play this existing game_id until chess-harness status shows game_over: $gameId
$alsoLine

Do NOT run chess-harness new. Do NOT start any other game. Do NOT invent a game_id. Do NOT play game-tmp.
If this game is already over, stop. That is the whole job.

If game_over is false: observe (PNG) and move when it is your turn. Keep going until this game ends.
Do not resign to skip. Do not read state.json.
"@
    }
    return @"
PLAY NOW. Do not acknowledge. Do not invent a game_id. Make chess moves.

CLI model stays composer-2.5 (Composer 2.5 non-fast). Never composer-2.5-fast. Never auto.
You are overlay pack $pack, White vs inverse-sf:exclude-top1-d8.

Known game_id: $gameId
If this chat already has a later live game_id from chess-harness new JSON, keep that one.

1. chess-harness status on the current id.
2. If game_over is false: observe (PNG, or board-text for pack H) and move if it is your turn. Pack H: board-text only, never board.png.
3. If game_over is true - including 1-0, 0-1, 1/2-1/2, AND idle no-result * - that id is dead. Start the NEXT game with:
   chess-harness new --model composer-2.5 --prompt-pack $pack --opponent inverse-sf:exclude-top1-d8 --color white --agent-color white
   Use only the game_id from that JSON. Then play it. Same pack. Do not reuse the finished id.
4. Do not resign to skip. Do not read state.json.

Play at least one ply this poke if it is your turn.
"@
}

function Test-AgentChatLive([string]$chatId) {
    if ([string]::IsNullOrWhiteSpace($chatId)) { return $false }
    $escaped = [regex]::Escape($chatId)
    $hits = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match $escaped -and
        $_.CommandLine -match '--resume' -and
        ($_.Name -eq 'node.exe' -or $_.CommandLine -match 'cursor-agent')
    })
    return $hits.Count -gt 0
}

function Invoke-Poke {
    $raw = Get-Content -LiteralPath $MapPath -Raw -Encoding UTF8
    $map = $raw | ConvertFrom-Json
    $filter = @()
    if (-not [string]::IsNullOrWhiteSpace($Packs)) {
        $filter = @($Packs.Split(",") | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    }
    $skip = @()
    if (-not [string]::IsNullOrWhiteSpace($SkipPacks)) {
        $skip = @($SkipPacks.Split(",") | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    }
    foreach ($prop in $map.PSObject.Properties) {
        $pack = $prop.Name
        if ($filter.Count -gt 0 -and $filter -notcontains $pack) { continue }
        if ($skip -contains $pack) { Write-Log "skip $pack (SkipPacks)"; continue }
        $row = $prop.Value
        $chatId = [string]$row.chat_id
        $worktree = [string]$row.worktree
        $gameId = [string]$row.game_id
        $alsoFinish = ""
        if ($row.PSObject.Properties["also_finish"] -and $row.also_finish) {
            $alsoFinish = [string]$row.also_finish
        }
        $model = [string]$row.model
        if (-not $chatId) { Write-Log "skip $pack (no chat_id)"; continue }
        if ($model -and $model -ne $AgentModel) {
            Write-Log "skip $pack model=$model (want $AgentModel)"
            continue
        }
        if (Test-AgentChatLive $chatId) {
            Write-Log "skip $pack chat=$chatId (agent already live)"
            continue
        }
        $stamp = Get-Date -Format "HHmmss"
        $promptPath = Join-Path $RunDir ("keepalive-$stamp-$pack.prompt.txt")
        Set-Content -LiteralPath $promptPath -Value (Get-PokePrompt -pack $pack -gameId $gameId -alsoFinish $alsoFinish) -Encoding UTF8
        $wrap = Join-Path $RunDir ("keepalive-$stamp-$pack-runner.ps1")
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
        $out = Join-Path $RunDir ("keepalive-$stamp-$pack.out.txt")
        $err = Join-Path $RunDir ("keepalive-$stamp-$pack.err.txt")
        try {
            $argLine = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $wrap
            $p = Start-Process -FilePath "powershell.exe" `
                -ArgumentList $argLine `
                -WorkingDirectory $RepoRoot `
                -PassThru -WindowStyle Hidden `
                -RedirectStandardOutput $out `
                -RedirectStandardError $err
            Write-Log ("poke pack=$pack chat=$chatId model=composer-2.5 pid=$($p.Id)")
        }
        catch {
            Write-Log ("poke FAIL $pack $($_.Exception.Message)")
        }
    }
}

Write-Log ("keepalive start interval={0}m model=composer-2.5 once={1} finishOnly={2} packs={3} skip={4}" -f $IntervalMinutes, [bool]$Once, [bool]$FinishOnly, $Packs, $SkipPacks)
if ($Once) {
    if (-not (Test-Path -LiteralPath $StopFlag)) {
        Invoke-Poke
    }
    Write-Log "keepalive exit"
    return
}
while ($true) {
    if (Test-Path -LiteralPath $StopFlag) {
        Write-Log "stop.flag seen - exiting"
        break
    }
    $left = [int]($IntervalMinutes * 60)
    Write-Log ("sleep {0}s before next poke" -f $left)
    while ($left -gt 0) {
        if (Test-Path -LiteralPath $StopFlag) { break }
        Start-Sleep -Seconds ([Math]::Min(30, $left))
        $left -= 30
    }
    if (Test-Path -LiteralPath $StopFlag) {
        Write-Log "stop.flag seen - exiting"
        break
    }
    Invoke-Poke
}
Write-Log "keepalive exit"
