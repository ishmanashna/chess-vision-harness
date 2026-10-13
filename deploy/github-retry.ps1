# Retry temporary GitHub transport/API failures without hiding auth/config errors.
function Invoke-GitHubWithRetry {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Operation,
        [ValidateRange(1, 10)][int]$MaxAttempts = 4
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        # Windows PowerShell turns native stderr into ErrorRecords. Capture it
        # with Continue so a TLS error reaches our exit-code/retry handling.
        $previousPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $output = @(& gh @Arguments 2>&1)
            $code = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousPreference
        }
        foreach ($line in $output) { Write-Host "$line" }
        if ($code -eq 0) { return }

        $detail = $output -join "`n"
        $transient = $detail -match '(?i)TLS handshake timeout|i/o timeout|context deadline exceeded|connection (reset|refused)|temporary failure|no such host|unexpected EOF|\bEOF\b|HTTP 5\d\d\b|HTTP 429\b'
        if (-not $transient -or $attempt -eq $MaxAttempts) {
            throw "$Operation failed (exit $code; attempt $attempt of $MaxAttempts). Localhost and the Quick Tunnel remain running. Check GitHub connectivity/authentication and run Go Online again."
        }
        $delay = [int][Math]::Pow(2, $attempt)
        Write-Host "$Operation hit a temporary GitHub error; retrying in ${delay}s (attempt $($attempt + 1)/$MaxAttempts)..." -ForegroundColor Yellow
        Start-Sleep -Seconds $delay
    }
}
