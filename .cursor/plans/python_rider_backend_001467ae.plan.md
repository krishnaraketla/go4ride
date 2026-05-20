---
name: Python Rider Backend
overview: "Greenfield FastAPI backend for Go4Ride, Phase 0–1 targeting the rider app: auth (OTP), location/fare helpers, ride booking and lifecycle, WebSocket ride updates. Driver matching, driver APIs, and admin panel follow in later phases on the same foundation."
todos:
  - id: phase0-scaffold
    content: Scaffold FastAPI + docker-compose (Postgres, Redis) + Alembic + core config/security/deps
    status: completed
  - id: phase0-models
    content: "Add ORM models: User, OTP, RideType, FareRule, Ride, RideStatusEvent + initial migration"
    status: completed
  - id: phase1-auth
    content: Implement rider register/login/verify-otp/logout with JWT + OTP provider integration
    status: completed
  - id: phase1-location-fare
    content: Reverse geocode + ride estimate + ride-types seed endpoints
    status: completed
  - id: phase1-rides-rest
    content: Create/cancel ride, status, details, history, profile, stats REST APIs
    status: completed
  - id: phase1-websocket
    content: WebSocket ride channel + Redis pub/sub on status changes
    status: completed
  - id: phase2-driver
    content: Driver app APIs, Redis geo, matching, full ride lifecycle (deferred)
    status: completed
  - id: phase3-admin
    content: "Admin APIs: users, drivers, fare, surge, dashboard, support (deferred)"
    status: completed
isProject: false
---

# Go4Ride Python Backend Plan (Rider First)

## Context

- Workspace [`/Users/krishna/go4ride/backend`](/Users/krishna/go4ride/backend) is **empty** — full greenfield.
- **Phase 1 scope:** Rider mobile app APIs + shared foundation that driver/admin will reuse later.
- **Real-time:** WebSockets from FastAPI (your choice); Redis pub/sub to fan out events across workers.

## Recommended stack

| Layer | Choice | Why |
|-------|--------|-----|
| API | **FastAPI** + Uvicorn | Async, OpenAPI for mobile teams, native WebSocket support |
| DB | **PostgreSQL 16** + SQLAlchemy 2.0 (async) + **Alembic** | Relational ride/booking data, migrations |
| Cache / geo / pub-sub | **Redis 7** | `GEOADD`/`GEORADIUS` for nearby drivers (Phase 2), pub/sub for WS broadcast |
| Auth | **JWT** (access + refresh) + **OTP** (SMS provider) | Same token shape for rider/driver/admin later (`role` claim) |
| Files | **S3-compatible** (AWS S3 or MinIO in dev) | Driver docs / face upload in Phase 2 |
| Background jobs | **ARQ** or **Celery** (Phase 2+) | Driver matching retries, notification fan-out |
| Maps | **Google Maps Platform** or **Mapbox** | Distance/duration, reverse geocoding |

```mermaid
flowchart TB
  subgraph clients [Phase1 Clients]
    RiderApp[Rider App]
  end
  subgraph api [FastAPI]
    REST[REST Routers]
    WS[WebSocket Hub]
  end
  subgraph data [Data Layer]
    PG[(PostgreSQL)]
    Redis[(Redis)]
  end
  RiderApp --> REST
  RiderApp --> WS
  REST --> PG
  WS --> Redis
  Redis --> WS
  REST --> Redis
```

---

## Project layout (create in Phase 0)

