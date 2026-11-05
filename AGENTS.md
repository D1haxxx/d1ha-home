# AGENTS.md - deploy target for this repository (FamLab `phil-apps`)

Copy this file to the root of a project repository. `CLAUDE.md` imports it for Claude Code; Codex reads it directly.
Owner of the project: Phil. Talk to him in Russian, keep explanations short, and show exact steps.

## Where this project runs

- **Coolify 4.6.0** (self-hosted) on a dedicated Hetzner VM: Ubuntu 24.04, Docker 29.8.2, **2 vCPU / 4 GB RAM / 40 GB disk, x86_64**. Images are **built on the same 4 GB machine**: keep builds lean (multi-stage Dockerfile, small base images, no huge dependency trees). With 40 GB of disk, also keep images and build caches small.
- Source: a GitHub repository, **which may be public: treat it as public** and never commit secrets. A public repository is cloned by Coolify over HTTPS without credentials; a private one through a read-only deploy key. Deploys are **manual**: Phil clicks Deploy/Redeploy in Coolify. There are no webhooks and no CI deploys.
- Public URL: **`https://d1ha.com`**, **`https://www.d1ha.com`** or **`https://<name>.d1ha.com`** (the domain `d1ha.com` is Phil's, DNS is managed by his dad; there is no e-mail on this domain) through the Coolify proxy (Traefik) with automatic Let's Encrypt certificates. **IPv4 only.**
- The Coolify dashboard is private (SSH tunnel only). **You, the agent, have no access to the server, the dashboard or the Coolify API, and must not try to get it.** When something must change in Coolify, tell Phil exactly which screen and field to change.

## Contract the app must follow

1. Listen on **`0.0.0.0:<PORT>`**, one HTTP port. Phil puts the same number into Coolify **"Ports Exposes"**. Never add host port mappings (`ports:`), Coolify routes by domain.
2. Provide a cheap **health endpoint** that returns 200 when the app works, e.g. `GET /healthz`, and checks the DB connection if there is one. Phil enables it in Coolify Healthcheck.
3. All configuration comes from **environment variables**. Keep a committed **`.env.example`** with names and empty or dummy values. **The repository may be public, so everything committed, including history, may be visible to everyone forever.** Never commit secrets, `.env`, keys, tokens, or personal data (real names, emails, phone numbers, classmates' school work, database dumps, logs). If a secret was committed, tell Phil immediately: it must be rotated; deleting the file or rewriting history is not enough.
4. Log to **stdout/stderr**.
5. **State:** the container filesystem is wiped on every redeploy. Persistent files go to a Coolify **volume mount** (e.g. `/data`, configured by Phil under Storages). Data goes to the database.
6. **Database:** use a **Coolify-managed PostgreSQL** resource (17.x), not a database service inside this repo's docker-compose: Coolify does not back up compose volumes. Connect via `DATABASE_URL`, set to the DB's *internal* URL. The DB must never be "publicly available". Schema migrations must be **idempotent** and run at startup or as a pre-deploy step. Remind Phil to enable the DB's daily backup to S3 storage `hetzner-hel1-backups`.
7. Pin versions: base images by exact tag (digest preferred), dependencies by lockfile. No `latest`.
8. Run as a non-root user in the container where practical. Keep memory use modest (well under 1 GB per app).

Preferred build pack: **Dockerfile**. Nixpacks or Static are fine for simple projects. Use Docker Compose only when really needed, and then without host ports and without stateful services.

Reference implementation of this contract: the Python + PostgreSQL example `py-pg-starter` (FastAPI, `/healthz`, `/data`, ordered migrations, digest-pinned images). It comes in Phil's hand-over package as `example/py-pg-starter/`; if it is not in this repository and you need it, ask Phil to copy it in. Its `compose.yaml` is for local runs only: on the server the database is a separate Coolify PostgreSQL resource.

## Do not

- Connect to the server or the Coolify API, add deploy workflows/CI that push to the server, or ask Phil for server, SSH or Coolify credentials.
- Store secrets in the repo, in Dockerfiles, in build args or in logs; commit data dumps, uploads or anything with personal data (the repo may be public).
- Make databases public, add `ports:` host mappings, or use `network_mode: host` / privileged containers.
- Tell Phil to change Coolify instance settings (Settings → Backup/Updates/Registration), the proxy, or the `localhost` server, or to change DNS of `d1ha.com`. Those belong to his dad.

## Checklist before Phil clicks Deploy

- [ ] `docker build .` succeeds locally (or the chosen build pack is clearly supported).
- [ ] The app starts with values from `.env.example` and listens on the documented port.
- [ ] The health endpoint returns 200.
- [ ] `git grep -nIE "(password|secret|token|api[_-]?key)\s*[:=]"` shows no real values; `.env` is gitignored; nothing personal or private is staged (treat the repo as public).
- [ ] Tell Phil: the port for "Ports Exposes", the health path, which env vars to set in Coolify (mark secrets), and whether a volume mount or database is needed.
- [ ] Database schema change? Tell Phil to run **Backup Now** on the database first. Rolling back the code does not roll back the schema.
