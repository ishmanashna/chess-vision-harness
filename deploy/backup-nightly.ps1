# Nightly Chess Vision Harness backup (Windows Task Scheduler helper)
#
# Edit $RepoRoot and $OutputDir, then register the task:
#   schtasks /Create /TN "ChessHarnessNightlyBackup" /XML "deploy\backup-task-scheduler.xml" /F
# Or run manually:
#   powershell -NoProfile -ExecutionPolicy Bypass -File deploy\backup-nightly.ps1

$ErrorActionPreference = "Stop"

$RepoRoot = "C:\Users\jordi\Desktop\coding stuff\chess-vision-harness"
$OutputDir = Join-Path $RepoRoot ".chess_harness\backups"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Python not found at $Python — activate the repo venv first."
}

& $Python (Join-Path $RepoRoot "scripts\backup_harness.py") `
    --output $OutputDir `
    --game-days 30 `
    --keep 14
