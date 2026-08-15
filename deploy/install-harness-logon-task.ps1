# Register ChessHarness to start at user logon (no admin).
# Uses HKCU Run + Startup folder. Prefer install-harness-nssm.ps1 when you can
# elevate — that survives before logon and restarts on crash.
#
# Usage:
#   .\deploy\install-harness-logon-task.ps1
#   .\deploy\install-harness-logon-task.ps1 -Remove
#   .\deploy\install-harness-logon-task.ps1 -StartNow

[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$RunValueName = "ChessHarnessServe",
    [switch]$Remove,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

$logs = Join-Path $RepoRoot ".chess_harness\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$wrapper = Join-Path $logs "start-harness-startup.cmd"
$outLog = Join-Path $logs "harness-startup.out.log"
$errLog = Join-Path $logs "harness-startup.err.log"
$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$startupCmd = Join-Path $startupDir "ChessHarnessServe.cmd"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

if ($Remove) {
    Remove-ItemProperty -Path $runKey -Name $RunValueName -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $startupCmd -Force -ErrorAction SilentlyContinue
    Write-Host "Removed logon auto-start ($RunValueName / Startup cmd)."
    return
}

$py = $null
foreach ($c in @(
    (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    "C:\Program Files\Python313\python.exe",
    "C:\Program Files\Python312\python.exe"
)) {
    if ($c -and (Test-Path -LiteralPath $c)) { $py = $c; break }
}
if (-not $py) { throw "python.exe not found" }

$pythonDir = Join-Path $RepoRoot "python"
@"
@echo off
set CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev
set CHESS_HARNESS_TRUSTED_PROXIES=127.0.0.0/8
cd /d "$pythonDir"
"$py" -m chess_harness serve --force >> "$outLog" 2>> "$errLog"
"@ | Set-Content -LiteralPath $wrapper -Encoding ASCII

New-Item -ItemType Directory -Force -Path $startupDir | Out-Null
Copy-Item -LiteralPath $wrapper -Destination $startupCmd -Force
Set-ItemProperty -Path $runKey -Name $RunValueName -Value "`"$wrapper`""

Write-Host "Logon auto-start registered (no admin):"
Write-Host "  HKCU Run:  $RunValueName"
Write-Host "  Startup:   $startupCmd"
Write-Host "  Wrapper:   $wrapper"
Write-Host "After reboot/logon, wait ~30s then: curl http://127.0.0.1:8765/health"
Write-Host "Public Online still needs: .\deploy\go-online.ps1"

if ($StartNow) {
    Write-Host "Starting harness now..."
    Start-Process -FilePath $wrapper -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" -UseBasicParsing -TimeoutSec 5
            $b = $r.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($b.ok -eq $true -or $b.status -eq "up") {
                Write-Host "Harness healthy."
                return
            }
        } catch { }
        Start-Sleep -Seconds 2
    }
    Write-Host "Harness not healthy yet - check $errLog" -ForegroundColor Yellow
}
