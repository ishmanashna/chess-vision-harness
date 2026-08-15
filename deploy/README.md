# Deploy folder

Operator **entry doc is in the repo root:** [`../DEPLOY.md`](../DEPLOY.md).

This directory holds templates and detailed runbooks:

| File | Contents |
|------|----------|
| [`home-pc.md`](home-pc.md) | Windows PC + Cloudflare Tunnel + Pages live path |
| [`pages.md`](pages.md) | Pages CI secrets, `GAME_ORIGIN`, local Functions preview |
| [`install-harness-nssm.ps1`](install-harness-nssm.ps1) | Windows NSSM service (needs admin) — best reboot durability |
| [`install-harness-logon-task.ps1`](install-harness-logon-task.ps1) | No-admin logon auto-start (Startup folder + HKCU Run) |
| [`go-online.ps1`](go-online.ps1) | One-shot: Quick Tunnel → `GAME_ORIGIN` → Pages deploy → verify |
| [`verify-online.ps1`](verify-online.ps1) | Three-probe Online vs Sleeping check (exit codes documented in script) |
| [`tools/`](tools/) | Vendored `nssm.exe` (win64) for the NSSM installer |
| [`Caddyfile`](Caddyfile) | Caddy reverse-proxy example |
| [`nginx.conf.example`](nginx.conf.example) | nginx example |
| [`chess-harness.service`](chess-harness.service) | systemd unit |
| [`games_disk_usage.sh`](games_disk_usage.sh) | Disk usage helper |
| [`sync-game-origin.py`](sync-game-origin.py) | CI helper — sync Pages `GAME_ORIGIN` from GitHub secret |
