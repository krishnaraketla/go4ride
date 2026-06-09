# Go4Ride Backend (Phase 0 + Phase 1 + Phase 2)

FastAPI backend for the **rider mobile app** only. Driver matching, driver APIs, and admin panel are planned for later phases and are not included in this codebase.

## Scope

| Phase | Included |
|-------|----------|
| **Phase 0** | FastAPI scaffold, Postgres, Redis, Alembic, JWT/OTP auth primitives, health check |
| **Phase 1** | Rider auth, profile, reverse geocode, fare estimate, ride booking (create/cancel/status/history), WebSocket ride updates |
| **Phase 1.5** | Mock driver lifecycle (auto-assign/advance in dev) for rider UI testing |
| **Phase 2** | Bookings filters, insights, repeat ride, saved addresses, settings, wallet/promo/referral/email verify, payment & invoice stubs |
| Phase 2 (driver) | Driver app — *not in this repo yet* |
| Phase 3 | Admin panel — *not in this repo yet* |

## Stack

- FastAPI + Uvicorn
- PostgreSQL 16 + SQLAlchemy async + Alembic
- Redis (pub/sub for WebSockets, OTP rate limits, idempotency)
- JWT + OTP (console / Twilio / MSG91)
- Maps: mock / Google / Mapbox

## Quick start

**Requires:** Python **3.11+**, Docker Desktop running (Postgres + Redis).

```bash
# If you use conda, leave the old env first (mlp is Python 3.8 and will fail)
conda deactivate

chmod +x scripts/dev.sh
./scripts/dev.sh setup    # venv, deps, docker, migrate, seed
./scripts/dev.sh run      # API on http://127.0.0.1:8000
```

Manual equivalent (always activate `.venv` before `alembic` / `uvicorn`):

```bash
docker compose up -d
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --port 8000
```

### Troubleshooting

| Error | Cause | Fix |
|-------|--------|-----|
| `Cannot connect to the Docker daemon` | Docker Desktop not running | Start Docker Desktop, wait until ready, then `docker compose up -d` |
| `command not found: alembic` | Wrong env (conda `mlp` or system Python without install) | `conda deactivate`, then `source .venv/bin/activate` and `pip install -e ".[dev]"` |
| `cannot import name 'Annotated' from 'typing'` | Python **3.8** (e.g. conda `mlp`) | Use project `.venv` built with Python 3.11+: `rm -rf .venv && python3 -m venv .venv` |
| `cannot import name 'async_sessionmaker'` | Old SQLAlchemy in conda env | Same as above — install deps inside `.venv` only |
| `role "go4ride" does not exist` | App hit **local** Postgres on 5432, not Docker | Use port **5433** in `DATABASE_URL` (see `.env.example`); run `docker compose up -d` |

- Interactive docs: http://localhost:8000/docs (Swagger UI)
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json (static copy: [docs/openapi.json](docs/openapi.json))
- API reference (Markdown): [docs/API.md](docs/API.md)
- Endpoint list (tables): [docs/API_endpoints.md](docs/API_endpoints.md)
- Deploy to Render (free tier): [docs/DEPLOY.md](docs/DEPLOY.md)
- Health: http://localhost:8000/health

## API documentation

Full endpoint reference with request/response examples: **[docs/API.md](docs/API.md)**  
Quick endpoint tables by area: **[docs/API_endpoints.md](docs/API_endpoints.md)**  
OpenAPI spec (Swagger): **[docs/openapi.json](docs/openapi.json)** — regenerate with `python scripts/export_openapi.py`

