# Lane A CLI - baseline sampler, then N parallel agent seats with hot sampler.
# From repo root: .\experiments\composer-load-and-burn\lane-a\run-cli-6.ps1 [-Seats 6]
# Games run to completion (agent exits). No default kill timeout - use -TimeoutSec only for wedged debugging.

param(
    [int]$Seats = 6,
    # 0 = wait until all seats exit (games over). Set >0 only to force-kill wedged agents.
    [int]$TimeoutSec = 0,
    [int]$BaselineSec = 90
)

$ErrorActionPreference = 'Stop'

$LaneADir = $PSScriptRoot
$ExpRoot = (Resolve-Path -LiteralPath (Join-Path $LaneADir '..')).Path
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $LaneADir '..\..\..')).Path
$SamplerPs1 = Join-Path $LaneADir 'sample-os.ps1'
$ChPs1 = Join-Path $ExpRoot 'bin\ch.ps1'
$PromptTemplate = Join-Path $ExpRoot 'prompts\lane-a-player.txt'
$AgentCmd = Join-Path $env:LOCALAPPDATA 'cursor-agent\agent.cmd'

if (-not (Test-Path -LiteralPath $AgentCmd)) {
    Write-Error "agent.cmd not found: $AgentCmd"
}

if (-not (Test-Path -LiteralPath $SamplerPs1)) {
    Write-Error "Sampler not found: $SamplerPs1"
}

if (-not (Test-Path -LiteralPath $PromptTemplate)) {
    Write-Error "Prompt template not found: $PromptTemplate"
}

if (-not (Test-Path -LiteralPath $ChPs1)) {
    Write-Error "Harness wrapper not found: $ChPs1"
}

if ($Seats -lt 1 -or $Seats -gt 6) {
    Write-Error "Seats must be between 1 and 6 (got $Seats)."
}

function Get-MadridLocalTime {
    param(
        [datetime]$When = (Get-Date)
    )
    $madridTz = [System.TimeZoneInfo]::FindSystemTimeZoneById('Romance Standard Time')
    $madrid = [System.TimeZoneInfo]::ConvertTime($When, $madridTz)
    return $madrid.ToString('yyyy-MM-dd HH:mm:ss')
}

function Get-CursorProcessCount {
    return @(Get-Process -Name 'Cursor' -ErrorAction SilentlyContinue).Count
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
        [string]$BoardPath
    )
    $spectatorUrl = "http://127.0.0.1:8765/g/$GameId"
    $boardPngUrl = "http://127.0.0.1:8765/g/$GameId/board.png"
    $result = $Template
    $result = $result.Replace('{{GAME_ID}}', $GameId)
    $result = $result.Replace('{{BOARD_PATH}}', $BoardPath)
    $result = $result.Replace('{{SPECTATOR_URL}}', $spectatorUrl)
    $result = $result.Replace('{{BOARD_PNG_URL}}', $boardPngUrl)
    $result = $result.Replace('{{MODEL_ID}}', 'composer-2.5')
    $result = $result.Replace('{{AGENT_COLOR}}', 'white')
    return $result
}

