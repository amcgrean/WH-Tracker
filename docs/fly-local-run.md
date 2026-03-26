# Fly Phase 2: local container run

This document covers local validation of the Phase 2 Fly container scaffolding without deploying.

## 1) Build the image

```bash
docker build -t wh-tracker:fly-phase2 .
```

## 2) Run locally

At minimum, provide runtime secrets and database connection via environment variables.

Required at a high level:
- `DATABASE_URL` (Postgres connection string used by Flask/SQLAlchemy)
- `SECRET_KEY` (Flask session secret)

Optional but commonly useful during local container testing:
- `RUN_MIGRATIONS_ON_START=false` (recommended on Fly; run migrations separately as a one-off task)
- `REQUIRE_STRONG_SECRET_KEY=true` (default behavior on Fly runtime; keeps weak fallback keys from being used)
- `PORT=8080` (defaults to 8080 in this container)

Example:

```bash
docker run --rm -p 8080:8080 \
  -e PORT=8080 \
  -e DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DBNAME' \
  -e SECRET_KEY='replace-with-a-real-secret-at-least-32-characters' \
  -e RUN_MIGRATIONS_ON_START=false \
  wh-tracker:fly-phase2
```

## 3) Confirm the app is listening on the expected port

In another terminal:

```bash
curl -fsS http://localhost:8080/dispatch/api/health
```

You should receive JSON with `"ok": true`.

## Notes / limitations

- Uploads default to local filesystem (`uploads/credits`) and are not durable across container rebuild/restart.
- On Fly runtime, startup migrations default to **off** unless `RUN_MIGRATIONS_ON_START=true` is explicitly set.
- On Fly runtime, strong `SECRET_KEY` enforcement is enabled by default (`REQUIRE_STRONG_SECRET_KEY=true` behavior).
- DB pooling remains environment-driven; for Fly start with `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`, and tune after observing real connection usage.
- This guide is for local validation only; no Fly deployment is performed in Phase 2.
