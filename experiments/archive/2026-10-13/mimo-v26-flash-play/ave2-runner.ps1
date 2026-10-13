$ErrorActionPreference = 'Continue'
$Brief = Get-Content -LiteralPath 'C:\Users\jordi\Desktop\coding stuff\chess-vision-harness\experiments\mimo-v26-flash-play\ave2-brief.txt' -Raw
Set-Location 'C:\Users\jordi\Desktop\CODING~1\chess-vision-harness'
& 'C:\Users\jordi\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe' run --dir 'C:\Users\jordi\Desktop\CODING~1\chess-vision-harness' -m opencode/mimo-v2.6-flash-free --variant max --auto --title 'mimo-v26-flash-ave2-game-qacJr4CF9yn077FxGW8TWw' -- $Brief
