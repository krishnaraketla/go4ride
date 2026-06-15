# Deploying Go4Ride backend to Render (free tier)

This guide deploys the FastAPI app, Postgres, and Redis-compatible
Key Value cache to [Render](https://render.com) using the
[`render.yaml`](../render.yaml) blueprint in this repo.

> Free-tier notes
>
> - **Web service** spins down after ~15 minutes of inactivity; the next
>   request triggers a cold start (~30 s).
> - **Postgres free plan expires after 30 days** — Render emails you a
>   warning; upgrade or recreate to keep data.
> - **Key Value free plan** has 25 MB and no persistence. This app only
>   uses Redis for OTP rate limits, idempotency keys, and WebSocket
>   pub/sub, all of which are transient — that's fine.
> - **WebSockets** work out of the box on Render web services.

## 1. Prerequisites

- A GitHub account with this repo pushed (the blueprint deploys from
  the `main` branch by default).
- A Render account (free): https://dashboard.render.com/register

## 2. One-click blueprint deploy

1. Open https://dashboard.render.com/blueprints and click
   **New Blueprint Instance**.
2. Connect your GitHub account and select the `go4ride` repository.
3. Render detects `render.yaml` and shows the three services it will
   create:
   - `go4ride-api` (Web Service, Python, free)
   - `go4ride-postgres` (Postgres, free)
   - `go4ride-cache` (Key Value / Redis-compatible, free)
4. Click **Apply**. Render provisions Postgres and the cache, then
   builds and starts the API. First build takes 3–5 minutes.

The web service:

- Runs `pip install -e .` as the build step.
- On every start, runs `alembic upgrade head` and then
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Exposes `/health` for Render's health check.

`DATABASE_URL` and `REDIS_URL` are wired automatically from the
managed services. `JWT_SECRET` is auto-generated.

## 3. Seed initial data (one time)

The blueprint runs migrations on every start, but does **not** seed
the database. To create ride types, fare rules, the mock driver, and
the `WELCOME5` promo:

1. In the Render dashboard, open the `go4ride-api` service.
2. Click **Shell** in the left sidebar.
3. Run:

   ```bash
   python -m app.db.seed
   ```

You only need to do this once (or after a Postgres reset).

## 4. Verify the deploy

Render gives the web service a URL like
`https://go4ride-api.onrender.com`.

```bash
# Health check
curl https://go4ride-api.onrender.com/health

# OpenAPI docs
open https://go4ride-api.onrender.com/docs

# OTP flow (works because OTP_DEBUG=true returns the code in the response)
curl -X POST https://go4ride-api.onrender.com/api/v1/auth/request-otp \
  -H "Content-Type: application/json" \
  -d '{"phone":"+919876543210"}'
```

WebSocket smoke test:

```
wss://go4ride-api.onrender.com/api/v1/ws/rides/<ride_id>?token=<access_token>
```

## 5. Production hardening (when you're ready)

The blueprint defaults are tuned for a demo. Once you have real users,
update these via the Render dashboard's **Environment** tab for
`go4ride-api`:

| Variable               | Change to                              | Why                                                                |
| ---------------------- | -------------------------------------- | ------------------------------------------------------------------ |
| `OTP_PROVIDER`         | `twilio` or `msg91`                    | Real SMS delivery                                                  |
| `OTP_DEBUG`            | `false`                                | Stop returning OTP in API responses                                |
| `TWILIO_*` / `MSG91_*` | provider credentials                   | Required for the chosen provider                                   |
| `MAPS_PROVIDER`        | `google` (default in blueprint)        | Real distance/duration and live ETA                                |
| `MAPS_API_KEY`         | Google server API key                  | Enable **Geocoding**, **Directions**, and **Distance Matrix** APIs |
| `MOCK_DRIVER_ENABLED`  | `false` (default in blueprint)         | Real driver accept/complete flow; set `true` for auto-advance demos |
| `DRIVER_ETA_CACHE_TTL_SEC` | `30`                             | Cache Google ETA per ride to limit API calls                       |
| `CLEAR_RIDES_ON_STARTUP`         | `false` (default in blueprint: `true`) | Stop wiping rides on every deploy                                |
| `CLEAR_OTP_LIMITS_ON_STARTUP`    | `false`                                | Stop resetting demo OTP rate limits on deploy                    |

After changing env vars, Render auto-redeploys the service.

## 6. Upgrade paths

Free tier is suitable for prototypes only. When you outgrow it:

- **Web Service** → **Starter ($7/mo)**: 512 MB RAM, no idle spin-down,
  custom domain TLS included.
- **Postgres** → any paid plan: removes the 30-day expiry, adds backups
  and point-in-time recovery.
- **Key Value** → paid plan: larger memory and persistence options.

For real horizontal scaling later, consider:

- Multiple web instances behind Render's load balancer
  (WebSocket events are fanned out via Redis pub/sub, so multiple
  instances work — but sticky sessions reduce reconnect churn).
- Moving Postgres/Redis to a dedicated provider (Neon, Supabase,
  Upstash) if Render's plans don't fit.

## 7. Troubleshooting

| Symptom                                                      | Likely cause                                                                                                | Fix                                                                                          |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Build fails with `error: Microsoft Visual C++` or similar    | Wrong runtime / Python version mismatch                                                                     | Ensure `PYTHON_VERSION=3.11.9` is set (already in blueprint)                                  |
| `sqlalchemy.exc.InvalidRequestError: dialect 'postgres'`     | `DATABASE_URL` was set manually without the `+asyncpg` driver                                                | Either leave it auto-wired by the blueprint, or paste Render's URL as-is — `config.py` rewrites `postgres://` and `postgresql://` to `postgresql+asyncpg://` automatically |
| First request takes 30+ seconds                              | Free-tier cold start after idle spin-down                                                                   | Upgrade to Starter, or hit `/health` from an external ping every few minutes (UptimeRobot)   |
| WebSocket disconnects after deploy                           | Render restarted the service on a new deploy                                                                | Expected; clients should reconnect with exponential backoff                                  |
| `alembic` complains "Target database is not up to date"      | Migrations not applied                                                                                      | Migrations run automatically in `startCommand`; check the service logs for errors            |
| Postgres connection refused                                  | Free Postgres expired (30 days)                                                                             | Recreate the database in Render, then run `alembic upgrade head` + `python -m app.db.seed`   |
