$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $Repo "python\src\chess_harness"))) {
  $Repo = "C:\Users\jordi\Desktop\coding stuff\chess-vision-harness"
}
Set-Location $Repo
Write-Host "Repo: $Repo"
Write-Host "Stopping listeners on :8765..."
Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object {
    Write-Host "  Stop-Process $_"
    Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
  }
Start-Sleep -Seconds 2

$startup = Join-Path $Repo ".chess_harness\logs\start-harness-startup.cmd"
$env:PYTHONPATH = (Resolve-Path (Join-Path $Repo "python\src")).Path

if (Test-Path $startup) {
  Write-Host "Starting via $startup"
  Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$startup`"" -WorkingDirectory $Repo -WindowStyle Hidden
} else {
  Write-Host "Starting python -m chess_harness serve --force"
  Start-Process -FilePath "python" -ArgumentList "-m","chess_harness","serve","--force" -WorkingDirectory $Repo -WindowStyle Hidden
}

$ok = $false
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Seconds 1
  try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -TimeoutSec 2
    Write-Host ("health ok: " + ($h | ConvertTo-Json -Compress))
    $ok = $true
    break
  } catch {}
}
if (-not $ok) { Write-Error "health did not come up"; exit 1 }

try {
  $pt = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/ops/prompt-test?family=jeff" -TimeoutSec 10
  $packIds = @()
  if ($pt.packs) {
    if ($pt.packs -is [System.Array]) { $packIds = @($pt.packs | ForEach-Object { $_.id }) }
    else { $packIds = @($pt.packs.PSObject.Properties.Name) }
  }
  Write-Host ("prompt-test?family=jeff packs: " + ($packIds -join ", "))
} catch {
  Write-Warning "prompt-test?family=jeff failed: $_"
}
Write-Host "Restart complete."
