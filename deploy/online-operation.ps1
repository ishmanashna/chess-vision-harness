# Shared desktop/panel operation record. The open handle is the cross-process lock.
function Open-OnlineOperation {
    param([string]$Logs, [string]$OperationId = "", [string]$Source = "desktop")
    New-Item -ItemType Directory -Force -Path $Logs | Out-Null
    try {
        $script:OnlineLock = [IO.File]::Open((Join-Path $Logs "go-online.lock"), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch { throw "Go Online or Sleep is already running. See Ops for status." }
    if (-not $OperationId) { $OperationId = "go-online-" + [guid]::NewGuid().ToString('N').Substring(0,12) }
    $script:OnlineStatusPath = Join-Path $Logs "go-online-status.json"
    $script:OnlineState = [ordered]@{
        schema_version = 1; job_id = $OperationId; source = $Source; pid = $PID
        status = 'running'; phase = 'Starting'; started_at = [DateTime]::UtcNow.ToString('o')
        updated_at = ''; finished_at = $null; exit_code = $null; failure_reason = $null
    }
    try { Set-OnlinePhase 'Starting' }
    catch { $script:OnlineLock.Dispose(); throw }
}

function Set-OnlinePhase {
    param([string]$Phase)
    $script:OnlineState.phase = $Phase
    $script:OnlineState.updated_at = [DateTime]::UtcNow.ToString('o')
    $temporary = $script:OnlineStatusPath + '.tmp'
    [IO.File]::WriteAllText($temporary, ($script:OnlineState | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    if ([IO.File]::Exists($script:OnlineStatusPath)) {
        # A short-lived Python reader can deny delete sharing on Windows.
        for ($attempt = 0; ; $attempt++) {
            try {
                [IO.File]::Replace($temporary, $script:OnlineStatusPath, [System.Management.Automation.Language.NullString]::Value)
                break
            } catch [IO.IOException] {
                if ($attempt -ge 10) { throw }
                Start-Sleep -Milliseconds 50
            }
        }
    } else { [IO.File]::Move($temporary, $script:OnlineStatusPath) }
}

function Close-OnlineOperation {
    param([int]$Code = 0, [string]$Reason = '')
    try {
        $script:OnlineState.status = if ($Code -eq 0) { 'ok' } else { 'fail' }
        $script:OnlineState.exit_code = $Code
        $script:OnlineState.finished_at = [DateTime]::UtcNow.ToString('o')
        $script:OnlineState.failure_reason = $Reason
        Set-OnlinePhase $(if ($Code -eq 0) { 'Public Online ready' } else { $script:OnlineState.phase })
    } finally { $script:OnlineLock.Dispose() }
}