```
backend/
├── app/
│   ├── main.py                 # FastAPI app, lifespan, CORS
│   ├── core/
│   │   ├── config.py           # pydantic-settings (env)
│   │   ├── security.py         # JWT, password hashing if needed
│   │   └── deps.py             # DB session, current_user
│   ├── db/
│   │   ├── base.py
│   │   └── session.py
│   ├── models/                 # SQLAlchemy ORM
│   ├── schemas/                # Pydantic request/response
│   ├── api/
│   │   └── v1/
│   │       ├── router.py
│   │       ├── auth.py
│   │       ├── rides.py
│   │       ├── location.py
│   │       └── ws.py
│   ├── services/               # business logic (no HTTP here)
│   │   ├── auth_service.py
│   │   ├── ride_service.py
│   │   ├── fare_service.py
│   │   └── geo_service.py
│   └── workers/                # Phase 2: matching, notifications
├── alembic/
├── tests/
├── docker-compose.yml          # postgres + redis + minio
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Core data model (design now, implement incrementally)

Entities needed for **rider Phase 1** (driver/admin fields nullable or stubbed):

- **User** — `id`, `phone` (unique), `email`, `name`, `role` (`rider` \| `driver` \| `admin`), `is_blocked`, timestamps
- **OTPVerification** — `phone`, `code_hash`, `expires_at`, `purpose` (`login` \| `register`)
- **RefreshToken** — optional blacklist table for logout
- **RideType** — `mini`, `sedan`, base fare rules (seed data)
- **FareRule** — per km/min, base fare, minimum fare (admin-managed later)
- **Ride** — `id`, `rider_id`, `driver_id` (nullable), `status`, pickup/drop lat-lng + address text, `estimated_fare`, `final_fare`, `ride_type_id`, timestamps per status
- **RideStatusEvent** — audit trail for lifecycle + notifications
- **Payment** — stub for Phase 3 (not in rider MVP)

**Ride status enum** (single source of truth for REST + WS + notifications):

`requested` → `searching_driver` → `driver_assigned` → `driver_arrived` → `in_progress` → `completed` | `cancelled`

Phase 1 rider APIs can stop at `requested` / `searching_driver` / `cancelled` until driver matching exists; WS still emits transitions.

---

## End-to-end ride booking flow

Full journey across **rider app**, **driver app**, **FastAPI**, **PostgreSQL**, **Redis**, and **Maps API**. Phase 1 implements the left/pre-booking column and create/cancel; matching through completion unlock in Phase 2.

### High-level flow (states + actors)

```mermaid
flowchart TD
  subgraph prebook [Pre-booking - Rider]
    A1[Open app - JWT valid]
    A2[Set pickup on map]
    A3[Reverse geocode pickup]
    A4[Set drop on map]
    A5[Reverse geocode drop]
    A6[GET ride-types mini sedan]
    A7[POST rides/estimate fare distance]
    A8{Rider confirms book}
  end

  subgraph book [Booking - Rider + API]
    B1[POST rides - create ride]
    B2[status: requested]
    B3[WS connect ws/rides/id]
    B4[status: searching_driver]
    B5[Matching worker Redis GEORADIUS]
  end

  subgraph match [Driver matching - Phase 2]
    M1[Notify nearby online drivers]
    M2{Driver accepts}
    M3[Driver rejects or timeout]
    M4[status: driver_assigned]
    M5[Retry search - optional]
  end

  subgraph trip [Active trip - Driver actions]
    T1[Driver navigates to pickup]
    T2[POST driver arrived]
    T3[status: driver_arrived]
    T4[Verify trip OTP + face - Phase 2]
    T5[POST start trip]
    T6[status: in_progress]
    T7[Driver streams location to Redis]
    T8[POST end trip]
    T9[status: completed]
  end

  subgraph cancel [Cancel paths]
    C1[Rider POST rides/id/cancel]
    C2[status: cancelled]
  end

  subgraph post [Post-ride]
    P1[Compute final_fare]
    P2[WS + push notification]
    P3[GET rides/history]
  end

  A1 --> A2 --> A3 --> A4 --> A5 --> A6 --> A7 --> A8
  A8 --> B1 --> B2 --> B3 --> B4 --> B5
  B5 --> M1
  M1 --> M2
  M1 --> M3
  M3 --> M5
  M5 --> M1
  M2 --> M4
  M4 --> T1 --> T2 --> T3 --> T4 --> T5 --> T6 --> T7 --> T8 --> T9
  T9 --> P1 --> P2 --> P3

  B2 --> C1
  B4 --> C1
  M4 --> C1
  T3 --> C1
  C1 --> C2
  C2 --> P2
