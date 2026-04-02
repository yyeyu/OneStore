# OneStore

OneStore platform core. This repository contains the shared system foundation
for the next product modules, not the full customer-facing automation stack.

## What The Platform Core Includes

- FastAPI app with `/health` and `/version`
- Typer CLI for system checks, account/module operations, jobs, actions, and smoke checks
- PostgreSQL + SQLAlchemy 2 + Alembic foundation
- Core tables:
  - `avito_accounts`
  - `modules`
  - `module_account_settings`
  - `module_runs`
  - `action_logs`
- Module 2 inbox tables:
  - `avito_chats`
  - `avito_messages`
  - `avito_clients`
  - `avito_listings_ref`
- Account and module enablement management
- Shared job runtime and scheduler bootstrap
- Shared action audit logging
- Compact smoke-check flow

Temporary probe job/action utilities are kept only to validate the platform
runtime. They are scaffold checks, not product business logic.

## Default Module Catalog

- `system_core`
- `module2_inbox`

## Database Schema Summary

1. `avito_accounts`
   - `id` INTEGER PK
   - `name`, `client_id` (UNIQUE), `client_secret`, `avito_user_id` (UNIQUE, nullable)
   - `is_active`, `last_inbox_sync_at`, `last_inbox_sync_status`, `last_inbox_error`
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
6. `avito_chats`
   - `id` INTEGER PK
   - `account_id`, `external_chat_id`, `chat_type`
   - `client_id`, `listing_id`, external timestamps and last-message summary fields
7. `avito_messages`
   - `id` INTEGER PK
   - `account_id`, `chat_id`, `external_message_id`
   - `direction`, `message_type`, `text`, `content_json`, `quote_json`
8. `avito_clients`
   - `id` INTEGER PK
   - `account_id`, `external_user_id`, profile snapshot fields
9. `avito_listings_ref`
   - `id` INTEGER PK
   - `account_id`, `external_item_id`, lightweight listing snapshot fields

## Official Runtime Contour

- Python: `3.13`
- PostgreSQL host port: `5433`
- Local DB DSN:
  `postgresql+psycopg://postgres:postgres@127.0.0.1:5433/onestore`

## Quick Start

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

### 6. Create account and enable the core module

```powershell
python -m app.main create-account "Local Dev Account" "local-dev-client" "local-dev-secret" --avito-user-id "shop-user-1"
python -m app.main set-module 1 system_core --enabled
python -m app.main list-module-settings --account-id 1
```

### 7. Run temporary runtime probes

```powershell
python -m app.main run-job system-probe
python -m app.main run-job account-system-probe --account-id 1
python -m app.main run-probe-action smoke-target "hello"
```

### 8. Run smoke check

```powershell
python -m app.main smoke-check
```

## Useful CLI Commands

```powershell
python -m app.main check-system
python -m app.main check-db
python -m app.main create-account "Shop A" "shop-a-client" "shop-a-secret" --avito-user-id "shop-a-user"
python -m app.main list-accounts
python -m app.main create-module module2_inbox
python -m app.main list-modules
python -m app.main ensure-default-modules
python -m app.main set-module 1 system_core --enabled
python -m app.main list-module-settings --account-id 1
python -m app.main bootstrap-local
python -m app.main run-system-probe
python -m app.main run-job account-system-probe --account-id 1
python -m app.main run-scheduler --interval-seconds 1 --duration-seconds 3
python -m app.main run-probe-action test-target "hello"
python -m app.main smoke-check
python -m app.main serve --reload
```

## API

Then open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/version`

## Tests

```powershell
python -m pytest -q -m "not integration"
python -m pytest -q
python -m pytest -q -m integration
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