function Get-TailText {
    param(
        [string]$Path,
        [int]$MaxLines = 80
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return '(no output captured)'
    }
    $lines = @(Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue)
    if ($lines.Count -eq 0) {
        return '(empty)'
    }
    if ($lines.Count -le $MaxLines) {
        return ($lines -join "`n")
    }
    return ('...(truncated)...' + "`n" + ($lines | Select-Object -Last $MaxLines | ForEach-Object { $_ } | Out-String))
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$RunDir = Join-Path $LaneADir "runs\$stamp"
New-Item -ItemType Directory -Path $RunDir -Force | Out-Null

$cursorCountAtLaunch = Get-CursorProcessCount
$startMadrid = Get-MadridLocalTime

Write-Host ""
Write-Host "=== Lane A CLI load run ==="
Write-Host "  stamp:          $stamp"
Write-Host "  seats:          $Seats"
Write-Host ("  timeout:        " + $(if ($TimeoutSec -gt 0) { ("{0} s (kill armed)" -f $TimeoutSec) } else { "none (run to completion)" }))
Write-Host "  baseline:       $BaselineSec s"
Write-Host "  run dir:        $RunDir"
Write-Host "  repo root:      $RepoRoot"
Write-Host "  Cursor procs:   $cursorCountAtLaunch"
Write-Host ""
Write-Host "WARNING: Close Cursor IDE for this arm if possible."
Write-Host "         Scripts will NOT kill Cursor processes."
Write-Host ""

Write-Host "Baseline sampler ($BaselineSec s)..."
$baselineArgLine = "-NoProfile -ExecutionPolicy Bypass -File `"$SamplerPs1`" -OutDir `"$RunDir`" -IntervalSec 5 -Phase baseline -DurationSec $BaselineSec"
$baselineProc = Start-Process -FilePath 'powershell.exe' `
    -ArgumentList $baselineArgLine `
    -WorkingDirectory $RepoRoot `
    -PassThru `
    -Wait `
    -WindowStyle Hidden
if ($baselineProc.ExitCode -ne 0) {
    Write-Error "Baseline sampler exited with code $($baselineProc.ExitCode)"
}
Write-Host "Baseline sampler finished."

Ensure-HarnessUp

$template = Get-Content -LiteralPath $PromptTemplate -Raw -Encoding UTF8
$gameRecords = @()

for ($seat = 1; $seat -le $Seats; $seat++) {
    Write-Host "Creating game for seat $seat..."
    $newJson = Invoke-ChNewGame
    if ($newJson.ok -ne $true) {
        $err = if ($newJson.error) { $newJson.error } else { 'unknown error' }
        Write-Error "Seat ${seat}: ch.ps1 new returned ok=false: $err"
    }
    if (-not $newJson.game_id) {
        Write-Error "Seat ${seat}: ch.ps1 new missing game_id in JSON."
    }
    if (-not $newJson.board_path) {
        Write-Error "Seat ${seat}: ch.ps1 new missing board_path in JSON."
    }

    $gameRecords += [PSCustomObject]@{
        Seat      = $seat
        GameId    = [string]$newJson.game_id
        BoardPath = [string]$newJson.board_path
    }
    Write-Host "  seat $seat game_id: $($newJson.game_id)"
}

$manifestLines = @(
    "# Lane A CLI run manifest"
    ""
    "- **stamp:** $stamp"
    "- **arm:** CLI"
    "- **start (Europe/Madrid):** $startMadrid"
    "- **seats:** $Seats"
    "- **cursor_process_count_at_launch:** $cursorCountAtLaunch"
    ""
    "## Games"
    ""
    "| seat | game_id | board_path |"
    "| --- | --- | --- |"
)
foreach ($rec in $gameRecords) {
    $manifestLines += "| $($rec.Seat) | $($rec.GameId) | $($rec.BoardPath) |"
}
$manifestPath = Join-Path $RunDir 'manifest.md'
Set-Content -LiteralPath $manifestPath -Value ($manifestLines -join "`n") -Encoding UTF8

Write-Host ""
Write-Host "Hot sampler starting..."
$hotArgLine = "-NoProfile -ExecutionPolicy Bypass -File `"$SamplerPs1`" -OutDir `"$RunDir`" -IntervalSec 5 -Phase hot"
$samplerProc = Start-Process -FilePath 'powershell.exe' `
    -ArgumentList $hotArgLine `
    -WorkingDirectory $RepoRoot `
    -PassThru `
    -WindowStyle Hidden
$samplerPid = $samplerProc.Id
Write-Host "Hot sampler started (PID $samplerPid)"
Start-Sleep -Seconds 2

$seatRecords = @()

foreach ($rec in $gameRecords) {
    $seat = $rec.Seat
    $prompt = Substitute-PlayerPrompt -Template $template -GameId $rec.GameId -BoardPath $rec.BoardPath
    $worktreeName = "lane-a-seat-$seat"

    $stdoutPath = Join-Path $RunDir "seat-$seat.stdout.tmp"
    $stderrPath = Join-Path $RunDir "seat-$seat.stderr.tmp"
    $promptPath = Join-Path $RunDir "seat-$seat-prompt.txt"
    $wrapperPath = Join-Path $RunDir "seat-$seat-runner.ps1"

    Set-Content -LiteralPath $promptPath -Value $prompt -Encoding UTF8

    $wrapperLines = @(
        '$ErrorActionPreference = ''Stop'''
        ('$AgentCmd = ''{0}''' -f ($AgentCmd.Replace("'", "''")))
        ('$WorktreeName = ''{0}''' -f $worktreeName)
        ('$PromptPath = ''{0}''' -f ($promptPath.Replace("'", "''")))
        '$Prompt = Get-Content -LiteralPath $PromptPath -Raw'
        '& $AgentCmd -p --trust --force --worktree $WorktreeName $Prompt'
        'exit $LASTEXITCODE'
    )
    Set-Content -LiteralPath $wrapperPath -Value ($wrapperLines -join "`n") -Encoding UTF8

    Write-Host "Starting seat $seat (worktree $worktreeName)..."

    $wrapperArgLine = "-NoProfile -ExecutionPolicy Bypass -File `"$wrapperPath`""
    $proc = Start-Process -FilePath 'powershell.exe' `
        -ArgumentList $wrapperArgLine `
        -WorkingDirectory $RepoRoot `
        -PassThru `
        -NoNewWindow `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath

    $seatRecords += [PSCustomObject]@{
        Seat       = $seat
        GameId     = $rec.GameId
        Process    = $proc
        StdOutPath = $stdoutPath
        StdErrPath = $stderrPath
        StartTime  = Get-Date
    }
}

$timedOut = $false
if ($TimeoutSec -gt 0) {
    Write-Host ("Optional kill timeout armed: {0} s (debug only)." -f $TimeoutSec)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
} else {
    Write-Host "No kill timeout - waiting until all seats exit (games to completion)."
    $deadline = [datetime]::MaxValue
}

while ($true) {
    $running = @($seatRecords | Where-Object { -not $_.Process.HasExited })
    if ($running.Count -eq 0) {
        break
    }
    if (($TimeoutSec -gt 0) -and ((Get-Date) -ge $deadline)) {
        $timedOut = $true
        Write-Host ("Timeout reached ({0} s) - stopping remaining seats..." -f $TimeoutSec)
        foreach ($rec in $running) {
            try {
                Stop-Process -Id $rec.Process.Id -Force -ErrorAction SilentlyContinue
            }
            catch {
                # already exited
            }
        }
        Start-Sleep -Seconds 2
        break
    }
    Start-Sleep -Seconds 2
}

$exitSummary = @()

foreach ($rec in $seatRecords) {
    $seat = $rec.Seat
    if (-not $rec.Process.HasExited) {
        try {
            $rec.Process.WaitForExit(5000)
        }
        catch {
            # force-stopped
        }
    }

    $exitCode = -1
    if ($rec.Process.HasExited) {
        $rec.Process.Refresh()
        $exitCode = $rec.Process.ExitCode
        if ($null -eq $exitCode) { $exitCode = -1 }
    }
    $logPath = Join-Path $RunDir "seat-$seat.log"

    $logBody = @(
        "seat: $seat"
        "game_id: $($rec.GameId)"
        "pid: $($rec.Process.Id)"
        "exit_code: $exitCode"
        "started: $($rec.StartTime.ToString('yyyy-MM-ddTHH:mm:ss'))"
        "ended: $((Get-Date).ToString('yyyy-MM-ddTHH:mm:ss'))"
        ""
        "----- stdout (tail) -----"
        (Get-TailText -Path $rec.StdOutPath)
        ""
        "----- stderr (tail) -----"
        (Get-TailText -Path $rec.StdErrPath)
    )
    Set-Content -LiteralPath $logPath -Value ($logBody -join "`n") -Encoding UTF8

    Remove-Item -LiteralPath $rec.StdOutPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $rec.StdErrPath -Force -ErrorAction SilentlyContinue

    $exitSummary += [PSCustomObject]@{
        Seat     = $seat
        GameId   = $rec.GameId
        ExitCode = $exitCode
        Log      = $logPath
    }

    Write-Host "Seat $seat finished with exit code $exitCode"
}

Start-Sleep -Seconds 2
try {
    if (-not $samplerProc.HasExited) {
        Stop-Process -Id $samplerPid -Force -ErrorAction Stop
    }
}
catch {
    Write-Host "Warning: could not stop hot sampler PID $samplerPid - $_"
}

$endMadrid = Get-MadridLocalTime
Add-Content -LiteralPath $manifestPath -Value "" -Encoding UTF8
Add-Content -LiteralPath $manifestPath -Value "- **end (Europe/Madrid):** $endMadrid" -Encoding UTF8

$csvPath = Join-Path $RunDir 'os.csv'
$csvRows = 0
$baselineRows = 0
$hotRows = 0
if (Test-Path -LiteralPath $csvPath) {
    $dataLines = @(Get-Content -LiteralPath $csvPath | Select-Object -Skip 1)
    $csvRows = $dataLines.Count
    foreach ($line in $dataLines) {
        if ($line -match ',baseline,') { $baselineRows++ }
        if ($line -match ',hot,') { $hotRows++ }
    }
}

$summaryLines = @(
    "# Lane A CLI run summary"
    ""
    "- **stamp:** $stamp"
    "- **arm:** CLI"
    "- **seats:** $Seats"
    "- **timeout_sec:** $(if ($TimeoutSec -gt 0) { $TimeoutSec } else { '0 (disabled - run to completion)' })"
    "- **baseline_sec:** $BaselineSec"
    "- **timed_out:** $timedOut"
    "- **start (Europe/Madrid):** $startMadrid"
    "- **end (Europe/Madrid):** $endMadrid"
    "- **cursor_process_count_at_launch:** $cursorCountAtLaunch"
    "- **baseline_sampler_exit:** $($baselineProc.ExitCode)"
    "- **hot_sampler_pid:** $samplerPid"
    "- **run_dir:** $RunDir"
    "- **repo_root:** $RepoRoot"
    "- **agent:** $AgentCmd"
    '- **model flag:** omitted (agent default; run `agent --list-models` to confirm Composer id)'
    '- **mode:** agent (no `--mode ask`; no `--workspace`; `--worktree` only)'
    "- **os.csv data rows:** $csvRows (baseline: $baselineRows, hot: $hotRows)"
    ""
    "## Seat exit codes"
    ""
    "| seat | game_id | exit_code | log |"
    "| --- | --- | --- | --- |"
)

foreach ($item in $exitSummary) {
    $relLog = "seat-$($item.Seat).log"
    $summaryLines += "| $($item.Seat) | $($item.GameId) | $($item.ExitCode) | $relLog |"
}

$summaryLines += ""
$summaryLines += "## Operator"
$summaryLines += ""
$summaryLines += "Note any agent crashes, auth blocks, or machine instability. Compare os.csv peaks across IDE vs CLI arms."
$summaryLines += ""
$summaryLines += "Sampler CSV: ``os.csv`` in this directory."

$summaryPath = Join-Path $RunDir 'summary.md'
Set-Content -LiteralPath $summaryPath -Value ($summaryLines -join "`n") -Encoding UTF8

Write-Host ""
Write-Host "Run complete."
Write-Host "  manifest: $manifestPath"
Write-Host "  summary:  $summaryPath"
Write-Host "  os.csv:   $csvPath"

$summarizePs1 = Join-Path $LaneADir 'summarize-os.ps1'
if (Test-Path -LiteralPath $summarizePs1) {
    try {
        & $summarizePs1 -RunDir $RunDir
        Write-Host "  os-summary: $(Join-Path $RunDir 'os-summary.md')"
    } catch {
        Write-Host "Warning: summarize-os.ps1 failed: $_"
    }
}
Write-Host ""

if ($timedOut) {
    exit 2
}

$failed = @($exitSummary | Where-Object { $_.ExitCode -ne 0 })
if ($failed.Count -gt 0) {
    exit 1
}

exit 0
