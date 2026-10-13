# Chess harness wrapper — resolves binary without PATH mutation.
# Repo root: bin -> composer-load-and-burn -> experiments -> repo (three parents).

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$HarnessExe = Join-Path $env:APPDATA 'Python\Python313\Scripts\chess-harness.exe'

if (Test-Path -LiteralPath $HarnessExe) {
    & $HarnessExe @args
    exit $LASTEXITCODE
}

$PythonDir = Join-Path $RepoRoot 'python'
Push-Location -LiteralPath $PythonDir
try {
    python -m chess_harness @args
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $exitCode
