# Deploy folder

Operator **entry doc is in the repo root:** [`../DEPLOY.md`](../DEPLOY.md).

This directory holds templates and detailed runbooks:

| File | Contents |
|------|----------|
| [`home-pc.md`](home-pc.md) | Windows PC + Cloudflare Tunnel + Pages live path |
| [`pages.md`](pages.md) | Pages CI secrets, `GAME_ORIGIN`, local Functions preview |
| [`Caddyfile`](Caddyfile) | Caddy reverse-proxy example |
| [`nginx.conf.example`](nginx.conf.example) | nginx example |
| [`chess-harness.service`](chess-harness.service) | systemd unit |
| [`games_disk_usage.sh`](games_disk_usage.sh) | Disk usage helper |
| [`sync-game-origin.py`](sync-game-origin.py) | CI helper — sync Pages `GAME_ORIGIN` from GitHub secret |
