# Bring public Online after reboot (or when Sleeping): ensure harness is up,
# start/reuse a Quick Tunnel, set GitHub GAME_ORIGIN, redeploy Pages, verify.
#
# Does NOT claim zero-touch Online — Quick Tunnel URLs change on restart.
# Harness reboot durability is separate (install-harness-nssm.ps1).
#
# Usage (repo root, network + gh auth):
#   .\deploy\go-online.ps1
#   .\deploy\go-online.ps1 -SkipDeploy   # tunnel + secret only
#   .\deploy\go-online.ps1 -PagesUrl "https://chessvisionharness.pages.dev"
#   .\deploy\go-online.ps1 -InstallShortcut   # Desktop .lnk -> deploy\Start-Online.bat
#   deploy\Start-Online.bat   # double-click entry (same script, visible window on failure)
#
# Manual serve (no NSSM): always restarts so agent briefs get CHESS_HARNESS_PUBLIC_URL
# (the Pages URL), not 127.0.0.1. NSSM keeps its own service env from install.
# Prerequisites: cloudflared on PATH or default install path, GitHub CLI logged in.

[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$HarnessUrl = "http://127.0.0.1:8765",
    [string]$PagesUrl = "https://chessvisionharness.pages.dev",
    [string]$ServiceName = "ChessHarness",
    [string]$CloudflaredPath = "",
    [string]$TunnelLogPath = "",
    [int]$HarnessWaitSec = 120,
    [int]$TunnelWaitSec = 90,
    [int]$EdgeWaitSec = 180,
    [switch]$SkipDeploy,
    [switch]$SkipVerify,
    [switch]$InstallShortcut
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path

if (-not $TunnelLogPath) {
    $TunnelLogPath = Join-Path $RepoRoot ".chess_harness\logs\quick-tunnel.log"
}
$TunnelPidPath = Join-Path $RepoRoot ".chess_harness\logs\quick-tunnel.pid"
$TunnelUrlPath = Join-Path $RepoRoot ".chess_harness\logs\quick-tunnel.url"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $TunnelLogPath) | Out-Null

function Install-StartOnlineShortcut {
    param([string]$Root)
    $batPath = Join-Path $Root "deploy\Start-Online.bat"
    if (-not (Test-Path -LiteralPath $batPath)) {
        throw "Start-Online.bat not found at $batPath"
    }
    $desktop = [Environment]::GetFolderPath("Desktop")
    $lnkPath = Join-Path $desktop "Chess Vision Harness Go Online.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($lnkPath)
    $shortcut.TargetPath = $batPath
    $shortcut.WorkingDirectory = $Root
    $shortcut.Description = "Start localhost harness (if needed) and public Online (Quick Tunnel + Pages)."
    $shortcut.Save()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null
    Write-Host "Desktop shortcut created: $lnkPath"
    Write-Host "Double-click it to run go-online (no admin; does not install or start NSSM)."
}

function Resolve-Cloudflared {
    param([string]$Candidate)
    if ($Candidate -and (Test-Path -LiteralPath $Candidate)) {
        return (Resolve-Path -LiteralPath $Candidate).Path
    }
    $cmd = Get-Command "cloudflared.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $default = "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe"
    if (Test-Path -LiteralPath $default) { return $default }
    $default2 = "$env:ProgramFiles\cloudflared\cloudflared.exe"
    if (Test-Path -LiteralPath $default2) { return $default2 }
    throw "cloudflared.exe not found. Install Cloudflare Tunnel or pass -CloudflaredPath."
}

function Test-LocalHealth {
    param([string]$BaseUrl)
    try {
        $res = Invoke-WebRequest -Uri "$($BaseUrl.TrimEnd('/'))/health" -UseBasicParsing -TimeoutSec 8
        $body = $res.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
        return ($body.ok -eq $true -or $body.status -eq "up")
    } catch {
        return $false
    }
}

function Wait-LocalHealth {
    param([string]$BaseUrl, [int]$TimeoutSec)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-LocalHealth -BaseUrl $BaseUrl) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Set-HarnessBriefEnv {
    param([string]$Pages)
    $env:CHESS_HARNESS_PUBLIC_URL = $Pages.TrimEnd("/")
    $env:CHESS_HARNESS_TRUSTED_PROXIES = "127.0.0.0/8"
    Write-Host "Agent briefs will use $($env:CHESS_HARNESS_PUBLIC_URL)"
}