```

### Detailed sequence (APIs + real-time)

```mermaid
sequenceDiagram
  participant Rider as RiderApp
  participant Driver as DriverApp
  participant API as FastAPI
  participant Maps as MapsAPI
  participant DB as PostgreSQL
  participant Redis as Redis
  participant Worker as MatchingWorker

  Note over Rider,API: Pre-booking
  Rider->>API: GET /location/reverse-geocode pickup
  API->>Maps: lat lng to address
  Maps-->>API: formatted address
  API-->>Rider: pickup address
  Rider->>API: GET /location/reverse-geocode drop
  API->>Maps: lat lng to address
  API-->>Rider: drop address
  Rider->>API: GET /ride-types
  API->>DB: list RideType
  API-->>Rider: mini sedan options
  Rider->>API: POST /rides/estimate
  API->>Maps: distance duration matrix
  API->>DB: FareRule + optional SurgeZone
  API-->>Rider: estimated_fare ETA

  Note over Rider,Redis: Book ride
  Rider->>API: POST /rides pickup drop ride_type
  API->>DB: INSERT Ride status requested
  API->>DB: INSERT RideStatusEvent
  API->>Redis: PUBLISH ride:id event
  API-->>Rider: ride_id status
  Rider->>API: WS /ws/rides/id token
  API->>Redis: SUBSCRIBE ride:id
  API->>DB: UPDATE status searching_driver
  API->>Redis: PUBLISH ride:id searching_driver
  Redis-->>Rider: WS status update

  Note over Worker,Driver: Matching Phase 2
  API->>Worker: enqueue match ride_id
  Worker->>Redis: GEORADIUS pickup online drivers
  Worker->>Driver: push ride request WS
  alt Driver accepts
    Driver->>API: POST /driver/rides/id/accept
    API->>DB: SET driver_id status driver_assigned
    API->>Redis: PUBLISH ride:id assigned
    Redis-->>Rider: WS driver details ETA
  else Reject or timeout
    Driver->>API: POST /driver/rides/id/reject
    Worker->>Redis: next candidate or retry
    Rider->>API: POST /rides/id/retry optional
  end

  Note over Driver,Rider: Trip lifecycle
  loop Every few seconds
    Driver->>API: POST /driver/location lat lng
    API->>Redis: GEOADD driver:locations
  end
  Driver->>API: POST /driver/rides/id/arrived
  API->>DB: status driver_arrived
  API->>Redis: PUBLISH
  Redis-->>Rider: WS driver arrived
  Driver->>API: POST /driver/rides/id/start OTP verified
  API->>DB: status in_progress started_at
  API->>Redis: PUBLISH
  Redis-->>Rider: WS trip started
  Driver->>API: POST /driver/rides/id/end
  API->>Maps: optional route recap
  API->>DB: status completed final_fare
  API->>Redis: PUBLISH
  Redis-->>Rider: WS completed receipt

  Note over Rider,API: Cancel anytime before in_progress
  Rider->>API: POST /rides/id/cancel
  API->>DB: status cancelled
  API->>Redis: PUBLISH
  Redis-->>Rider: WS cancelled
  Redis-->>Driver: WS ride cancelled
