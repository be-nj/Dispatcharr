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
