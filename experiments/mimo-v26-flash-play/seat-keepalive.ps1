$ErrorActionPreference = 'Continue'
$RunDir = 'C:\Users\jordi\Desktop\CODING~1\CHESS-~1\EXPERI~1\MIMO-V~1'
$Repo = 'C:\Users\jordi\Desktop\CODING~1\CHESS-~1'
$Oc = 'C:\Users\jordi\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe'
$Sid = Get-Content (Join-Path $RunDir 'session-id.txt') -ErrorAction SilentlyContinue
$Stop = Join-Path $RunDir 'stop.flag'
$Log = Join-Path $RunDir 'keepalive.log'
function L($m){ $line = '{0} {1}' -f (Get-Date -Format o), $m; Add-Content $Log $line; Write-Output $line }
L 'keepalive start'
while (-not (Test-Path $Stop)) {
  if (-not $Sid) { L 'no session id'; Start-Sleep 60; continue }
  $stamp = Get-Date -Format HHmmss
  $out = Join-Path $RunDir ("ka-$stamp.out.txt")
  $err = Join-Path $RunDir ("ka-$stamp.err.txt")
  try {
    $p = Start-Process -FilePath $Oc -ArgumentList @('run','--dir',$Repo,'-s',$Sid,'-m','opencode/mimo-v2.6-flash-free','--variant','max','--auto', 'CONTINUE. Fetch board with your Bearer key. If your turn POST one UCI move now. If waiting, recheck. If game over, POST a new AvE game vs stockfish-handicap:noise55 as white and keep playing. No essays. MOVE.') -WorkingDirectory $Repo -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden
    L ("poke sid=$Sid pid=$($p.Id)")
  } catch { L ("poke fail $($_.Exception.Message)") }
  $left = 900
  while ($left -gt 0 -and -not (Test-Path $Stop)) { Start-Sleep 30; $left -= 30 }
}
L 'keepalive exit'
