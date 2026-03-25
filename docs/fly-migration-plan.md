# Fly.io Migration Plan (Phase 1 Audit)

## Scope and constraints
- Target branch: `fly-main`.
- Goal: make WH-Tracker deployable to Fly.io as a persistent containerized Flask app.
- Constraint: keep current Vercel deployment path intact during migration.
- Out of scope for now: production cutover and any broad PO app merge.

## Current runtime shape (audit findings)

### App structure and deployment target
- Main Flask app lives under `app/` and is assembled by `create_app()` in `app/__init__.py`.
- Current web entrypoints:
  - `api/index.py` for Vercel Python serverless runtime.
  - `run.py` exposes `app = create_app()` and can also launch via `app.run()` when executed directly.
- Vercel routing is currently explicit in `vercel.json`, sending all routes to `api/index.py`.
- Existing CI/CD is Vercel-only via `.github/workflows/deploy.yml` on push to `main`.

### Runtime/dependencies
- Python dependencies are pip/requirements based (`requirements.txt`).
- `gunicorn` is already present in dependencies.
- App uses Flask + Flask-SQLAlchemy + Flask-Migrate.
- Database URL must be present at import/startup time (`config.py` raises if `DATABASE_URL` is missing).

### Environment variable usage
- Core runtime settings are centralized in `app/runtime_settings.py` (DB URL normalization, pool options, feature toggles).
- Config currently defaults `SECRET_KEY` to a dev fallback, but only enforces strict secret presence when `VERCEL` is set.
- `RUN_MIGRATIONS_ON_START` defaults to true outside Vercel and false on Vercel.
- DB engine pooling defaults are serverless-aware (`DB_USE_NULL_POOL` auto-defaults on when `VERCEL=true`).

### Serverless-specific assumptions observed
- Vercel behavior checks are present in app startup (`create_app()`) and config validation (`config.py`).
- Runtime migration logic currently catches `SystemExit` to prevent serverless crash behavior.
- `api/index.py` is dedicated Vercel handler file and should remain for legacy path compatibility.

### File upload/static handling
- Credit/RMA uploads are written to local disk under `UPLOAD_FOLDER` (default `uploads/credits`).
- Upload flow writes files to disk and persists metadata in DB, then serves files from local directory via Flask route.
- Email sync service also writes attachments to local upload directory.
- Static assets are served from Flask `app/static`; templates from `app/templates`.

### Health/startup behavior
- Existing JSON health endpoint already exists at `GET /dispatch/api/health`.
- Startup currently includes optional migration execution (`upgrade()`) inside app creation.

## Candidate Fly production entrypoint
- Recommended production entrypoint for Fly: Gunicorn against Flask app object in `run.py`.
- Proposed command shape for next phase:
  - `gunicorn run:app --bind 0.0.0.0:${PORT:-8080}`
- Rationale:
  - `run.py` already exposes a module-level `app` object.
  - Avoids relying on Flask development server.
  - Keeps `api/index.py` untouched for Vercel.

## Risk areas for Fly persistent hosting
1. **Ephemeral local filesystem**
   - Current credit image and email attachment flow assumes local disk persistence.
   - On Fly, machine-local disk is ephemeral unless a volume is explicitly mounted.
   - Risk: uploaded files can disappear on redeploy/restart/scale-out.

2. **Startup migrations in multi-instance runtime**
   - Running Alembic migration on every app startup can race or add startup fragility when multiple machines/instances start.
   - Should be explicitly controlled by env for Fly (conservative default recommended).

3. **Database pooling defaults shift**
   - Current defaults are serverless-biased; Fly persistent workers should use tuned SQLAlchemy pooling settings.
   - Need explicit env recommendations to avoid connection exhaustion.

4. **SECRET_KEY policy in non-Vercel production**
   - Strict key enforcement currently tied to Vercel env flag.
   - Fly production should also require explicit `SECRET_KEY` (or at least document/enforce via env policy).

5. **Legacy SQL Server fallback dependency**
   - Optional `pyodbc` paths exist and may require OS-level ODBC drivers in container if fallback is ever enabled.
   - Should remain disabled by default, with clear docs.

6. **Health checks**
   - Existing health endpoint is nested under dispatch path; Fly checks may prefer a simple root-level health endpoint in later phase (optional if current route is used).

## Phase-by-phase implementation plan

### Phase 2 (scaffolding)
- Add Dockerfile with conservative production defaults (Python slim base, requirements install, non-root runtime if practical).
- Add `.dockerignore`.
- Add `fly.toml` with placeholders and safe defaults:
  - internal port `8080`
  - process command using Gunicorn and `PORT`
  - HTTP service checks mapped to chosen health endpoint.
- Preserve `vercel.json`, `api/index.py`, and Vercel workflow unchanged.
- Add short local container run doc.

### Phase 3 (runtime hardening)
- Minimal, targeted runtime updates only:
  - ensure startup behavior is suitable for persistent workers;
  - tighten production secret/env expectations;
  - validate DB pooling defaults for Fly;
  - add/confirm health endpoint path for Fly checks;
  - document upload storage limitations and safest interim behavior.

#### Phase 3 implementation notes (completed)
- Fly runtime now defaults `RUN_MIGRATIONS_ON_START` to `false`; Vercel remains `false`; non-Fly/non-Vercel remains `true` for backward compatibility.
- Fly runtime now defaults to requiring a strong `SECRET_KEY` (minimum 32 chars) via env-controlled `REQUIRE_STRONG_SECRET_KEY`.
- Added lightweight root health endpoint (`/healthz`) for Fly checks while preserving existing `/dispatch/api/health`.
- Upload folder is created on startup, and Fly runtime logs a warning that local-disk uploads are non-durable without a mounted volume.
- Fly baseline config now keeps at least one machine warm (`min_machines_running = 1`) to avoid scale-to-zero cold starts.

### Phase 4 (local validation + docs)
- Build container locally and run with env placeholders.
- Validate startup command and `PORT` binding behavior.
- Add `docs/fly-deploy.md` with manual steps, env vars, Fly secrets, scaling, callback URL notes, and rollback guidance (Vercel remains active).

### Phase 5 (optional PO app prep)
- Document low-risk integration approach only (no merge unless trivial and clearly safe).

## Assumptions to confirm before Fly cutover
- Desired Fly app name and primary region.
- Whether to use Fly volume for `uploads/credits` as temporary compatibility layer vs. moving uploads to object storage.
- Whether runtime migrations should be disabled in app start and run via one-off Fly release command instead.
- Expected machine count at launch (1 vs 2+) and resulting DB pool sizing strategy.
