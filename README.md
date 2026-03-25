# Avito AI Assistant

Module `0` is a minimal platform core with a simplified database schema and
runtime flow.

## What Module 0 includes

- FastAPI app with `/health` and `/version`
- Typer CLI for system checks, account/module ops, jobs, actions, smoke checks
- PostgreSQL + SQLAlchemy 2 + Alembic foundation
- Core tables:
  - `avito_accounts`
  - `modules`
  - `module_account_settings`
  - `module_runs`
  - `action_logs`

## Database schema summary

1. `avito_accounts`
   - `id` INTEGER PK
   - `name`, `client_id` (UNIQUE), `client_secret`, `is_active`
   - `created_at`, `updated_at`
2. `modules`
   - `id` INTEGER PK
   - `name` UNIQUE
3. `module_account_settings`
   - composite PK: `(account_id, module_id)`
   - `is_enabled`, `created_at`, `updated_at`
4. `module_runs`
   - `id` INTEGER PK
   - `account_id` (nullable), `module_id`, `job_name`, `trigger_source`
   - `status` (`running`/`success`/`error`), `error_message`
   - `started_at`, `finished_at`
5. `action_logs`
   - `id` INTEGER PK
   - `account_id` (nullable), `run_id` (nullable)
   - `action_name`, `status` (`success`/`error`), `error_message`, `created_at`

## Official runtime contour

- Python: `3.13`
- PostgreSQL host port: `5433`
- Local DB DSN:
  `postgresql+psycopg://postgres:postgres@127.0.0.1:5433/avito_ai_assistant`

## Quick start

### 1. Create local virtual environment

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### 2. Create `.env` from `.env.example`

```powershell
Copy-Item .env.example .env
```

### 3. Start PostgreSQL

```powershell
docker compose up -d postgres
docker compose ps
```

### 4. Apply migrations

```powershell
alembic upgrade head
alembic current
```

### 5. Seed module catalog

```powershell
python -m app.main ensure-default-modules
python -m app.main list-modules
```

### 6. Create account and enable module

```powershell
python -m app.main create-account "Local Dev Account" "local-dev-client" "local-dev-secret"
python -m app.main set-module 1 module0 --enabled
python -m app.main list-module-settings --account-id 1
```

### 7. Run job and action

```powershell
python -m app.main run-job account-ping --account-id 1
python -m app.main run-demo-action smoke-target "hello"
```

### 8. Run smoke check

```powershell
python -m app.main smoke-check
```

## Useful CLI commands

```powershell
python -m app.main check-system
python -m app.main check-db
python -m app.main create-account "Shop A" "shop-a-client" "shop-a-secret"
python -m app.main list-accounts
python -m app.main create-module module0
python -m app.main list-modules
python -m app.main ensure-default-modules
python -m app.main set-module 1 module0 --enabled
python -m app.main list-module-settings --account-id 1
python -m app.main bootstrap-local
python -m app.main run-job ping
python -m app.main run-job account-ping --account-id 1
python -m app.main run-scheduler --interval-seconds 1 --duration-seconds 3
python -m app.main run-demo-action test-target "hello"
python -m app.main smoke-check
```

## API

```powershell
python -m app.main serve --reload
```

Then open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/version`

## Tests

```powershell
pytest
pytest -m integration
pytest -m "not integration"
```

Notes:

- integration tests require reachable PostgreSQL
- integration tests apply `alembic upgrade head` once per session

## Logging

Stable investigation fields:

- `run_id`
- `module_id`
- `module_name`
- `job_name`
- `action_name`
- `account_id`
- `status`
- `trigger_source`