Quick list:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/request-otp` | Send OTP for a phone (handles both first-time sign-up and returning login) |
| POST | `/api/v1/auth/verify-otp` | Verify OTP → JWT tokens (creates rider account on first sign-in) |
| POST | `/api/v1/auth/refresh` | Refresh JWT pair |
| POST | `/api/v1/auth/logout` | Revoke refresh token |
| GET | `/api/v1/auth/me` | Current user |
| GET/PATCH | `/api/v1/profile` | Rider profile |
| GET | `/api/v1/stats` | Lifetime ride stats |
| GET | `/api/v1/insights` | Weekly/monthly analytics |
| CRUD | `/api/v1/addresses` | Saved addresses |
| GET/PATCH | `/api/v1/settings` | User preferences |
| GET | `/api/v1/wallet` | Ride credit balance |
| POST | `/api/v1/promo/apply` | Apply promo code |
| GET | `/api/v1/referral` | Referral code |
| POST | `/api/v1/email/*` | Email verification |
| CRUD | `/api/v1/payment-methods` | Saved cards (stub) |
| GET | `/api/v1/location/reverse-geocode` | Lat/lng → address |
| POST | `/api/v1/rides/quote` | All ride types with fare + ETA for route |
| POST | `/api/v1/rides` | Create ride |
| POST | `/api/v1/rides/{id}/cancel` | Cancel ride |
| GET | `/api/v1/rides/{id}` | Ride details |
| GET | `/api/v1/rides/{id}/status` | Current status |
| GET | `/api/v1/rides/history` | Paginated history (`?status=`) |
| POST | `/api/v1/rides/{id}/repeat` | Repeat-ride prefilled payload |
| GET | `/api/v1/rides/{id}/invoice` | Invoice/receipt stub |
| WS | `/api/v1/ws/rides/{id}?token=...` | Live status events |

## Ride status (Phase 1.5)

With `MOCK_DRIVER_ENABLED=true` (default when `APP_ENV=development`), booked rides auto-advance:

`requested` → `searching_driver` → `driver_assigned` → `driver_arrived` → `in_progress` → `completed`

Set `MOCK_DRIVER_ENABLED=false` for real driver flow (default in production blueprint). Drivers discover rides via `GET /api/v1/driver/rides/search?lat=&lng=&radius_km=5` while online.

| Env var | Default (dev) | Description |
|---------|---------------|-------------|
| `MOCK_DRIVER_ENABLED` | `true` (dev) / `false` (prod blueprint) | Auto-assign seeded mock driver when `true` |
| `MAPS_PROVIDER` | `mock` | Set `google` + `MAPS_API_KEY` for real routes and live ETA |
| `DRIVER_ETA_CACHE_TTL_SEC` | `30` | Cache Google ETA per ride |
| `DRIVER_LOCATION_PUBLISH_INTERVAL_SEC` | `10` | Min seconds between WS location_update events |
| `MOCK_DRIVER_AUTO_ADVANCE` | `true` | Step through arrived → in_progress → completed |
| `MOCK_DRIVER_ASSIGN_DELAY_SEC` | `2` | Delay before assign |
| `MOCK_DRIVER_STEP_DELAY_SEC` | `5` | Delay between auto-advance steps |
| `MOCK_DRIVER_ETA_MIN` | `5` | ETA shown on driver card |

Cancel is allowed through `driver_arrived`; blocked once `in_progress`.

`requested` → `searching_driver` → `driver_assigned` → `driver_arrived` → `in_progress` → `completed` | `cancelled`

## Auth flow (one-step OTP)

The rider app uses a single OTP request endpoint for both first-time sign-up
and returning login:

1. `POST /api/v1/auth/request-otp` with `{"phone": "+91…"}` — always succeeds for a valid phone. The response includes `is_new_user` so the client knows whether to show an onboarding step after verification.
2. `POST /api/v1/auth/verify-otp` with `{"phone", "code"}` (plus optional `name` and `referral_code`). If the phone has never signed in before, the rider account is created automatically; otherwise the user is logged in. The response includes the JWT pair and `is_new_user` so the client can route to onboarding vs. home.

`name` is optional everywhere — riders can fill it later via `PATCH /api/v1/profile`. There is no separate `/auth/register` or `/auth/login` endpoint.

## OTP in development

With `OTP_DEBUG=true`, the OTP is returned in `data.debug_otp` on the request-otp response and logged when `OTP_PROVIDER=console`.

All `/api/v1` JSON responses use `{ "success", "message", "data" }` — see [docs/API.md](docs/API.md#response-envelope).

## API demo

`scripts/demo.py` runs an end-to-end walkthrough: Docker + DB setup, auth (OTP + refresh), profile, insights, addresses, settings, wallet/promo/referral/email, payment methods, ride booking (idempotency + WebSocket lifecycle), bookings (history, repeat, invoice), stats, and logout.

### One command (recommended)

From the repo root (Docker Desktop running):

```bash
./scripts/dev.sh demo
```

This will:

1. `docker compose down` / `up -d`
2. `./scripts/dev.sh setup` (venv, migrate, seed)
3. Start the API on port 8000 if it is not already running (restarts it after Docker recycle)
4. Run the full HTTP + WebSocket demo against `http://localhost:8000`

Requires `OTP_DEBUG=true` in `.env` so login/register responses include `debug_otp`.

### Manual (API already running)

If you prefer to keep your own `uvicorn` process (e.g. `./scripts/dev.sh run` in another terminal):

```bash
./scripts/dev.sh run      # terminal 1
DEMO_SKIP_SETUP=1 DEMO_SKIP_SERVER=1 ./scripts/dev.sh demo   # terminal 2
```

### Demo options (environment variables)

| Variable | Effect |
|----------|--------|
| `DEMO_RESET_DB=1` | Wipe Postgres volume (`./scripts/dev.sh reset-db`) instead of `setup` |
| `DEMO_SKIP_SETUP=1` | Skip Docker and migrate/seed (DB and containers must already be ready) |
| `DEMO_SKIP_SERVER=1` | Do not start or restart uvicorn; API must already be on port 8000 |
| `DEMO_SKIP_CANCEL=1` | Skip the create-and-cancel REST demo step |

Examples:

```bash
DEMO_RESET_DB=1 ./scripts/dev.sh demo          # fresh DB + full demo
DEMO_SKIP_SETUP=1 DEMO_SKIP_SERVER=1 ./scripts/dev.sh demo   # API demo only
```

### Interactive demos (API must already be running)

Two optional UIs share state via `.demo_session.json` (tokens, `ride_id`, addresses). Start the API first:

```bash
./scripts/dev.sh run          # terminal 1
./scripts/dev.sh demo-menu    # terminal 2 — Typer numbered menu
./scripts/dev.sh demo-tui     # terminal 2 — Textual TUI (key bindings)
```

| Command | File | Usage |
|---------|------|--------|
| `demo-menu` | `scripts/demo_menu.py` | Menu: rides, profile, insights, wallet, bookings, … |
| `demo-tui` | `scripts/demo_tui.py` | Same steps via keyboard shortcuts |

Subcommands (non-interactive):

```bash
python scripts/demo_menu.py health
python scripts/demo_menu.py auth
python scripts/demo_menu.py insights
python scripts/demo_menu.py ws-listen
```

Requires `OTP_DEBUG=true` for Auth. Typical walkthrough: **2** Auth → **4** Estimate → **5** Create ride → **7** WS listen → **8** Cancel (or cancel from Swagger while WS is open).

### Notebook


## Tests

```bash
pytest
```

## Project layout

```
app/
  api/v1/     auth, location, rides, profile, ws
  core/       config, security, redis, deps
  db/         session, seed
  models/     user, ride
  schemas/
  services/   auth, ride, fare, geo, otp
alembic/
tests/
```
