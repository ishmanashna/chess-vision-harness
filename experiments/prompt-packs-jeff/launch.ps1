param(
  [string]$Config = "config\runner_slots_jeff_ab.json",
  [switch]$Once
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $Root "python\src\chess_harness"))) {
  $Root = "C:\Users\jordi\Desktop\coding stuff\chess-vision-harness"
}
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "python\src"
$cfg = Join-Path $Root $Config
if (-not (Test-Path $cfg)) { throw "Missing config: $cfg" }
Write-Host "Jeff A/B runner"
Write-Host "  config: $cfg"
Write-Host "  packs:  ja jb jc jd je ji j2 (family=jeff)"
Write-Host "  Ops:    /api/ops/prompt-test?family=jeff"
Write-Host "  Composer A/B unchanged (default Ops hides Jeff)."
$args = @("runner", "--config", $cfg)
if ($Once) { $args += "--once" }
python -m chess_harness @args
