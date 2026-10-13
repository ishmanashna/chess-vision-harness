$ErrorActionPreference = 'Continue'
$Brief = Get-Content -LiteralPath 'C:\Users\jordi\Desktop\CODING~1\CHESS-~1\EXPERI~1\MIMO-V~1\seat1-brief.txt' -Raw
Set-Location -LiteralPath 'C:\Users\jordi\Desktop\CODING~1\CHESS-~1'
& 'C:\Users\jordi\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe' run --dir 'C:\Users\jordi\Desktop\CODING~1\CHESS-~1' -m opencode/mimo-v2.6-flash-free --variant max --auto --title 'mimo-v26-flash-game-efPMZmzgOVnuYBmVUNZmaQ' -- $Brief
exit $LASTEXITCODE
