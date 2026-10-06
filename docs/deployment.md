# Deployment

Target: a small VPS (≥4 vCPU / 8 GB is generous; the workload is far
smaller). Docker + Compose only — no orchestrator, no external database.

```
Internet
   │
   ▼
Caddy            TLS termination, auto-renewal, security headers
   │
   ▼
web container    uvicorn → FastAPI read-only (user `shorts`, non-root)
   │
   ▼
/data volume     SQLite ledger + raw snapshots + manifest (persistent)
```

## Steps

```bash
git clone <repo> && cd shorts-es
DOMAIN=shorts.example.com docker compose up -d
```

- Set `DOMAIN` (env or `.env`) — Caddy obtains the certificate
  automatically; the host's DNS must point at the VPS.
- Only 80/443 are published; uvicorn never faces the internet directly.
- First sync: `docker compose run --rm sync` (or wait for cron).

## Scheduled sync

Twice daily is a sane default (CNMV updates on trading days, exact time
unknown). Host cron:

```
23 6,18 * * *  cd /opt/shorts-es && docker compose run --rm sync
```

or inside a container: `docker compose run --rm sync` runs
`shorts-es sync` against the shared `/data` volume. Identical content
produces `NO_CHANGE` — no duplicate snapshot is stored.

## Backups

`scripts/backup.sh [dest]` copies the SQLite ledger, raw snapshots and
manifest — the observation history, which cannot be reconstructed
retroactively. Schedule it after sync.

## Security baseline

- Container runs as non-root `shorts`; read-only filesystem is compatible
  (only `/data` needs writes).
- Caddy strips `Server`, sets nosniff/frame-deny/referrer headers.
- No login, no cookies, no user data — the entire surface is read-only.
- Dependencies pinned via `uv.lock`; image rebuilt to pick up updates.

## Health

`GET /api/v1/health` → `{"status": "ok"|"empty", ...}`. The Docker
`HEALTHCHECK` uses it; Caddy could be extended with upstream health
checks if needed.
