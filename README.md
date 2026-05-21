# Go4Ride Backend (Phase 0 + Phase 1)

FastAPI backend for the **rider mobile app** only. Driver matching, driver APIs, and admin panel are planned for later phases and are not included in this codebase.

## Scope

| Phase | Included |
|-------|----------|
| **Phase 0** | FastAPI scaffold, Postgres, Redis, Alembic, JWT/OTP auth primitives, health check |
| **Phase 1** | Rider auth, profile, reverse geocode, fare estimate, ride booking (create/cancel/status/history), WebSocket ride updates |
| Phase 2 | Driver app — *not in this repo yet* |
| Phase 3 | Admin panel — *not in this repo yet* |

## Stack

- FastAPI + Uvicorn
- PostgreSQL 16 + SQLAlchemy async + Alembic
- Redis (pub/sub for WebSockets, OTP rate limits, idempotency)
- JWT + OTP (console / Twilio / MSG91)
- Maps: mock / Google / Mapbox

## Quick start

```bash
docker compose up -d
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --port 8000
```

- Interactive docs: http://localhost:8000/docs
- API reference (Markdown): [docs/API.md](docs/API.md)
- Endpoint list (tables): [docs/API_endpoints.md](docs/API_endpoints.md)
- Health: http://localhost:8000/health

## API documentation

Full endpoint reference with request/response examples: **[docs/API.md](docs/API.md)**  
Quick endpoint tables by area: **[docs/API_endpoints.md](docs/API_endpoints.md)**

Quick list:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Send OTP for new rider |
| POST | `/api/v1/auth/login` | Send OTP for existing rider |
| POST | `/api/v1/auth/verify-otp` | Verify OTP → JWT tokens |
| POST | `/api/v1/auth/logout` | Revoke refresh token |
| GET | `/api/v1/auth/me` | Current user |
| GET/PATCH | `/api/v1/profile` | Rider profile |
| GET | `/api/v1/stats` | Ride stats |
| GET | `/api/v1/location/reverse-geocode` | Lat/lng → address |
| GET | `/api/v1/ride-types` | Mini, sedan, etc. |
| POST | `/api/v1/rides/estimate` | Fare quote |
| POST | `/api/v1/rides` | Create ride |
| POST | `/api/v1/rides/{id}/cancel` | Cancel ride |
| GET | `/api/v1/rides/{id}` | Ride details |
| GET | `/api/v1/rides/{id}/status` | Current status |
| GET | `/api/v1/rides/history` | Paginated history |
| WS | `/api/v1/ws/rides/{id}?token=...` | Live status events |

## Ride status (Phase 1)

After booking, rides move to `searching_driver` and **stay there** until Phase 2 adds driver matching. Cancellable while `requested` or `searching_driver`.

`requested` → `searching_driver` → *(Phase 2: driver_assigned → … → completed)* | `cancelled`

## OTP in development

With `OTP_DEBUG=true`, the OTP is returned in the API response as `debug_otp` and logged when `OTP_PROVIDER=console`.

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
