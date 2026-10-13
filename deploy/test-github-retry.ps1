# Offline regression checks; run with Windows PowerShell (the desktop launcher).
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'github-retry.ps1')

function Assert-True($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Start-Sleep {
    param([int]$Seconds)
    $script:delays += $Seconds
}

function gh {
    $script:calls++
    $script:seenArguments = @($args)
    $reply = $script:replies[[Math]::Min($script:calls - 1, $script:replies.Count - 1)]
    if ($reply -eq 'ok') {
        $global:LASTEXITCODE = 0
    } else {
        # Real native stderr exercises Windows PowerShell's ErrorRecord behavior.
        & powershell.exe -NoProfile -Command "[Console]::Error.WriteLine('$reply'); exit 1"
        $global:LASTEXITCODE = $LASTEXITCODE
    }
}

function Reset-Stub([string[]]$Replies) {
    $script:replies = $Replies
    $script:calls = 0
    $script:delays = @()
}

Reset-Stub @('ok')
Invoke-GitHubWithRetry -Arguments @('workflow', 'run', 'Deploy public site') -Operation 'Deploy'
Assert-True ($script:calls -eq 1 -and $script:delays.Count -eq 0) 'Success must not retry.'
Assert-True ($script:seenArguments.Count -eq 3 -and $script:seenArguments[2] -eq 'Deploy public site') 'Workflow name must remain a single argument.'

Reset-Stub @('failed to fetch public key: net/http: TLS handshake timeout', 'HTTP 502 Bad Gateway', 'ok')
Invoke-GitHubWithRetry -Arguments @('secret', 'set', 'GAME_ORIGIN', '-b', 'https://example.trycloudflare.com') -Operation 'Secret'
Assert-True ($script:calls -eq 3 -and ($script:delays -join ',') -eq '2,4') 'Temporary errors must retry with backoff.'
Assert-True ($ErrorActionPreference -eq 'Stop') 'ErrorActionPreference must be restored.'

Reset-Stub @('HTTP 403 Resource not accessible')
$failed = $false
try { Invoke-GitHubWithRetry -Arguments @('secret', 'set') -Operation 'Secret' } catch { $failed = $true }
Assert-True ($failed -and $script:calls -eq 1 -and $script:delays.Count -eq 0) 'Permission errors must fail immediately.'

Reset-Stub @('net/http: TLS handshake timeout')
$failed = $false
try { Invoke-GitHubWithRetry -Arguments @('secret', 'set') -Operation 'Secret' } catch { $failed = $_.Exception.Message -match 'attempt 4 of 4' }
Assert-True ($failed -and $script:calls -eq 4 -and ($script:delays -join ',') -eq '2,4,8') 'Persistent errors must stop after four attempts.'
Write-Host 'All GitHub retry checks passed.' -ForegroundColor Green