function Resolve-HarnessExe {
    $cmd = Get-Command "chess-harness.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = Join-Path $env:APPDATA "Python\Python313\Scripts\chess-harness.exe"
    if (Test-Path -LiteralPath $fallback) { return $fallback }
    return $null
}

function Stop-ManualHarness {
    param([string]$ExePath)
    Write-Host "Stopping localhost serve so the next process picks up the Pages URL..."
    try {
        if ($ExePath) {
            & $ExePath @("serve", "stop")
        } else {
            $py = Join-Path $RepoRoot "python"
            Push-Location $py
            try {
                python -m chess_harness serve stop
            } finally {
                Pop-Location
            }
        }
    } catch {
        Write-Host "serve stop: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 2
}

function Start-ManualHarness {
    param([string]$ExePath)
    if (-not $ExePath) {
        throw "chess-harness.exe not found and service '$ServiceName' missing."
    }
    $serveOut = Join-Path $RepoRoot ".chess_harness\logs\harness-manual.log.out"
    $serveErr = Join-Path $RepoRoot ".chess_harness\logs\harness-manual.log.err"
    foreach ($f in @($serveOut, $serveErr)) {
        if (Test-Path -LiteralPath $f) {
            Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
        }
    }
    # Start-Process forbids RedirectStandardOutput == RedirectStandardError
    $p = Start-Process -FilePath $ExePath -ArgumentList @("serve", "--force") -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $serveOut -RedirectStandardError $serveErr -PassThru -WindowStyle Hidden
    Write-Host "Started chess-harness serve (pid $($p.Id)); log: $serveOut"
}

function Ensure-Harness {
    param([string]$BaseUrl, [string]$SvcName, [int]$WaitSec)
    Set-HarnessBriefEnv -Pages $PagesUrl
    $svc = Get-Service -Name $SvcName -ErrorAction SilentlyContinue
    if ($svc) {
        if ($svc.Status -ne "Running") {
            Write-Host "Starting Windows service '$SvcName'..."
            Start-Service -Name $SvcName
        } else {
            Write-Host "Service '$SvcName' is already running (brief URL comes from the service env)."
        }
    } else {
        $exePath = Resolve-HarnessExe
        if (Test-LocalHealth -BaseUrl $BaseUrl) {
            Stop-ManualHarness -ExePath $exePath
        } else {
            Write-Host "No '$SvcName' service. Starting chess-harness serve (background)..."
        }
        Start-ManualHarness -ExePath $exePath
    }
    if (-not (Wait-LocalHealth -BaseUrl $BaseUrl -TimeoutSec $WaitSec)) {
        throw "Harness did not become healthy within ${WaitSec}s at $BaseUrl/health"
    }
    Write-Host "Harness healthy."
}

function Stop-TrackedQuickTunnel {
    if (Test-Path -LiteralPath $TunnelPidPath) {
        $oldPid = (Get-Content -LiteralPath $TunnelPidPath -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
        if ($oldPid -match '^\d+$') {
            $proc = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
            if ($proc -and $proc.ProcessName -match 'cloudflared') {
                Write-Host "Stopping previous Quick Tunnel pid $oldPid..."
                Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1
            }
        }
        Remove-Item -LiteralPath $TunnelPidPath -Force -ErrorAction SilentlyContinue
    }
}

function Start-QuickTunnel {
    param([string]$CfPath, [string]$OriginUrl, [int]$WaitSec)
    Stop-TrackedQuickTunnel
    $outLog = "$TunnelLogPath.out"
    $errLog = "$TunnelLogPath.err"
    foreach ($f in @($TunnelLogPath, $outLog, $errLog)) {
        if (Test-Path -LiteralPath $f) {
            Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "Starting Quick Tunnel -> $OriginUrl ..."
    # Start-Process forbids RedirectStandardOutput == RedirectStandardError
    $p = Start-Process -FilePath $CfPath `
        -ArgumentList @("tunnel", "--url", $OriginUrl) `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru -WindowStyle Hidden
    Set-Content -LiteralPath $TunnelPidPath -Value "$($p.Id)" -Encoding ascii
    $deadline = (Get-Date).AddSeconds($WaitSec)
    $url = $null
    while ((Get-Date) -lt $deadline) {
        $chunks = @()
        foreach ($f in @($outLog, $errLog)) {
            if (Test-Path -LiteralPath $f) {
                $chunks += Get-Content -LiteralPath $f -Raw -ErrorAction SilentlyContinue
            }
        }
        $text = ($chunks -join "`n")
        if ($text) {
            Set-Content -LiteralPath $TunnelLogPath -Value $text -Encoding utf8
            if ($text -match 'https://[a-z0-9-]+\.trycloudflare\.com') {
                $url = $Matches[0].TrimEnd('/')
                break
            }
        }
        if ($p.HasExited) {
            throw "cloudflared exited early (code $($p.ExitCode)). See $TunnelLogPath"
        }
        Start-Sleep -Seconds 2
    }
    if (-not $url) {
        throw "Timed out waiting for trycloudflare.com URL. See $TunnelLogPath"
    }
    Set-Content -LiteralPath $TunnelUrlPath -Value $url -Encoding ascii
    Write-Host "Quick Tunnel URL: $url"
    return $url
}

function Wait-OriginHealth {
    param([string]$Origin, [int]$TimeoutSec)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $res = Invoke-WebRequest -Uri "$Origin/health" -UseBasicParsing -TimeoutSec 10
            $body = $res.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($body.ok -eq $true -or $body.status -eq "up") { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

# --- main ---
Write-Host "=== Go Online ==="
Write-Host "Repo: $RepoRoot"

if ($InstallShortcut) {
    Install-StartOnlineShortcut -Root $RepoRoot
    return
}

Ensure-Harness -BaseUrl $HarnessUrl -SvcName $ServiceName -WaitSec $HarnessWaitSec

$cf = Resolve-Cloudflared -Candidate $CloudflaredPath
$origin = Start-QuickTunnel -CfPath $cf -OriginUrl $HarnessUrl -WaitSec $TunnelWaitSec

if (-not (Wait-OriginHealth -Origin $origin -TimeoutSec 60)) {
    throw "Tunnel URL up but $origin/health did not respond in time"
}
Write-Host "Origin /health OK via tunnel."

Write-Host "Setting GitHub secret GAME_ORIGIN..."
& gh secret set GAME_ORIGIN -b $origin
if ($LASTEXITCODE -ne 0) { throw "gh secret set GAME_ORIGIN failed (exit $LASTEXITCODE)" }

if (-not $SkipDeploy) {
    Write-Host "Triggering Pages deploy..."
    & gh workflow run "Deploy public site"
    if ($LASTEXITCODE -ne 0) { throw "gh workflow run failed (exit $LASTEXITCODE)" }
    Write-Host "Deploy requested. If edge-health stays Sleeping, run once more: gh workflow run `"Deploy public site`""
}

if (-not $SkipVerify) {
    Write-Host "Waiting for Pages edge-health (up to ${EdgeWaitSec}s)..."
    $verify = Join-Path $PSScriptRoot "verify-online.ps1"
    $deadline = (Get-Date).AddSeconds($EdgeWaitSec)
    $exit = 3
    while ((Get-Date) -lt $deadline) {
        & $verify -GameOrigin $origin -PagesUrl $PagesUrl
        $exit = $LASTEXITCODE
        if ($exit -eq 0) { break }
        if ($exit -eq 1 -or $exit -eq 2 -or $exit -eq 4) { break }
        # exit 3 = Pages not online yet; wait and retry (secret race)
        Start-Sleep -Seconds 15
    }
    if ($exit -eq 3) {
        Write-Host "Edge still not online — redeploying once more (secret race)..."
        & gh workflow run "Deploy public site"
        Start-Sleep -Seconds 25
        & $verify -GameOrigin $origin -PagesUrl $PagesUrl
        $exit = $LASTEXITCODE
    }
    if ($exit -ne 0) {
        Write-Host "verify-online exited $exit — see deploy/home-pc.md Sleeping runbook." -ForegroundColor Yellow
        exit $exit
    }
}

Write-Host ""
Write-Host "Public Online ready." -ForegroundColor Green
Write-Host "  GAME_ORIGIN: $origin"
Write-Host "  Pages:       $PagesUrl"
Write-Host "  Agent briefs: $($PagesUrl.TrimEnd('/'))"
Write-Host "  Tunnel pid:  $(Get-Content $TunnelPidPath -ErrorAction SilentlyContinue)"
Write-Host "After next reboot: harness should auto-start (logon Startup / HKCU Run); run this script again for Online."
