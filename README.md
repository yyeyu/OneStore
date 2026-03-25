# Avito AI Assistant

Module `0` is the platform core for the next development stages: PostgreSQL foundation, Alembic migrations, job runner, Action layer, account bootstrap, observability and smoke checks.

## What Module 0 includes

- FastAPI app with `/health` and `/version`
- Typer CLI for system, DB, jobs, actions and smoke checks
- PostgreSQL + SQLAlchemy 2 + Alembic foundation
- Technical tables only: `avito_accounts`, `module_account_settings`, `module_runs`, `action_logs`, `idempotency_keys`
- Shared `RunContext`, `JobRunner`, APScheduler bootstrap and cross-process job locking
- Shared Action layer with `dry_run` / `live`, audit log and idempotency
- Local operator bootstrap via `account_code`

## Official runtime contour

- Python: `3.13`
- PostgreSQL host port: `5433`
- Local DB DSN: `postgresql+psycopg://postgres:postgres@127.0.0.1:5433/avito_ai_assistant`
- Docker Compose DB DSN inside containers: `postgresql+psycopg://postgres:postgres@postgres:5433/avito_ai_assistant`
- Main human-facing account identifier: `account_code`

## Project layout

```text
app/
  actions/
  adapters/
  api/
  cli/
  core/
  db/
  jobs/
  modules/
tests/
```

## Prerequisites

- Python `3.13`
- Docker Desktop with `docker compose`

## Quick start

Recommended developer path: run the app locally and use Docker only for PostgreSQL.

### 1. Create a local virtual environment

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

Default `.env.example` already points to the official local PostgreSQL contour on `127.0.0.1:5433`.

### 3. Start PostgreSQL

```powershell
docker compose up -d postgres
docker compose ps
```

Expected result: `postgres` is `healthy` and published on `0.0.0.0:5433`.

### 4. Apply migrations

```powershell
alembic upgrade head
alembic current
```

Expected result: the database reaches revision `0002_module0_core_tables`.

### 5. Run basic checks

```powershell
python -m app.main check-system
python -m app.main check-db
```

Expected result:

- `check-system` returns `status: ok`
- `check-db` returns `status: ok` and the DSN on `127.0.0.1:5433`

### 6. Bootstrap one local account

```powershell
python -m app.main bootstrap-local --account-code local-dev --display-name "Local Dev Account"
python -m app.main list-module-settings --account-code local-dev
```

Expected result: account `local-dev` exists and module `module0` is enabled.

### 7. Run one job manually

```powershell
python -m app.main run-job account-ping --account-code local-dev
```

Expected result: job returns `status: success` and creates a row in `module_runs`.

### 8. Run the smoke check

```powershell
python -m app.main smoke-check
```

Expected result:

- `status: ok`
- `job_recorded: true`
- `action_dry_run_status: dry_run`
- `action_live_status: success`

## Start the API locally

```powershell
python -m app.main serve --reload
```

Then open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/version`

## Useful CLI commands

```powershell
python -m app.main check-system
python -m app.main check-db
python -m app.main create-account demo-shop "Demo Shop"
python -m app.main list-accounts
python -m app.main set-module demo-shop module0 --enabled
python -m app.main set-module demo-shop module0 --disabled
python -m app.main list-module-settings --account-code demo-shop
python -m app.main bootstrap-local --account-code local-dev
python -m app.main run-job ping
python -m app.main run-job account-ping --account-code local-dev
python -m app.main run-job ping --trigger-source retry
python -m app.main run-scheduler --interval-seconds 1 --duration-seconds 3
python -m app.main run-demo-action test-target "hello from demo action"
python -m app.main run-demo-action test-target "hello from demo action" --live
python -m app.main smoke-check
```

## Tests

```powershell
pytest
pytest -m integration
pytest -m "not integration"
```

Notes:

- `integration` tests require a reachable PostgreSQL database
- integration tests automatically apply `alembic upgrade head` once per session
- `unit` and `integration` are now separated by marker rather than repeated ad-hoc skip logic

## Optional Docker app startup

If you want to run the API itself in Docker too:

```powershell
docker compose up -d postgres
docker compose up --build app
```

API will be available at `http://127.0.0.1:8000`.

## Logs and diagnostics

The default log format is readable text. For structured logs:

```powershell
$env:AVITO_AI_LOG_FORMAT="json"
python -m app.main check-system
```

Stable investigation fields include:

- `run_id`
- `correlation_id`
- `module_name`
- `job_name`
- `account_id`
- `status`

## Handoff to Module 1

Module `0` is ready to accept the next development stage without reshaping the core:

- add new jobs through the existing registry and `JobRunner`
- add new outward effects through `ActionExecutor`
- reuse existing account bootstrap, module settings and logs

## Stage boundary

Module `0` still does not include:

- real Avito, Telegram or Google Sheets API calls
- product tables for items, chats, messages, cases or statuses
- Module 1 business logic
