# Install or update the ChessHarness Windows service via NSSM.

#

# Creates .chess_harness\logs, sets CHESS_HARNESS_PUBLIC_URL and

# CHESS_HARNESS_TRUSTED_PROXIES (merges with any existing AppEnvironmentExtra

# entries), enables log rotation, and restarts the process on failure.

# Run from an elevated PowerShell.

#

# Usage:

#   .\deploy\install-harness-nssm.ps1

#   .\deploy\install-harness-nssm.ps1 -RepoRoot "D:\chess-vision-harness" -PublicUrl "https://chessvisionharness.pages.dev"

#

# Requires NSSM on PATH (https://nssm.cc/) or pass -NssmPath.



[CmdletBinding()]

param(

    [string]$RepoRoot = "",

    [string]$ServiceName = "ChessHarness",

    [string]$PublicUrl = "https://chessvisionharness.pages.dev",

    [string]$TrustedProxies = "127.0.0.0/8",

    [string]$NssmPath = "nssm",

    [switch]$Start

)



$ErrorActionPreference = "Stop"



function Resolve-NssmExe {

    param([string]$Candidate)

    if ([System.IO.Path]::IsPathRooted($Candidate) -and (Test-Path -LiteralPath $Candidate)) {

        return (Resolve-Path -LiteralPath $Candidate).Path

    }

    $cmd = Get-Command $Candidate -ErrorAction SilentlyContinue

    if ($cmd) { return $cmd.Source }

    throw "NSSM not found. Install from https://nssm.cc/ and add nssm.exe to PATH, or pass -NssmPath."

}



function Invoke-Nssm {

    param([string[]]$Args)

    & $script:NssmExe @Args

    if ($LASTEXITCODE -ne 0) {

        throw "nssm $($Args -join ' ') failed with exit code $LASTEXITCODE"

    }

}



function Get-NssmAppEnvironmentExtra {

    param([string]$ServiceName)

    $envMap = [ordered]@{}

    try {

        $raw = & $script:NssmExe get $ServiceName AppEnvironmentExtra 2>$null

        if ($LASTEXITCODE -ne 0) { return $envMap }

        foreach ($line in ($raw -split "`r?`n")) {

            $line = $line.Trim()

            if (-not $line) { continue }

            $eq = $line.IndexOf("=")

            if ($eq -lt 1) { continue }

            $key = $line.Substring(0, $eq)

            $value = $line.Substring($eq + 1)

            $envMap[$key] = $value

        }

    } catch {

        # Service may not exist yet; start with empty map.

    }

    return $envMap

}



function Format-NssmAppEnvironmentExtra {

    param([System.Collections.IDictionary]$EnvMap)

    return ($EnvMap.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "`n"

}



if (-not $RepoRoot) {

    $RepoRoot = Split-Path -Parent $PSScriptRoot

}

$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path



$HarnessExe = Join-Path $RepoRoot ".venv\Scripts\chess-harness.exe"

if (-not (Test-Path -LiteralPath $HarnessExe)) {

    $cmd = Get-Command "chess-harness.exe" -ErrorAction SilentlyContinue

    if ($cmd -and $cmd.Source) {

        $HarnessExe = $cmd.Source

        Write-Host "Using chess-harness from PATH: $HarnessExe"

    } else {

        $userScripts = Join-Path $env:APPDATA "Python\Python313\Scripts\chess-harness.exe"

        if (Test-Path -LiteralPath $userScripts) {

            $HarnessExe = $userScripts

            Write-Host "Using chess-harness from user Scripts: $HarnessExe"

        } else {

            throw "chess-harness.exe not found at $HarnessExe (or PATH / %APPDATA%\Python\Python313\Scripts). Create a venv and run: pip install -e `"python/[dev]`""

        }

    }

}



$LogsDir = Join-Path $RepoRoot ".chess_harness\logs"

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null



$PublicUrl = $PublicUrl.Trim().TrimEnd("/")

if (-not $PublicUrl) {

    throw "PublicUrl must not be empty."

}



$TrustedProxies = $TrustedProxies.Trim()

if (-not $TrustedProxies) {

    throw "TrustedProxies must not be empty."

}



$script:NssmExe = Resolve-NssmExe -Candidate $NssmPath



$StdoutLog = Join-Path $LogsDir "harness.log"

$StderrLog = Join-Path $LogsDir "harness.err.log"



$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

if ($existing) {

    Write-Host "Updating existing service '$ServiceName'..."

    if ($existing.Status -eq "Running") {

        Invoke-Nssm @("stop", $ServiceName)

        Start-Sleep -Seconds 2

    }

} else {

    Write-Host "Installing service '$ServiceName'..."

    Invoke-Nssm @("install", $ServiceName, $HarnessExe, "serve")

}



$envExtra = Get-NssmAppEnvironmentExtra -ServiceName $ServiceName

$envExtra["CHESS_HARNESS_PUBLIC_URL"] = $PublicUrl

$envExtra["CHESS_HARNESS_TRUSTED_PROXIES"] = $TrustedProxies

$envExtraText = Format-NssmAppEnvironmentExtra -EnvMap $envExtra



Invoke-Nssm @("set", $ServiceName, "AppDirectory", $RepoRoot)

Invoke-Nssm @("set", $ServiceName, "AppEnvironmentExtra", $envExtraText)

Invoke-Nssm @("set", $ServiceName, "AppStdout", $StdoutLog)

Invoke-Nssm @("set", $ServiceName, "AppStderr", $StderrLog)

Invoke-Nssm @("set", $ServiceName, "AppStdoutCreationDisposition", "4")

Invoke-Nssm @("set", $ServiceName, "AppStderrCreationDisposition", "4")

Invoke-Nssm @("set", $ServiceName, "AppRotateFiles", "1")

Invoke-Nssm @("set", $ServiceName, "AppRotateBytes", "10485760")

Invoke-Nssm @("set", $ServiceName, "AppRotateOnline", "1")

Invoke-Nssm @("set", $ServiceName, "AppExit", "Default", "Restart")

Invoke-Nssm @("set", $ServiceName, "AppRestartDelay", "5000")

Invoke-Nssm @("set", $ServiceName, "AppThrottle", "15000")

Invoke-Nssm @("set", $ServiceName, "Description", "Chess Vision Harness - chess-harness serve on 127.0.0.1:8765")



Set-Service -Name $ServiceName -StartupType Automatic



if ($Start -or -not $existing) {

    Invoke-Nssm @("start", $ServiceName)

    Write-Host "Started $ServiceName."

} else {

    Invoke-Nssm @("restart", $ServiceName)

    Write-Host "Restarted $ServiceName."

}



Write-Host ""

Write-Host "Harness service configured."

Write-Host "  Repo:            $RepoRoot"

Write-Host "  Public URL:      $PublicUrl  (agent briefs - not GAME_ORIGIN)"

Write-Host "  Trusted proxies: $TrustedProxies  (client IP through tunnel/Pages)"

Write-Host "  Logs:            $LogsDir"

Write-Host ""

Write-Host "After reboot, localhost should recover in a few minutes:"

Write-Host "  curl http://127.0.0.1:8765/health"

Write-Host ""

Write-Host "Public Online still needs a live Quick Tunnel + GAME_ORIGIN refresh - see deploy\home-pc.md"


