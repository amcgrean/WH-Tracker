# Fly Deployment Runbook (Phase 4)

## Purpose of this branch
This Fly migration branch exists to validate WH-Tracker as a persistent containerized deployment target on Fly.io **without cutting over production traffic yet**.

- **Vercel remains the active legacy deployment path during Fly testing.**
- Do not remove or break `vercel.json` / `api/index.py` during this phase.
- Do not merge the PO app in this phase.

## What was validated locally in Phase 4
Validation was performed conservatively and without a real Fly deploy.

### Verified
- Gunicorn startup command used by Fly works locally:
  - `sh -c 'gunicorn run:app --bind 0.0.0.0:${PORT:-8080}'`
- App binds to `PORT` correctly (validated with `PORT=8092`).
- Root health endpoint responds:
  - `GET /healthz` → `{"ok": true, "service": "wh-tracker"}`
- Existing dispatch health endpoint responds:
  - `GET /dispatch/api/health` → `{"ok": true, ...}`

### Not fully verified locally
- **Docker image build** could not be validated in this environment because Docker is not installed (`docker: command not found`).
- Full DB-backed behavior against real Fly-managed Postgres / Supabase infra was not validated here.
- Real Fly machine lifecycle behaviors (cold start, machine replacement, region routing) require actual Fly environment testing.

## Required environment variables
Set these for Fly before first launch.

### Required secrets
- `DATABASE_URL` (Postgres URL)
- `SECRET_KEY` (strong secret, at least 32 chars)

### Recommended runtime config (starting values)
- `RUN_MIGRATIONS_ON_START=false`
- `REQUIRE_STRONG_SECRET_KEY=true`
- `DB_POOL_SIZE=5`
- `DB_MAX_OVERFLOW=5`
- `DB_POOL_TIMEOUT=30`
- `DB_POOL_RECYCLE=300`
- `DB_USE_NULL_POOL=false`
- `ENABLE_LEGACY_ERP_FALLBACK=false`
- `CLOUD_MODE=true`
- `PORT=8080` (already in `fly.toml`)

### Optional/conditional variables
- `UPLOAD_FOLDER=/data/uploads/credits` only if a Fly volume is mounted.
- SQL Server fallback vars (`SQLSERVER_*` or legacy `SQL_*`) only if fallback is intentionally enabled for troubleshooting.

## Fly secrets and config setup
Assumes `flyctl` is installed and authenticated.

### 1) Prepare app and config
```bash
# from repo root
flyctl apps create <fly-app-name>

# set app name in fly.toml
# app = "<fly-app-name>"
```

### 2) Set secrets
```bash
flyctl secrets set \
  DATABASE_URL="postgresql://..." \
  SECRET_KEY="<strong-random-secret-at-least-32-chars>" \
  --app <fly-app-name>
```

### 3) Set non-secret runtime values
Use `fly.toml` env section for stable non-secret defaults, or:
```bash
flyctl secrets set \
  RUN_MIGRATIONS_ON_START="false" \
  REQUIRE_STRONG_SECRET_KEY="true" \
  DB_POOL_SIZE="5" \
  DB_MAX_OVERFLOW="5" \
  DB_POOL_TIMEOUT="30" \
  DB_POOL_RECYCLE="300" \
  DB_USE_NULL_POOL="false" \
  ENABLE_LEGACY_ERP_FALLBACK="false" \
  CLOUD_MODE="true" \
  --app <fly-app-name>
```

## Manual launch and scale steps

### Initial launch (test)
```bash
flyctl deploy --app <fly-app-name> --remote-only
```

### Scale for one-machine testing
```bash
flyctl scale count 1 --app <fly-app-name>
flyctl scale show --app <fly-app-name>
```

### Scale for two-machine production redundancy
```bash
flyctl scale count 2 --app <fly-app-name>
flyctl scale show --app <fly-app-name>
```

> Keep `min_machines_running = 1` during early production to reduce cold-start risk.

## Migrations operating model
- Current recommended Fly behavior: `RUN_MIGRATIONS_ON_START=false`.
- Run migrations as a controlled one-off operation instead of allowing every machine startup to attempt migrations.

Example:
```bash
# run once before scaling out
flyctl ssh console --app <fly-app-name> -C "cd /app && flask db upgrade"
```

If this command style is inconvenient, use an equivalent one-off Fly machine/process pattern, but keep migrations single-run and explicit.

## Health verification after launch
```bash
flyctl status --app <fly-app-name>
flyctl logs --app <fly-app-name>
curl -fsS https://<fly-app-name>.fly.dev/healthz
curl -fsS https://<fly-app-name>.fly.dev/dispatch/api/health
```

## Upload storage on Fly (current phase guidance)
- Current upload path writes to local disk.
- Local disk is non-durable across machine replacement/redeploy and not shared across machines.

