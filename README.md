# Go4Ride Backend

FastAPI backend for a ride-hailing app.

**Live API:** https://go4ride-api.onrender.com  
Docs: https://go4ride-api.onrender.com/docs · Health: https://go4ride-api.onrender.com/health

## What it does

- **Riders** — OTP login, profile, fare quotes, book/cancel rides, ride history, saved addresses, wallet/promos, live updates over WebSocket
- **Drivers** — OTP login, go online/offline, search and accept rides, KYC onboarding (documents + vehicle upload to S3)
- **Admin** — Review and approve/reject driver applications (`X-Admin-Key`)

In development, rides can auto-assign and advance through statuses via a mock driver (`MOCK_DRIVER_ENABLED=true`).

## Stack

FastAPI · PostgreSQL · Redis · SQLAlchemy (async) · Alembic · JWT/OTP · AWS S3 · Docker

## Run locally

Requires Python 3.11+ and Docker (Postgres + Redis).

```bash
chmod +x scripts/dev.sh
./scripts/dev.sh setup
./scripts/dev.sh run
```

API: http://localhost:8000  
Docs: http://localhost:8000/docs

Copy `.env.example` to `.env` before setup. Use the project `.venv` (not a system/conda Python 3.8 env).

## Docs

| | |
|---|---|
| [API reference](docs/API.md) | Endpoints with request/response examples |
| [Endpoint tables](docs/API_endpoints.md) | Quick lookup by area |
| [Deploy](docs/DEPLOY.md) | Render blueprint |
| [OpenAPI](docs/openapi.json) | Exported spec |

## Tests

```bash
pytest
```

## Layout

```
app/
  api/v1/       rider, driver, admin, websocket routes
  services/     business logic
  models/       SQLAlchemy models
  core/         config, auth, redis
alembic/        migrations
tests/
docs/           API docs, deploy guide
```
