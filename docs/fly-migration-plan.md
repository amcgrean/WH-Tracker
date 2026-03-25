# Fly.io Migration Plan (Phase 1 Audit)

## Scope and goal
Prepare the existing Flask-based WH-Tracker app to run as a persistent containerized web app on Fly.io, while keeping the current Vercel deployment path intact during transition.

## Current deployment/runtime audit

### App structure and likely deploy target
- Main Flask app factory: `app.create_app()` in `app/__init__.py`.
- Current local/dev entrypoint: `run.py` (creates app and runs Flask dev server).
- Current Vercel entrypoint(s): `api/index.py` and `vercel_index.py` (both expose `app = create_app()`).
- Blueprint composition indicates a single monolith web target (`main`, `dispatch`, `sales`) that should be the initial Fly deploy target.

### Dependencies/runtime
- Python/Flask stack via `requirements.txt`.
- `gunicorn` already present as dependency.
- Postgres SQLAlchemy runtime expected via `DATABASE_URL`; app fails fast if missing.
- Optional SQL Server fallback codepaths use `pyodbc` in service modules and are guarded to avoid hard failure when unavailable.

### Environment variable usage (high impact)
- Required: `DATABASE_URL`.
- Security-sensitive: `SECRET_KEY` currently has an insecure default except when `VERCEL` is set.
- Startup/migrations: `RUN_MIGRATIONS_ON_START` defaults to enabled outside Vercel.
- DB pooling toggles: `DB_USE_NULL_POOL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`.
- Upload path: `UPLOAD_FOLDER` default `uploads/credits`.
- Additional app/runtime toggles and integrations in services (ERP fallback, Samsara, email, etc.) remain env-driven.

### Vercel-specific assumptions
- Vercel routing in `vercel.json` points all traffic to `api/index.py`.
- Runtime includes `VERCEL` checks in startup:
  - pooled-DB warning behavior
  - migration default differences (`RUN_MIGRATIONS_ON_START` default false on Vercel).
- These are currently non-conflicting with a Fly path if preserved.

### Filesystem/file handling behavior
- Credit/RMA upload routes write directly to local disk under `UPLOAD_FOLDER`.
- Image retrieval uses `send_from_directory` from that local path.
- This is a risk on Fly because machine-local filesystem is ephemeral unless an explicit volume strategy is used.

### Static/template behavior
- Uses Flask `app/static` and template rendering; no external asset pipeline required.
- Fly deployment can serve static files directly via Flask/Gunicorn as-is.

### Serverless-to-persistent runtime considerations
- App startup currently may run DB migrations on process start.
- In persistent multi-instance environments, startup migrations can race across instances.
- Existing SQLAlchemy engine options already support pooled connections for non-serverless mode.

### Existing health-check behavior
- Dispatch blueprint has `/dispatch/api/health`.
- No app-level lightweight health endpoint at root-level currently dedicated for Fly checks.

## Risks and gap analysis for Fly
1. **Entrypoint ambiguity for production server**
   - Need explicit WSGI target (e.g., `run:app` or dedicated `wsgi.py`) and stable Gunicorn command.
2. **Secret handling hardening**
   - `SECRET_KEY` fallback is unsafe for production unless guarded by explicit production/fly checks.
3. **Runtime migrations**
   - Auto-migrations on every start can create operational risk on Fly with >1 machine.
4. **Ephemeral local uploads**
   - Credit image uploads currently assume persistent local disk.
   - Minimum-safe transition should document ephemerality and/or gate behavior clearly.
5. **Container base/deps**
   - `pyodbc` presence may require OS packages in Docker image even if optional at runtime.
   - Need conservative image strategy and verify app can boot without legacy SQL fallback.
6. **Health/readiness**
   - Fly benefits from dedicated health route and predictable startup behavior.
7. **Auth/callback URLs**
   - Any external auth callback/base-URL assumptions must be validated for new Fly domain before cutover.

## Proposed production entrypoint for Fly
Use Gunicorn serving the Flask app object instantiated from the current app factory.

Recommended baseline command:
- `gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 2 --threads 4 --timeout 120 run:app`

Rationale:
- `run.py` already exposes top-level `app = create_app()` suitable for WSGI import.
- Keeps changes minimal and backward-compatible.
- Uses Fly-provided `PORT` and explicit host bind.

## Phase-by-phase implementation plan

### Phase 2 (scaffolding)
- Add production `Dockerfile` with conservative Python base and Gunicorn `CMD`.
- Add `.dockerignore`.
- Add `fly.toml` with placeholders and health check defaults.
- Keep `vercel.json` + `api/index.py` untouched.
- Add `docs/fly-local-run.md` with local build/run commands.

### Phase 3 (runtime readiness)
- Add explicit lightweight app health route (e.g., `/healthz`).
- Make production `SECRET_KEY` requirement environment-driven beyond Vercel-only detection.
- Revisit migration behavior defaults for Fly (likely disable auto-migrate by default; document explicit migration run step).
- Add clear logging around startup mode and migration toggles.
- Document/guard upload persistence assumptions for Fly ephemeral disk.

### Phase 4 (local validation + docs)
- Build and run container locally.
- Verify startup command and `PORT` behavior.
- Write `docs/fly-deploy.md` with env vars, `fly secrets set`, launch steps, scaling, health checks, and rollback note (Vercel remains active).

### Phase 5 (optional PO merge prep)
- Add short integration plan only (no merge) unless tiny and low-risk.

## Recommended guardrails for next phases
- Keep all new Fly work isolated to `fly-main` branch.
- Preserve Vercel path until explicit cutover.
- Use env vars only; no secret literals.
- Prefer minimal reversible changes.
