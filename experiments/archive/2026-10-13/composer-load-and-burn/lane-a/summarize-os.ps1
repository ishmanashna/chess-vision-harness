# Summarize lane-a os.csv baseline vs hot for a run folder.
# From repo root:
#   .\experiments\composer-load-and-burn\lane-a\summarize-os.ps1 -RunDir experiments\composer-load-and-burn\lane-a\runs\<stamp>

param(
    [Parameter(Mandatory = $true)]
    [string]$RunDir
)

$ErrorActionPreference = 'Stop'
$CsvPath = Join-Path $RunDir 'os.csv'
if (-not (Test-Path -LiteralPath $CsvPath)) {
    Write-Error "os.csv not found: $CsvPath"
}

$rows = Import-Csv -LiteralPath $CsvPath
if ($rows.Count -eq 0) {
    Write-Error "os.csv has no data rows: $CsvPath"
}

function Stats-ForPhase {
    param($All, [string]$PhaseName)
    $p = @($All | Where-Object { $_.phase -eq $PhaseName })
    if ($p.Count -eq 0) {
        return $null
    }
    $num = {
        param($name)
        $vals = @($p | ForEach-Object { [double]($_.$name) })
        [PSCustomObject]@{
            mean = [math]::Round(($vals | Measure-Object -Average).Average, 2)
            max  = [math]::Round(($vals | Measure-Object -Maximum).Maximum, 2)
            min  = [math]::Round(($vals | Measure-Object -Minimum).Minimum, 2)
            last = [math]::Round($vals[-1], 2)
        }
    }
    return [PSCustomObject]@{
        n              = $p.Count
        cpu            = & $num 'cpu_load_pct'
        ram_used_gb    = & $num 'ram_used_gb'
        ram_free_gb    = & $num 'ram_free_gb'
        commit_pct     = & $num 'commit_pct'
        cursor_count   = & $num 'proc_count_cursor'
        cursor_ws_mb   = & $num 'proc_ws_mb_cursor_sum'
        node_count     = & $num 'proc_count_node'
        node_ws_mb     = & $num 'proc_ws_mb_node_sum'
        agent_count    = & $num 'proc_count_agentish'
        agent_ws_mb    = & $num 'proc_ws_mb_agentish_sum'
        python_ws_mb   = & $num 'proc_ws_mb_python_sum'
        disk_c_free_gb = & $num 'disk_c_free_gb'
    }
}

$baseline = Stats-ForPhase $rows 'baseline'
$hot = Stats-ForPhase $rows 'hot'

$md = New-Object System.Collections.Generic.List[string]
$md.Add('# OS sample summary')
$md.Add('')
$md.Add("- **csv:** ``os.csv``")
$md.Add("- **rows:** $($rows.Count)")
$md.Add('')

function Add-PhaseSection {
    param($Name, $S)
    $md.Add("## $Name")
    $md.Add('')
    if ($null -eq $S) {
        $md.Add('_no rows_')
        $md.Add('')
        return
    }
    $md.Add("| metric | mean | max | min | last |")
    $md.Add("| --- | ---: | ---: | ---: | ---: |")
    foreach ($pair in @(
        @('cpu_load_pct', $S.cpu),
        @('ram_used_gb', $S.ram_used_gb),
        @('ram_free_gb', $S.ram_free_gb),
        @('commit_pct', $S.commit_pct),
        @('proc_count_cursor', $S.cursor_count),
        @('proc_ws_mb_cursor_sum', $S.cursor_ws_mb),
        @('proc_count_node', $S.node_count),
        @('proc_ws_mb_node_sum', $S.node_ws_mb),
        @('proc_count_agentish', $S.agent_count),
        @('proc_ws_mb_agentish_sum', $S.agent_ws_mb),
        @('proc_ws_mb_python_sum', $S.python_ws_mb),
        @('disk_c_free_gb', $S.disk_c_free_gb)
    )) {
        $m = $pair[1]
        $md.Add("| $($pair[0]) | $($m.mean) | $($m.max) | $($m.min) | $($m.last) |")
    }
    $md.Add('')
    $md.Add("- **samples:** $($S.n)")
    $md.Add('')
}

Add-PhaseSection 'baseline' $baseline
Add-PhaseSection 'hot' $hot

if ($baseline -and $hot) {
    $md.Add('## Delta (hot max - baseline mean)')
    $md.Add('')
    $md.Add('| metric | delta |')
    $md.Add('| --- | ---: |')
    $md.Add("| cpu_load_pct | $([math]::Round($hot.cpu.max - $baseline.cpu.mean, 2)) |")
    $md.Add("| ram_used_gb | $([math]::Round($hot.ram_used_gb.max - $baseline.ram_used_gb.mean, 2)) |")
    $md.Add("| commit_pct | $([math]::Round($hot.commit_pct.max - $baseline.commit_pct.mean, 2)) |")
    $md.Add("| proc_ws_mb_cursor_sum | $([math]::Round($hot.cursor_ws_mb.max - $baseline.cursor_ws_mb.mean, 2)) |")
    $md.Add("| proc_ws_mb_node_sum | $([math]::Round($hot.node_ws_mb.max - $baseline.node_ws_mb.mean, 2)) |")
    $md.Add("| proc_ws_mb_agentish_sum | $([math]::Round($hot.agent_ws_mb.max - $baseline.agent_ws_mb.mean, 2)) |")
    $md.Add('')
    $md.Add('CLI vs IDE: compare these deltas across arms. CLI with Cursor closed should show ~0 cursor_count in baseline/hot.')
    $md.Add('')
}

$outPath = Join-Path $RunDir 'os-summary.md'
[System.IO.File]::WriteAllLines($outPath, $md)
Write-Host "Wrote $outPath"
Get-Content $outPath
