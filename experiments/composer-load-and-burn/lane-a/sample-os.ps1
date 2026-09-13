# Lane A OS sampler — WMI/Cim (Spanish-locale safe). One os.csv with phase=baseline|hot.
# From repo root:
#   .\experiments\composer-load-and-burn\lane-a\sample-os.ps1 -OutDir <dir> -Phase baseline -DurationSec 90
#   .\experiments\composer-load-and-burn\lane-a\sample-os.ps1 -OutDir <dir> -Phase hot
#   .\experiments\composer-load-and-burn\lane-a\sample-os.ps1 -OutDir <dir> -Phase baseline -Once

param(
    [Parameter(Mandatory = $true)]
    [string]$OutDir,

    [Parameter(Mandatory = $true)]
    [ValidateSet('baseline', 'hot')]
    [string]$Phase,

    [int]$IntervalSec = 5,

    [switch]$Once,

    [int]$DurationSec = 0
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}

$CsvPath = Join-Path $OutDir 'os.csv'
$Header = @(
    'timestamp_iso_local'
    'phase'
    'cpu_load_pct'
    'ram_total_gb'
    'ram_free_gb'
    'ram_used_gb'
    'commit_used_gb'
    'commit_limit_gb'
    'commit_pct'
    'disk_c_free_gb'
    'proc_total'
    'proc_count_cursor'
    'proc_ws_mb_cursor_sum'
    'proc_count_node'
    'proc_ws_mb_node_sum'
    'proc_count_agentish'
    'proc_ws_mb_agentish_sum'
    'proc_count_python'
    'proc_ws_mb_python_sum'
    'top_proc_name'
    'top_proc_ws_mb'
) -join ','

function Format-CsvNumber {
    param(
        [double]$Value,
        [int]$Decimals = 3
    )
    $inv = [System.Globalization.CultureInfo]::InvariantCulture
    return $Value.ToString("F$Decimals", $inv)
}

function Escape-CsvField {
    param([string]$Text)
    if ($null -eq $Text) { return '' }
    if ($Text -match '[,"\r\n]') {
        return '"' + ($Text.Replace('"', '""')) + '"'
    }
    return $Text
}

function Test-AgentishProcess {
    param([System.Diagnostics.Process]$Proc)
    if ($null -eq $Proc) { return $false }
    $name = [string]$Proc.Name
    if ($name -match '(?i)agent') { return $true }
    try {
        $path = [string]$Proc.Path
    } catch {
        $path = ''
    }
    if ($path -match '(?i)cursor-agent' -or $path -match '(?i)\\agent') { return $true }
    return $false
}

function Get-WsMbSum {
    param([object[]]$Procs)
    if ($null -eq $Procs -or $Procs.Count -eq 0) { return 0.0 }
    $sum = ($Procs | Measure-Object -Property WorkingSet64 -Sum).Sum
    if ($null -eq $sum) { return 0.0 }
    return [math]::Round($sum / 1MB, 2)
}

function Get-SampleRow {
    param([string]$PhaseValue)

    $ts = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')

    # CPU — WMI LoadPercentage (works on ES locale; English Get-Counter often fails)
    $cpuSamples = @(Get-CimInstance -ClassName Win32_Processor |
        ForEach-Object { $_.LoadPercentage } |
        Where-Object { $null -ne $_ })
    $cpuPct = 0.0
    if ($cpuSamples.Count -gt 0) {
        $cpuPct = [math]::Round(($cpuSamples | Measure-Object -Average).Average, 2)
    }

    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $kbToGb = 1.0 / (1024 * 1024)
    $ramTotalGb = [math]::Round($os.TotalVisibleMemorySize * $kbToGb, 3)
    $ramFreeGb = [math]::Round($os.FreePhysicalMemory * $kbToGb, 3)
    $ramUsedGb = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) * $kbToGb, 3)
    $commitLimitGb = [math]::Round($os.TotalVirtualMemorySize * $kbToGb, 3)
    $commitUsedGb = [math]::Round(($os.TotalVirtualMemorySize - $os.FreeVirtualMemorySize) * $kbToGb, 3)
    $commitPct = 0.0
    if ($commitLimitGb -gt 0) {
        $commitPct = [math]::Round(100.0 * $commitUsedGb / $commitLimitGb, 2)
    }

    $diskC = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='C:'"
    $diskCFreeGb = 0.0
    if ($null -ne $diskC) {
        $diskCFreeGb = [math]::Round($diskC.FreeSpace / 1GB, 3)
    }

    # Snapshot processes once
    $all = @(Get-Process -ErrorAction SilentlyContinue)
    $procTotal = $all.Count

    $cursorProcs = @($all | Where-Object { $_.Name -eq 'Cursor' })
    $nodeProcs = @($all | Where-Object { $_.Name -eq 'node' })
    $pythonProcs = @($all | Where-Object { $_.Name -match '^(python|pythonw)$' })
    $agentish = @($all | Where-Object { Test-AgentishProcess -Proc $_ })

    $top = $all | Sort-Object WorkingSet64 -Descending | Select-Object -First 1
    $topName = if ($null -eq $top) { '' } else { [string]$top.Name }
    $topWs = if ($null -eq $top) { 0.0 } else { [math]::Round($top.WorkingSet64 / 1MB, 2) }

    return @(
        $ts
        $PhaseValue
        (Format-CsvNumber -Value $cpuPct -Decimals 2)
        (Format-CsvNumber -Value $ramTotalGb)
        (Format-CsvNumber -Value $ramFreeGb)
        (Format-CsvNumber -Value $ramUsedGb)
        (Format-CsvNumber -Value $commitUsedGb)
        (Format-CsvNumber -Value $commitLimitGb)
        (Format-CsvNumber -Value $commitPct -Decimals 2)
        (Format-CsvNumber -Value $diskCFreeGb)
        $procTotal
        $cursorProcs.Count
        (Format-CsvNumber -Value (Get-WsMbSum $cursorProcs) -Decimals 2)
        $nodeProcs.Count
        (Format-CsvNumber -Value (Get-WsMbSum $nodeProcs) -Decimals 2)
        $agentish.Count
        (Format-CsvNumber -Value (Get-WsMbSum $agentish) -Decimals 2)
        $pythonProcs.Count
        (Format-CsvNumber -Value (Get-WsMbSum $pythonProcs) -Decimals 2)
        (Escape-CsvField $topName)
        (Format-CsvNumber -Value $topWs -Decimals 2)
    ) -join ','
}

if (-not (Test-Path -LiteralPath $CsvPath)) {
    Set-Content -LiteralPath $CsvPath -Value $Header -Encoding ASCII
} else {
    # If an old thin header exists, archive it so we do not mix schemas mid-run.
    $existing = Get-Content -LiteralPath $CsvPath -TotalCount 1 -ErrorAction SilentlyContinue
    if ($existing -and ($existing -ne $Header)) {
        $bak = Join-Path $OutDir ("os-schema-mismatch-{0}.csv.bak" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
        Move-Item -LiteralPath $CsvPath -Destination $bak -Force
        Set-Content -LiteralPath $CsvPath -Value $Header -Encoding ASCII
        Write-Host "os.csv header changed — old file moved to $bak"
    }
}

$startTime = Get-Date

while ($true) {
    $row = Get-SampleRow -PhaseValue $Phase
    Add-Content -LiteralPath $CsvPath -Value $row -Encoding ASCII

    if ($Once) { break }

    if ($DurationSec -gt 0) {
        $elapsed = ((Get-Date) - $startTime).TotalSeconds
        if ($elapsed -ge $DurationSec) { break }
    }

    Start-Sleep -Seconds $IntervalSec
}