```

### Status timeline (what the rider sees)

| Step | Ride status | Trigger | Rider UI | Real-time |
|------|-------------|---------|----------|-----------|
| 1 | — | Pickup/drop + estimate | Fare preview | REST only |
| 2 | `requested` | `POST /rides` | “Confirming…” | WS optional |
| 3 | `searching_driver` | Matching worker starts | “Finding driver…” | WS + push |
| 4 | `driver_assigned` | Driver accepts | Driver name, vehicle, ETA | WS + push |
| 5 | `driver_arrived` | Driver at pickup | “Driver has arrived” | WS + push |
| 6 | `in_progress` | Start trip (+ OTP/face) | Live map / tracking | WS + location |
| 7 | `completed` | End trip | Receipt, rate driver | WS + push |
| — | `cancelled` | Rider or system cancel | Cancelled screen | WS + push |

### Backend responsibilities per step

**In plain English** — what the server is responsible for at each stage:

1. **Geocode + estimate** — Turn map coordinates into readable addresses for pickup and drop. Call the maps provider for route distance and travel time. Look up your fare rules (and surge, when enabled) and return a price quote the rider can accept before booking. Do not create a ride record yet.

2. **Create ride** — When the rider confirms, save a new ride with pickup/drop, ride type, and quoted fare. Record the first status (`requested`, then `searching_driver`). Enforce auth, idempotency, and validation (e.g. rider not blocked, coordinates in service area).

3. **Real-time updates** — Keep a live channel open for that ride so the app does not have to poll. Whenever status changes, broadcast the update to connected clients (rider and, later, driver) via WebSocket, using Redis so all API instances stay in sync.

4. **Match driver** — Find online drivers near the pickup (Redis geo index). Send the request to one or more drivers. When a driver accepts, attach them to the ride and move status to `driver_assigned`. Handle rejections, timeouts, and optional retry without leaving the ride in a stuck state.

5. **Trip transitions** — Apply driver actions in order: arrived at pickup, start trip (after OTP/face checks when required), end trip. Update status and timestamps on each step. Reject invalid transitions (e.g. start before arrived). Optionally recalculate final fare at end using actual distance/time.

6. **Notifications** — On every status change, notify interested parties: WebSocket immediately for foreground apps; mobile push (FCM/APNs) when the app is backgrounded (Phase 1.5). Use the same event source so REST, WS, and push never disagree about current ride state.

| Step | Service | Stores |
|------|---------|--------|
| Geocode + estimate | `geo_service`, `fare_service` | Read `FareRule`; call Maps |
| Create ride | `ride_service` | `rides`, `ride_status_events` |
| Real-time updates | `ws` hub + Redis pub/sub | Channel `ride:{id}` |
| Match driver | `matching_service` worker | Redis geo index; update `rides.driver_id` |
| Trip transitions | `ride_service` driver routes | Status + timestamps on `rides` |
| Notifications | event on every status change | Same Redis publish → WS; FCM in Phase 1.5 |

---

## Phase 0 — Foundation (1–2 days)

1. **Scaffold** FastAPI project, `docker-compose` (Postgres, Redis, MinIO optional).
2. **Settings** via `pydantic-settings`: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `OTP_PROVIDER_*`, `MAPS_API_KEY`.
3. **Alembic** initial migration: `users`, `otp_verifications`, `ride_types`, `fare_rules`, `rides`, `ride_status_events`.
4. **Auth primitives**
   - Issue JWT: `sub`, `role`, `exp`; refresh token in HttpOnly cookie or body (mobile-friendly: return refresh in JSON).
   - Dependency `get_current_rider` — rejects `role != rider`.
5. **Global** exception handlers, request ID middleware, structured logging.
6. **Health** `GET /health`, OpenAPI at `/docs`.

No rider-facing business APIs yet — only plumbing.

---

## Phase 1 — Rider app APIs (your estimated list, mapped)

### 1. Authentication (rider subset of your 8 endpoints)

| # | Endpoint | Method | Notes |
|---|----------|--------|-------|
| 1 | `/api/v1/auth/register` | POST | Phone + name; sends OTP; creates user `role=rider` after verify |
| 2 | `/api/v1/auth/login` | POST | Phone → OTP |
| 6 | `/api/v1/auth/verify-otp` | POST | Returns access + refresh JWT |
| 5 | `/api/v1/auth/logout` | POST | Invalidate refresh token |

**Defer to Phase 2 (driver):** register driver, login driver, upload document, face upload — same `auth` router, different `role` and KYC tables (`DriverProfile`, `DriverDocument`).

**OTP flow:** rate-limit by phone/IP in Redis; store hashed OTP; integrate **Twilio** or **MSG91** (config switch).

### 2. Location and map (rider-facing)

| # | Endpoint | Method | Notes |
|---|----------|--------|-------|
| 4 | `/api/v1/location/reverse-geocode` | GET | `lat`, `lng` → address via Maps API |
| 3 | `/api/v1/rides/estimate` | POST | Pickup/drop + `ride_type` → distance, duration, fare (uses `FareRule` + Maps) |

**Phase 2 (needs online drivers):** `GET /api/v1/drivers/nearby` — Redis `GEORADIUS` on `driver:locations`.

### 3. Ride booking

| # | Endpoint | Method | Notes |
|---|----------|--------|-------|
| 4 | `/api/v1/ride-types` | GET | List mini/sedan + icons/descriptions |
| 3 | `/api/v1/rides/estimate` | POST | (above) |
| 1 | `/api/v1/rides` | POST | Create ride → `status=requested`, then enqueue `searching_driver` (stub worker returns 503 or mock assign in dev) |
| 2 | `/api/v1/rides/{id}/cancel` | POST | Rider cancel rules (only before `in_progress`) |

### 4. Ride lifecycle (rider view)

| # | Endpoint | Method | Notes |
|---|----------|--------|-------|
| 5 | `/api/v1/rides/{id}/status` | GET | Current status + driver summary if assigned |
| 6 | `/api/v1/rides/{id}` | GET | Full ride details |
| 7 | `/api/v1/rides/history` | GET | Paginated list for current rider |

**Phase 2+ (driver actions):** arrived, start, end trip — implemented on driver router but update same `Ride` row and emit WS events.

**Phase 2:** trip OTP + face verification at start — `Ride.start_otp`, `DriverProfile.face_embedding_url` or manual admin flag.

### 5. Notifications + WebSocket

| # | Mechanism | Notes |
|---|-----------|-------|
| 1 | `WS /api/v1/ws/rides/{ride_id}?token=...` | Authenticated rider subscribes; server pushes `RideStatusEvent` payloads |
| — | Redis channel `ride:{id}` | On status change: `publish` → all Uvicorn workers → WS manager sends to connected clients |

**Push (FCM/APNs):** optional Phase 1.5 — same event triggers mobile push when app backgrounded; store `UserDevice.fcm_token` on login.

```mermaid
sequenceDiagram
  participant Rider
  participant API as FastAPI
  participant DB as PostgreSQL
  participant R as Redis
  Rider->>API: POST /rides
  API->>DB: insert Ride requested
  API->>R: publish ride:uuid status
  Rider->>API: WS connect ride:uuid
  R->>API: status event
  API->>Rider: WS message
