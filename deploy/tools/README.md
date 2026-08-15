# Deploy tools (local binaries)

`nssm.exe` (win64) is vendored here so `install-harness-nssm.ps1 -NssmPath` works without a global install.

Re-download if missing:

```powershell
Invoke-WebRequest https://nssm.cc/release/nssm-2.24.zip -OutFile $env:TEMP\nssm.zip
Expand-Archive $env:TEMP\nssm.zip $env:TEMP\nssm-extract -Force
Copy-Item (Get-ChildItem $env:TEMP\nssm-extract -Recurse -Filter nssm.exe | Where-Object FullName -match win64 | Select-Object -First 1).FullName .\nssm.exe
```
