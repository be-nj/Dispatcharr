# Development setup (be-nj fork)

This fork tracks [Dispatcharr/Dispatcharr](https://github.com/Dispatcharr/Dispatcharr)
and carries the features listed in the fork's issue tracker (OIDC login,
device-flow/Bearer API, per-user favorites, per-request stream profiles).

## Running the dev environment

```bash
cd docker
docker compose -f docker-compose.dev.yml up -d
```

- Web UI / API: http://localhost:9191
- Frontend dev server (hot reload): http://localhost:5656
- The repo is bind-mounted into the container (`../:/app`), so backend edits
  apply on reload; the frontend dev server picks up changes live. Note: the
  container chowns the checkout to uid 1000 (`dispatch`) on first start — if
  your host uid differs, re-chown the source files, but NEVER `docker/data`:
  it holds the container's Postgres data dir and must stay uid 1000, or
  Postgres fails with `could not open file "global/pg_filenode.map"`.
- First visit initializes the superuser (local/private networks only by
  default; see `DISPATCHARR_SETUP_ALLOWED_IP` in `docker-compose.dev.yml`).
- The optional `pgadmin` service may fail to start if host port 8082 is taken;
  it is not required for development.

## Syncing with upstream

```bash
git fetch upstream
git checkout main
git merge upstream/main   # or rebase fork branches onto upstream/main
git push origin main
```

`upstream` points at `https://github.com/Dispatcharr/Dispatcharr.git`.
Keep fork features on topic branches so they can be offered upstream as PRs.

Known sync pitfalls (seen on the v0.31.0 sync, 2026-10-06):

- **Migration number collisions.** The fork's seed migration lives in
  `core/migrations/` and upstream keeps adding numbered migrations there.
  After each merge run `python manage.py makemigrations --check --dry-run`
  in the dev container; if two leaf nodes exist, renumber the fork's
  migration and point its dependency at upstream's newest. The seed uses
  `get_or_create`, so re-applying it under a new name is a no-op.
- **`uv.lock` is fork-only.** Upstream pins versions in `pyproject.toml`
  but ships no lockfile; run `uv lock` after every merge. The Docker image
  takes its Python deps from upstream's `ghcr.io/dispatcharr/dispatcharr:base`.
- **Ownership.** The dev container chowns the bind-mounted checkout to uid
  1000 on every start. If git refuses to unlink files, re-chown everything
  except `docker/data` and `frontend/node_modules` (the container needs
  write access to the latter for Vite).
- **Entrypoint changes need a container recreate.** A uwsgi HUP re-reads
  `uwsgi.dev.ini`, which may reference env vars only the new entrypoint
  exports; use `docker compose ... up -d --force-recreate dispatcharr`.
- **Upstream's base-image workflow** needs Docker Hub secrets; it is guarded
  with `if: github.repository_owner == 'Dispatcharr'` in this fork.

Deploying PROD (diana, Komodo stack `dispatcharr`, `/etc/komodo/stacks/dispatcharr`):
push to `main`, wait for the "Build and Push Multi-Arch Docker Image" run,
then on diana `docker compose pull`, `docker compose stop -t 60`, tar `data/`
into `/home/data/backups/dispatcharr/`, `docker compose up -d`, and check
`/api/core/version/`, `/api/accounts/oidc/status/` and the startup log for
`Applying ...` lines.

## Fork features

- **OIDC SSO** for the web UI + Bearer auth for API clients: see the
  docstring in `apps/accounts/oidc.py` for all `OIDC_*` environment
  variables. The status endpoint exposes issuer + device client id for TV
  clients (device authorization grant).
- **Per-user favorites**: `/api/channels/favorites/` (+ `<id>/` toggle).
- **Named output profiles**: `?output_profile=audiofix|720p|raw` on the
  stream endpoint; seeded profiles live in
  `core/migrations/0029_seed_fork_output_profiles.py`.