For Phase 4:
- **Acceptable temporarily for testing** with explicit risk acknowledgment.
- If uploads must persist before cutover, mount a Fly volume and point `UPLOAD_FOLDER` at that mount path.
- Longer-term recommendation (Phase 5+): move uploads to object storage and store URLs/metadata in DB.

## Supabase callback/auth URL considerations
If Supabase auth callbacks are enabled, add Fly hostnames before testing auth flows:
- `https://<fly-app-name>.fly.dev`
- Any custom domain used for Fly prod traffic

Keep legacy Vercel callback URLs configured until final cutover.

## Rollback / safety note
Until explicit cutover:
- **Vercel remains available as rollback path.**
- If Fly behavior degrades, route traffic back to Vercel immediately and investigate offline.

## Remaining risk register (Phase 4 status)

1. **Upload storage is non-durable on Fly local disk**
   - Status: **acceptable temporarily**
   - Plan: test with explicit risk; before cutover use Fly volume or object storage migration.

2. **Migrations could race in multi-machine startup**
   - Status: **solved now (operationally)**
   - Guardrail: `RUN_MIGRATIONS_ON_START=false`, run one-off migration command before scale-out.

3. **DB pooling defaults may be suboptimal**
   - Status: **acceptable temporarily**
   - Plan: start with `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`, monitor DB connections, then tune.

4. **`pyodbc` / SQL Server fallback runtime needs may be incomplete**
   - Status: **deferred with concrete plan**
   - Plan: keep `ENABLE_LEGACY_ERP_FALLBACK=false`. If ever enabled, add required ODBC runtime drivers and validate separately.

5. **Secret handling strictness in Fly**
   - Status: **solved now**
   - Guardrail: enforce strong key with `REQUIRE_STRONG_SECRET_KEY=true`; set secrets only via Fly secrets/env.

6. **Fly scale/warm-machine behavior**
   - Status: **acceptable temporarily**
   - Plan: keep `min_machines_running=1`; observe startup latency and logs before considering scale-to-zero tweaks.

## Operational checklist

### Pre-deploy
- [ ] Confirm Vercel remains live and unchanged.
- [ ] Confirm `fly.toml` app name and region are set for target app.
- [ ] Set `DATABASE_URL` and strong `SECRET_KEY` in Fly secrets.
- [ ] Set runtime guardrails (`RUN_MIGRATIONS_ON_START=false`, `REQUIRE_STRONG_SECRET_KEY=true`).
- [ ] Confirm initial DB pool values.
- [ ] Confirm callback/auth URLs include Fly host (if auth flow is used).

### Initial Fly launch
- [ ] Deploy with `flyctl deploy --remote-only`.
- [ ] Keep scale at 1 machine.
- [ ] Run migrations one time with explicit command.

### Post-deploy validation
- [ ] Check `flyctl status` and `flyctl logs` for healthy boot.
- [ ] Validate `GET /healthz` and `GET /dispatch/api/health`.
- [ ] Smoke-test critical read paths in UI/API.
- [ ] Confirm no unexpected SQL Server fallback usage.

### Production cutover readiness
- [ ] Decide and implement durable upload strategy (volume or object storage).
- [ ] Confirm stable DB pooling under representative load.
- [ ] Validate auth callbacks/domains for Fly production hostname(s).
- [ ] Validate two-machine operation and health checks.
- [ ] Keep explicit rollback plan to Vercel until confidence threshold is met.

## Exact manual command sequence (first Fly test deployment)
Use this sequence as the practical first deploy playbook:

```bash
# 1) create app once
flyctl apps create <fly-app-name>

# 2) ensure fly.toml app name matches
# edit fly.toml: app = "<fly-app-name>"

# 3) set required secrets
flyctl secrets set DATABASE_URL="postgresql://..." SECRET_KEY="<32+ char secret>" --app <fly-app-name>

# 4) set runtime guardrails and baseline pool config
flyctl secrets set RUN_MIGRATIONS_ON_START="false" REQUIRE_STRONG_SECRET_KEY="true" DB_POOL_SIZE="5" DB_MAX_OVERFLOW="5" DB_POOL_TIMEOUT="30" DB_POOL_RECYCLE="300" DB_USE_NULL_POOL="false" ENABLE_LEGACY_ERP_FALLBACK="false" CLOUD_MODE="true" --app <fly-app-name>

# 5) deploy first test machine
flyctl deploy --app <fly-app-name> --remote-only

# 6) keep scale at 1 while validating
flyctl scale count 1 --app <fly-app-name>

# 7) run migrations once (single controlled execution)
flyctl ssh console --app <fly-app-name> -C "cd /app && flask db upgrade"

# 8) validate service health
flyctl status --app <fly-app-name>
flyctl logs --app <fly-app-name>
curl -fsS https://<fly-app-name>.fly.dev/healthz
curl -fsS https://<fly-app-name>.fly.dev/dispatch/api/health

# 9) later, scale to redundancy after validation
flyctl scale count 2 --app <fly-app-name>
```
