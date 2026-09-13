# Attribute Cursor usage CSV rows to a run manifest time window.
# From repo root:
#   .\experiments\composer-load-and-burn\usage\attribute.ps1 -Manifest <path> -Csv <path>

param(
    [Parameter(Mandatory = $true)]
    [string]$Manifest,

    [Parameter(Mandatory = $true)]
    [string]$Csv
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Manifest)) {
    Write-Error "Manifest not found: $Manifest"
}

if (-not (Test-Path -LiteralPath $Csv)) {
    Write-Error "CSV not found: $Csv"
}

function Parse-ManifestTimes {
    param([string]$Path)

    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $startMatch = [regex]::Match($text, '(?im)^-\s*\*\*start\s*\(Europe/Madrid\):\*\*\s*(.+)$')
    $endMatch = [regex]::Match($text, '(?im)^-\s*\*\*end\s*\(Europe/Madrid\):\*\*\s*(.+)$')

    if (-not $startMatch.Success) {
        Write-Error "Manifest missing start (Europe/Madrid) line: $Path"
    }

    $startText = $startMatch.Groups[1].Value.Trim()
    $startDt = [datetime]::ParseExact($startText, 'yyyy-MM-dd HH:mm:ss', [System.Globalization.CultureInfo]::InvariantCulture)

    $endDt = $null
    if ($endMatch.Success) {
        $endText = $endMatch.Groups[1].Value.Trim()
        if ($endText -notmatch 'yyyy-MM-dd') {
            $endDt = [datetime]::ParseExact($endText, 'yyyy-MM-dd HH:mm:ss', [System.Globalization.CultureInfo]::InvariantCulture)
        }
    }

    return [PSCustomObject]@{
        Start = $startDt
        End   = $endDt
        Text  = $text
    }
}

function Parse-ManifestGameIds {
    param([string]$Text)

    $ids = New-Object System.Collections.Generic.List[string]

    $singleMatch = [regex]::Match($Text, '(?im)^-\s*\*\*game_id:\*\*\s*(.+)$')
    if ($singleMatch.Success) {
        $id = $singleMatch.Groups[1].Value.Trim()
        if (-not [string]::IsNullOrWhiteSpace($id)) {
            $ids.Add($id)
        }
    }

    $tableMatches = [regex]::Matches($Text, '\|\s*\d+\s*\|\s*([^\|]+?)\s*\|')
    foreach ($m in $tableMatches) {
        $candidate = $m.Groups[1].Value.Trim()
        if ($candidate -match '^game-') {
            if (-not $ids.Contains($candidate)) {
                $ids.Add($candidate)
            }
        }
    }

    return @($ids)
}

function Find-ColumnIndex {
    param(
        [string[]]$Headers,
        [string[]]$Keywords,
        [switch]$Required
    )

    for ($i = 0; $i -lt $Headers.Count; $i++) {
        $normalized = $Headers[$i].ToLowerInvariant()
        foreach ($kw in $Keywords) {
            if ($normalized.Contains($kw)) {
                return $i
            }
        }
    }

    if ($Required) {
        return -1
    }
    return $null
}

function Find-TokenColumns {
    param([string[]]$Headers)

    $indices = New-Object System.Collections.Generic.List[int]
    $names = New-Object System.Collections.Generic.List[string]
    $keywords = @('token', 'input', 'output', 'cache')

    for ($i = 0; $i -lt $Headers.Count; $i++) {
        $normalized = $Headers[$i].ToLowerInvariant()
        foreach ($kw in $keywords) {
            if ($normalized.Contains($kw)) {
                $indices.Add($i)
                $names.Add($Headers[$i])
                break
            }
        }
    }

    return [PSCustomObject]@{
        Indices = @($indices)
        Names   = @($names)
    }
}

