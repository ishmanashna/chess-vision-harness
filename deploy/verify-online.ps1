# Probe harness liveness vs public Online (Pages edge-health).
#
# Three checks (Sleeping runbook card):
#   1. http://127.0.0.1:8765/health           — harness on this PC
#   2. {GAME_ORIGIN}/health                   — tunnel/origin Cloudflare Pages uses
#   3. https://chessvisionharness.pages.dev/api/edge-health — public Online signal
#
# Exit codes:
#   0 — all probes healthy (Public Online)
#   1 — local harness unhealthy (probe 1 failed)
#   2 — harness OK; GAME_ORIGIN probe failed (stale Quick Tunnel, named tunnel without public hostname, or tunnel down)
#   3 — harness + GAME_ORIGIN OK; Pages edge-health not online (secret/deploy race or Pages env stale)
#   4 — configuration error (missing GAME_ORIGIN when required)
#
# Usage:
#   .\deploy\verify-online.ps1
#   .\deploy\verify-online.ps1 -GameOrigin "https://abc.trycloudflare.com"
#   $env:GAME_ORIGIN = "https://abc.trycloudflare.com"; .\deploy\verify-online.ps1
#
# Schedule when the PC is expected Online (Task Scheduler). A non-zero exit means follow home-pc.md recovery.

[CmdletBinding()]
param(
    [string]$HarnessUrl = "http://127.0.0.1:8765",
    [string]$GameOrigin = "",
    [string]$PagesUrl = "https://chessvisionharness.pages.dev",
    [int]$TimeoutSec = 15
)

$ErrorActionPreference = "Continue"

function Test-HarnessHealth {
    param([string]$BaseUrl)
    $url = "$($BaseUrl.TrimEnd('/'))/health"
    try {
        $res = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $TimeoutSec
        if ($res.StatusCode -lt 200 -or $res.StatusCode -ge 300) {
            return @{ Ok = $false; Url = $url; Detail = "HTTP $($res.StatusCode)" }
        }
        $body = $res.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($body.ok -eq $true -or $body.status -eq "up") {
            return @{ Ok = $true; Url = $url; Detail = "ok" }
        }
        return @{ Ok = $false; Url = $url; Detail = "unexpected JSON payload" }
    } catch {
        return @{ Ok = $false; Url = $url; Detail = $_.Exception.Message }
    }
}

function Test-EdgeHealth {
    param([string]$BaseUrl)
    $url = "$($BaseUrl.TrimEnd('/'))/api/edge-health"
    try {
        $res = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $TimeoutSec
        if ($res.StatusCode -lt 200 -or $res.StatusCode -ge 300) {
            return @{ Ok = $false; Url = $url; Detail = "HTTP $($res.StatusCode)"; Online = $false; Origin = $null }
        }
        $body = $res.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
        $online = ($body.online -eq $true) -or ($body.status -eq "online")
        $origin = $body.origin
        if ($online) {
            return @{ Ok = $true; Url = $url; Detail = "online"; Online = $true; Origin = $origin }
        }
        $msg = if ($body.message) { $body.message } else { "offline" }
        return @{ Ok = $false; Url = $url; Detail = $msg; Online = $false; Origin = $origin }
    } catch {
        return @{ Ok = $false; Url = $url; Detail = $_.Exception.Message; Online = $false; Origin = $null }
    }
}

function Write-ProbeLine {
    param([string]$Label, [hashtable]$Result)
    $mark = if ($Result.Ok) { "OK" } else { "FAIL" }
    $color = if ($Result.Ok) { "Green" } else { "Red" }
    Write-Host ("[{0}] {1}" -f $mark, $Label) -ForegroundColor $color
    Write-Host ("       {0}" -f $Result.Url)
    if (-not $Result.Ok) {
        Write-Host ("       {0}" -f $Result.Detail) -ForegroundColor DarkYellow
    }
}

$HarnessUrl = $HarnessUrl.Trim().TrimEnd("/")
$PagesUrl = $PagesUrl.Trim().TrimEnd("/")
$GameOrigin = $GameOrigin.Trim().TrimEnd("/")
if (-not $GameOrigin -and $env:GAME_ORIGIN) {
    $GameOrigin = $env:GAME_ORIGIN.Trim().TrimEnd("/")
}

Write-Host "Chess Vision Harness - Online verification"
Write-Host ""

$p1 = Test-HarnessHealth -BaseUrl $HarnessUrl
Write-ProbeLine -Label "Harness (localhost)" -Result $p1

if (-not $p1.Ok) {
    Write-Host ""
    Write-Host "Exit 1: harness unhealthy. Check NSSM service ChessHarness and $HarnessUrl/health" -ForegroundColor Red
    exit 1
}

if (-not $GameOrigin) {
    Write-Host ""
    Write-Host "[SKIP] GAME_ORIGIN probe - pass -GameOrigin or set `$env:GAME_ORIGIN" -ForegroundColor Yellow
    Write-Host "Exit 4: GAME_ORIGIN required for full Online check." -ForegroundColor Yellow
    exit 4
}

$p2 = Test-HarnessHealth -BaseUrl $GameOrigin
Write-ProbeLine -Label "GAME_ORIGIN (tunnel)" -Result $p2

if (-not $p2.Ok) {
    Write-Host ""
    Write-Host "Exit 2: harness is up but GAME_ORIGIN is unreachable." -ForegroundColor Red
    Write-Host "  A named cloudflared service without a public hostname does NOT make Pages Online."
    Write-Host "  Recovery: start Quick Tunnel, copy URL, update GAME_ORIGIN secret, redeploy Pages (see deploy\home-pc.md)."
    exit 2
}

$p3 = Test-EdgeHealth -BaseUrl $PagesUrl
Write-ProbeLine -Label "Pages edge-health" -Result $p3

if (-not $p3.Ok) {
    Write-Host ""
    if ($p3.Origin -eq $false) {
        Write-Host "  edge-health: GAME_ORIGIN not configured on Pages - set secret and redeploy."
    } elseif ($p3.Origin -eq $true -and -not $p3.Online) {
        Write-Host "  edge-health: origin configured but unreachable from Cloudflare (stale secret or deploy pending)."
    }
    Write-Host ""
    Write-Host "Exit 3: tunnel OK from PC but public site not Online." -ForegroundColor Red
    Write-Host "  Redeploy Pages again when the secret just changed (deploy race)."
    exit 3
}

Write-Host ""
Write-Host "Exit 0: Public Online - all probes healthy." -ForegroundColor Green
exit 0