```

### 6. Rider profile / stats (your bottom list)

| # | Endpoint | Method | Notes |
|---|----------|--------|-------|
| 3 | `/api/v1/profile` | GET/PATCH | Name, phone, email, avatar |
| 1 | `/api/v1/stats` | GET | Total rides, spend, rating avg (when ratings exist) |
| 2 | `/api/v1/rides/history` | GET | Same as lifecycle #7 |

---

## Phase 2 — Driver app (after rider MVP stable)

- Driver auth + KYC: register, login, document upload (S3 presigned URLs), face photo
- `PATCH /api/v1/driver/status` — online/offline (sets Redis geo + availability flag)
- `POST /api/v1/driver/location` — high-frequency updates → Redis `GEOADD`
- Accept/reject ride, arrived, start, end trip
- **Matching service:** on `ride.created`, find nearby online drivers (Redis), notify via WS + push; accept assigns `driver_id`; retry endpoint
- Rider endpoints: nearby drivers (optional map preview before book)

---

## Phase 3 — Admin panel APIs

Separate router prefix `/api/v1/admin` + `role=admin` guard:

| Module | Key endpoints |
|--------|----------------|
| User management | list/search users, block/unblock, user ride history |
| Driver management | pending KYC queue, approve/reject, suspend, view documents |
| Quick actions | force driver offline (delete Redis geo + set status) |
| Live map | `GET /admin/drivers/live` — Redis geo + status aggregate |
| Fare management | CRUD `FareRule`, ride types |
| Surge | zones + multiplier schedules (new `SurgeZone` model) |
| Dashboard | rides/day, revenue, active drivers (SQL aggregates) |
| Support | tickets linked to `ride_id` / `user_id` |

Admin UI is a separate frontend; backend only exposes JSON aligned to your admin screens.

---

## API conventions (apply from day one)

- Prefix: `/api/v1`
- JSON errors: `{ "detail": "...", "code": "RIDE_NOT_CANCELLABLE" }`
- Pagination: `?page=1&limit=20` on history/list endpoints
- Idempotency: `Idempotency-Key` header on `POST /rides` (store in Redis 24h)
- Version mobile contracts via OpenAPI export in CI

---

## Security checklist

- JWT short-lived access (15m) + refresh (7d)
- Rate limits: OTP, login, create ride
- Validate lat/lng bounds; sanitize addresses from geocoder
- Presigned S3 uploads — never stream DL/RC through API body
- CORS: rider app bundle IDs / dev origins only
- Admin routes behind separate secret or IP allowlist in production

---

## Testing strategy (minimal but useful)

- **pytest** + **httpx** `AsyncClient` against test DB (docker)
- Unit tests: `fare_service` (distance → price), status transitions
- Integration: register → verify OTP → create ride → WS receives status
- Redis/geo tests in Phase 2

---

## Suggested implementation order (rider app)

1. Phase 0 scaffold + models + migrations  
2. OTP auth + profile  
3. Reverse geocode + fare estimate + ride types seed  
4. Create / cancel ride + status/detail/history REST  
5. WebSocket + Redis pub/sub for ride channel  
6. Stats endpoint  
7. Phase 2 driver location + matching (unblocks full lifecycle)  
8. Phase 3 admin  

---

## What you will **not** build in Phase 1

- Driver register/login, document/face upload  
- Auto driver assign (stub `searching_driver` only)  
- Accept/reject, retry search, driver arrived/start/end  
- Surge, admin CRUD, live admin map  
- Payment capture (unless you add a explicit requirement later)

---

## Environment variables (`.env.example`)

```
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=...
JWT_ACCESS_EXPIRE_MINUTES=15
OTP_PROVIDER=msg91|twilio
MAPS_PROVIDER=google|mapbox
MAPS_API_KEY=...
AWS_S3_BUCKET=...
CORS_ORIGINS=["http://localhost:3000"]
```

---

## Next step after you approve this plan

Implement **Phase 0 + Phase 1** in the empty [`backend`](/Users/krishna/go4ride/backend) folder: `docker-compose up`, first Alembic migration, rider auth and ride APIs, WebSocket hub — with a short README and Postman/OpenAPI collection for the mobile team.