function Parse-CsvTimestamp {
    param(
        [string]$Value,
        [string]$HeaderName
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    $trimmed = $Value.Trim()
    $formats = @(
        'yyyy-MM-dd HH:mm:ss',
        'yyyy-MM-ddTHH:mm:ss',
        'yyyy-MM-ddTHH:mm:ssK',
        'yyyy-MM-ddTHH:mm:ss.fff',
        'yyyy-MM-ddTHH:mm:ss.fffK',
        'M/d/yyyy H:mm:ss',
        'M/d/yyyy h:mm:ss tt',
        'MM/dd/yyyy HH:mm:ss'
    )

    foreach ($fmt in $formats) {
        try {
            return [datetime]::ParseExact($trimmed, $fmt, [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::AllowWhiteSpaces)
        }
        catch {
            # try next format
        }
    }

    try {
        return [datetime]::Parse($trimmed, [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::AllowWhiteSpaces)
    }
    catch {
        throw "Could not parse timestamp '$trimmed' in column '$HeaderName'"
    }
}

function Parse-NumericCell {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return 0.0
    }

    $trimmed = $Value.Trim().Replace(',', '')
    $num = 0.0
    if ([double]::TryParse($trimmed, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$num)) {
        return $num
    }
    return 0.0
}

$manifestInfo = Parse-ManifestTimes -Path $Manifest
$gameIds = Parse-ManifestGameIds -Text $manifestInfo.Text

$csvLines = @(Get-Content -LiteralPath $Csv -Encoding UTF8)
if ($csvLines.Count -lt 1) {
    Write-Error "CSV is empty: $Csv"
}

$headerLine = $csvLines[0]
$headers = @($headerLine -split ',' | ForEach-Object { $_.Trim().Trim('"') })

$timeIdx = Find-ColumnIndex -Headers $headers -Keywords @('timestamp', 'time', 'date') -Required
if ($timeIdx -lt 0) {
    Write-Host "Could not map timestamp column. CSV headers:"
    Write-Host $headerLine
    exit 1
}

$tokenCols = Find-TokenColumns -Headers $headers
if ($tokenCols.Indices.Count -eq 0) {
    Write-Host "Could not map token-like columns. CSV headers:"
    Write-Host $headerLine
    exit 1
}

$timeHeader = $headers[$timeIdx]
$rowsInWindow = 0
$columnSums = @{}
foreach ($name in $tokenCols.Names) {
    $columnSums[$name] = 0.0
}

$endInclusive = if ($null -ne $manifestInfo.End) { $manifestInfo.End } else { [datetime]::MaxValue }

for ($lineNum = 1; $lineNum -lt $csvLines.Count; $lineNum++) {
    $line = $csvLines[$lineNum]
    if ([string]::IsNullOrWhiteSpace($line)) {
        continue
    }

    $fields = @($line -split ',' | ForEach-Object { $_.Trim().Trim('"') })
    if ($fields.Count -le $timeIdx) {
        continue
    }

    try {
        $rowTime = Parse-CsvTimestamp -Value $fields[$timeIdx] -HeaderName $timeHeader
    }
    catch {
        continue
    }

    if ($rowTime -lt $manifestInfo.Start) {
        continue
    }
    if ($rowTime -gt $endInclusive) {
        continue
    }

    $rowsInWindow++
    for ($j = 0; $j -lt $tokenCols.Indices.Count; $j++) {
        $idx = $tokenCols.Indices[$j]
        $colName = $tokenCols.Names[$j]
        if ($idx -lt $fields.Count) {
            $columnSums[$colName] += Parse-NumericCell -Value $fields[$idx]
        }
    }
}

$totalTokens = 0.0
foreach ($name in $tokenCols.Names) {
    $totalTokens += $columnSums[$name]
}

$manifestDir = Split-Path -Parent $Manifest
$outPath = Join-Path $manifestDir 'attributed.md'

$outLines = @(
    "# Usage attribution"
    ""
    "- **manifest:** $Manifest"
    "- **csv:** $Csv"
    "- **window start (Europe/Madrid):** $($manifestInfo.Start.ToString('yyyy-MM-dd HH:mm:ss'))"
)

if ($null -ne $manifestInfo.End) {
    $outLines += "- **window end (Europe/Madrid):** $($manifestInfo.End.ToString('yyyy-MM-dd HH:mm:ss'))"
}
else {
    $outLines += "- **window end (Europe/Madrid):** (not set in manifest - used open end)"
}

$outLines += "- **rows in window:** $rowsInWindow"
$outLines += "- **timestamp column:** $timeHeader"
$outLines += ""
$outLines += "## Token column sums"
$outLines += ""

foreach ($name in $tokenCols.Names) {
    $sum = $columnSums[$name]
    $outLines += "- **${name}:** $sum"
}

$outLines += ""
$outLines += "- **total (sum of mapped columns):** $totalTokens"
$outLines += ""

if ($gameIds.Count -gt 0) {
    $perGame = $totalTokens / $gameIds.Count
    $outLines += "## Per-game estimate"
    $outLines += ""
    $outLines += "- **game_ids in manifest:** $($gameIds.Count) ($($gameIds -join ', '))"
    $outLines += "- **per-game estimate (labeled):** $perGame (= window total / game count)"
    $outLines += ""
    $outLines += "If the CSV cannot split lead vs player rows (IDE arm), treat per-game as a labeled estimate only."
}
else {
    $outLines += "## Per-game estimate"
    $outLines += ""
    $outLines += "No game_ids found in manifest - per-game estimate not computed."
}

Set-Content -LiteralPath $outPath -Value ($outLines -join "`n") -Encoding UTF8

Write-Host "Wrote $outPath"
Write-Host "  rows in window: $rowsInWindow"
Write-Host "  total tokens:   $totalTokens"
