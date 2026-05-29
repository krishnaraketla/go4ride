# Go4Ride API Documentation

**Version:** 0.2.0 (Phase 0 + Phase 1 + Phase 2 — Rider app)  
**Base URL:** `http://localhost:8000` (development)

Interactive OpenAPI docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Table of contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Common conventions](#common-conventions)
4. [Error responses](#error-responses)
5. [Ride status lifecycle](#ride-status-lifecycle)
6. [Endpoints](#endpoints)
  - [Health](#health)
  - [Auth](#auth)
  - [Profile](#profile)
  - [Location](#location)
  - [Rides](#rides)
  - [WebSocket](#websocket)
7. [Typical booking flow](#typical-booking-flow)

---

## Overview

The Go4Ride API powers the **rider mobile app**. All business routes are prefixed with `/api/v1`.


| Area    | Description                                                                          |
| ------- | ------------------------------------------------------------------------------------ |
| Phase 0 | Infrastructure, JWT auth, health check                                               |
| Phase 1 | Rider phone-OTP auth, profile, maps, fare quotes, ride booking, real-time status     |
| Phase 2 | Insights, bookings history filters, repeat ride, saved addresses, settings, wallet/promo/referral/email verify, payment & invoice stubs |

See [API_endpoints.md](./API_endpoints.md) for the full Phase 2 endpoint list.

Driver matching APIs are **not** included in this version. In development (`MOCK_DRIVER_ENABLED=true`), rides auto-advance through the full lifecycle using a seeded mock driver. In production (`MOCK_DRIVER_ENABLED=false`), rides stay at `searching_driver` until Phase 2.

---

## Response envelope

All `/api/v1` JSON endpoints return a consistent wrapper so the client can handle every response the same way:

```json
{
  "success": true,
  "message": "OTP sent",
  "data": {
    "expires_in_minutes": 10,
    "is_new_user": true,
    "debug_otp": "482910"
  }
}
```

- `success` — `true` on HTTP 2xx, `false` on errors.
- `message` — human-readable summary for toasts or alerts.
- `data` — payload for the endpoint (object, array, or `null` for message-only actions like logout).

The `/health` endpoint is **not** wrapped (`{"status": "ok"}`). WebSocket events are unchanged.

**Client pattern**

```javascript
if (response.success) {
  // use response.data
} else {
  // show response.message; optional response.data.code
}
```

---

## Authentication

Protected endpoints require a **Bearer access token** in the `Authorization` header:

```http
Authorization: Bearer <access_token>
```

### Token pair


| Token           | Lifetime (default) | Use                                              |
| --------------- | ------------------ | ------------------------------------------------ |
| `access_token`  | 15 minutes         | API requests + WebSocket `token` query param     |
| `refresh_token` | 7 days             | Returned on verify-otp; send to logout to revoke |


Obtain tokens via `POST /api/v1/auth/verify-otp` after OTP verification.

---

## Common conventions

### Headers


| Header            | Required                  | Description                                                       |
| ----------------- | ------------------------- | ----------------------------------------------------------------- |
| `Authorization`   | Protected routes          | `Bearer <access_token>`                                           |
| `Content-Type`    | POST/PATCH with body      | `application/json`                                                |
| `Idempotency-Key` | Optional on `POST /rides` | Unique key; duplicate requests return the cached response for 24h |
| `X-Request-ID`    | Optional                  | Client-generated ID; echoed in response as `X-Request-ID`         |


### Pagination

List endpoints use query parameters:


| Param   | Default | Max   | Description           |
| ------- | ------- | ----- | --------------------- |
| `page`  | `1`     | —     | Page number (1-based) |
| `limit` | `20`    | `100` | Items per page        |


### Coordinates

Latitude and longitude are decimal numbers:

- `lat`: -90 to 90  
- `lng`: -180 to 180

### Phone numbers

E.164-style strings, 10–15 characters (e.g. `+919876543210`).

---

## Error responses

Errors use the same envelope with `success: false`:

```json
{
  "success": false,
  "message": "Ride cannot be cancelled",
  "data": {
    "code": "RIDE_NOT_CANCELLABLE"
  }
}
```

Validation errors (`422`) include `data.errors` with FastAPI validation details.

### Common HTTP status codes


| Status | Meaning                                             |
| ------ | --------------------------------------------------- |
| `400`  | Invalid input or business rule violation            |
| `401`  | Missing or invalid access token                     |
| `403`  | Authenticated but not allowed (e.g. non-rider role) |
| `404`  | Resource not found                                  |
| `409`  | Conflict (e.g. phone already registered)            |
| `429`  | Rate limited (OTP requests)                         |
| `500`  | Internal server error (`INTERNAL_ERROR`)            |


### Error codes reference


| Code                   | Typical cause                           |
| ---------------------- | --------------------------------------- |
| `OTP_INVALID`          | Wrong or expired OTP                    |
| `ACCOUNT_BLOCKED`      | User is blocked                         |
| `RIDE_TYPE_NOT_FOUND`  | Unknown `ride_type_slug`                |
| `FARE_RULE_NOT_FOUND`  | No fare rule for ride type              |
| `RIDE_NOT_FOUND`       | Ride ID invalid or not owned by rider   |
| `RIDE_NOT_CANCELLABLE` | Cancel attempted after matching started |
| `RATE_LIMITED`         | Too many OTP requests                   |
| `UNAUTHORIZED`         | Invalid or missing JWT                  |
| `FORBIDDEN`            | Rider access required                   |


---

## Ride status lifecycle

```
requested → searching_driver → driver_assigned → driver_arrived → in_progress → completed
                            ↘ cancelled (rider cancel, until in_progress)
```


| Status             | Behavior                                                                                      |
| ------------------ | --------------------------------------------------------------------------------------------- |
| `requested`        | Ride record created                                                                           |
| `searching_driver` | Set immediately after create                                                                  |
| `driver_assigned`  | Mock driver assigned (dev) or real match (Phase 2)                                            |
| `driver_arrived`   | Driver at pickup                                                                              |
| `in_progress`      | Trip started; `start_otp` set on ride                                                         |
| `completed`        | Trip ended; `final_fare` set                                                                  |
| `cancelled`        | Rider cancelled while `requested`, `searching_driver`, `driver_assigned`, or `driver_arrived` |


When a driver is assigned, `RideResponse`, `RideStatusResponse`, and WebSocket events include a `driver` object (`id`, `name`, `phone`, vehicle fields, optional `lat`/`lng`, `eta_min`).

---

## Endpoints

### Health

#### `GET /health`

No authentication. Service liveness check.

**Response `200`**

```json
{
  "status": "ok"
}
```

---

### Auth

Base path: `/api/v1/auth`

The rider app uses a single-step phone-OTP flow: there is **no separate
`/register` or `/login` endpoint**. The client always calls
`POST /auth/request-otp` followed by `POST /auth/verify-otp`. The account is
created lazily on first verification.

#### `POST /request-otp`

Send an OTP to a phone number. Works for both first-time sign-up and returning
login — the server figures out which case it is and reports it via
`is_new_user` so the UI can plan its next screen.

**Auth:** None

**Request body**

```json
{
  "phone": "+919876543210"
}
```


| Field   | Type   | Required | Description |
| ------- | ------ | -------- | ----------- |
| `phone` | string | Yes      | 10–15 chars |


**Response `200`**

```json
{
  "success": true,
  "message": "OTP sent",
  "data": {
    "expires_in_minutes": 10,
    "is_new_user": true,
    "debug_otp": "482910"
  }
}
```

- `data.is_new_user` — `true` when this phone has never signed in before. Use it to
  decide whether to collect a name on the OTP-verify screen.
- `data.debug_otp` — only present when `OTP_DEBUG=true` (development).

**Errors:** `400 ACCOUNT_BLOCKED`, `429 RATE_LIMITED`

---

#### `POST /verify-otp`

Verify the OTP and receive JWT tokens. Creates the rider account automatically
when the phone is new.

**Auth:** None

**Request body**

```json
{
  "phone": "+919876543210",
  "code": "482910",
  "name": "Krishna",
  "referral_code": "ABC123",
  "fcm_token": "optional-fcm-token",
  "platform": "ios"
}
```


| Field           | Type   | Required | Description                                                                                                  |
| --------------- | ------ | -------- | ------------------------------------------------------------------------------------------------------------ |
| `phone`         | string | Yes      | Same phone used for `request-otp`                                                                            |
| `code`          | string | Yes      | 4–8 digit OTP                                                                                                |
| `name`          | string | No       | Saved on first sign-in for new users (skipped if the account already exists with a name).                    |
| `referral_code` | string | No       | Applied on first sign-in to credit the referrer. Ignored for existing users.                                 |
| `fcm_token`     | string | No       | Push notification token (Phase 1.5)                                                                          |
| `platform`     | string | No       | e.g. `ios`, `android`                                                                                         |


**Response `200`**

```json
{
  "success": true,
  "message": "Signed in successfully",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "role": "rider",
    "is_new_user": true
  }
}
```

`data.is_new_user` mirrors the `request-otp` response and lets the client route to
an onboarding screen (e.g. ask for name later via `PATCH /profile`) the first
time a rider signs in.

**Errors:** `400 OTP_INVALID`, `400 ACCOUNT_BLOCKED`

---

#### `POST /logout`

Revoke a refresh token.

**Auth:** None (refresh token in body)

**Request body**

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response `200`**

```json
{
  "message": "Logged out"
}
```

---

#### `GET /me`

Return the authenticated user.

**Auth:** Bearer (any valid user)

**Response `200`**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "phone": "+919876543210",
  "name": "Krishna",
  "role": "rider"
}
```

---

### Profile

**Auth:** Bearer (rider role required)

#### `GET /profile`

**Response `200`**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "phone": "+919876543210",
  "email": null,
  "name": "Krishna",
  "avatar_url": null,
  "role": "rider"
}
```

---

#### `PATCH /profile`

Update profile fields. All fields optional; only sent fields are updated.

**Request body**

```json
{
  "name": "Krishna R",
  "email": "krishna@example.com",
  "avatar_url": "https://cdn.example.com/avatar.jpg"
}
```

**Response `200`** — `ProfileResponse` (same shape as GET).

---

#### `GET /stats`

Rider ride statistics.

**Response `200`**

```json
{
  "total_rides": 12,
  "completed_rides": 10,
  "total_spend": "2450.00",
  "currency": "INR"
}
```

---

### Location

Base path: `/api/v1/location`

#### `GET /reverse-geocode`

Convert coordinates to a human-readable address.

**Auth:** None

**Query parameters**


| Param | Type    | Required | Description |
| ----- | ------- | -------- | ----------- |
| `lat` | decimal | Yes      | -90 to 90   |
| `lng` | decimal | Yes      | -180 to 180 |


**Example**

```http
GET /api/v1/location/reverse-geocode?lat=12.9716&lng=77.5946
```

**Response `200`**

```json
{
  "lat": "12.9716",
  "lng": "77.5946",
  "formatted_address": "Address at 12.9716, 77.5946"
}
```

With `MAPS_PROVIDER=google` or `mapbox` and a valid API key, `formatted_address` comes from the maps provider.

---

### Rides

**Auth:** Bearer (rider) for create/cancel/status/detail/history. Ride types and estimate are public.

#### `GET /ride-types`

List active vehicle categories (e.g. mini, sedan).

**Auth:** None

**Response `200`**

```json
[
  {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "slug": "mini",
    "name": "Go4 Mini",
    "description": "Affordable compact rides",
    "icon_url": null
  },
  {
    "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "slug": "sedan",
    "name": "Go4 Sedan",
    "description": "Comfortable sedan rides",
    "icon_url": null
  }
]
```

---

#### `POST /rides/estimate`

Get distance, duration, and fare quote before booking.

**Auth:** None

**Request body**

```json
{
  "pickup": { "lat": "12.9716", "lng": "77.5946" },
  "drop": { "lat": "12.9352", "lng": "77.6245" },
  "ride_type_slug": "mini"
}
```

**Response `200`**

```json
{
  "distance_km": "8.42",
  "duration_min": "16.84",
  "estimated_fare": "142.68",
  "currency": "INR",
  "surge_multiplier": "1.00"
}
```

**Errors:** `404 RIDE_TYPE_NOT_FOUND`, `404 FARE_RULE_NOT_FOUND`

---

#### `POST /rides`

Create a ride booking.

**Auth:** Bearer (rider)

**Headers:** `Idempotency-Key` (optional, recommended)

**Request body**

```json
{
  "pickup": { "lat": "12.9716", "lng": "77.5946" },
  "drop": { "lat": "12.9352", "lng": "77.6245" },
  "pickup_address": "MG Road, Bangalore",
  "drop_address": "Koramangala, Bangalore",
  "ride_type_slug": "mini"
}
```

**Response `200`**

```json
{
  "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "status": "searching_driver",
  "pickup_lat": "12.9716",
  "pickup_lng": "77.5946",
  "pickup_address": "MG Road, Bangalore",
  "drop_lat": "12.9352",
  "drop_lng": "77.6245",
  "drop_address": "Koramangala, Bangalore",
  "estimated_fare": "142.68",
  "final_fare": null,
  "distance_km": "8.42",
  "duration_min": "16.84",
  "surge_multiplier": "1.00",
  "ride_type_slug": "mini",
  "requested_at": "2026-05-20T10:30:00Z",
  "driver_assigned_at": null,
  "driver_arrived_at": null,
  "started_at": null,
  "completed_at": null,
  "cancelled_at": null,
  "driver": null
}
```

Status transitions: `requested` → `searching_driver` (WebSocket events published for both). With mock driver enabled, further transitions are published automatically.

---

#### `POST /rides/{ride_id}/cancel`

Cancel a ride. Allowed while status is `requested`, `searching_driver`, `driver_assigned`, or `driver_arrived`. Not allowed once `in_progress`.

**Auth:** Bearer (rider, must own ride)

**Path parameters**


| Param     | Description      |
| --------- | ---------------- |
| `ride_id` | UUID of the ride |


**Response `200`** — `RideResponse` with `status: "cancelled"`.

**Errors:** `400 RIDE_NOT_CANCELLABLE`, `404 RIDE_NOT_FOUND`

---

#### `GET /rides/{ride_id}/status`

Lightweight status check.

**Auth:** Bearer (rider)

**Response `200`**

```json
{
  "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "status": "driver_assigned",
  "message": "Driver assigned",
  "driver": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Dev Driver",
    "phone": "+919999000001",
    "vehicle_model": "Toyota Etios",
    "vehicle_plate": "KA01AB1234",
    "vehicle_color": "white",
    "lat": "12.9700",
    "lng": "77.5900",
    "eta_min": 5
  }
}
```

---

#### `GET /rides/{ride_id}`

Full ride details.

**Auth:** Bearer (rider)

**Response `200`** — `RideResponse` (same shape as create response).

---

#### `GET /rides/history`

Paginated list of the rider's past and current rides (newest first).

**Auth:** Bearer (rider)

**Query parameters:** `page`, `limit`

**Example**

```http
GET /api/v1/rides/history?page=1&limit=20
```

**Response `200`**

```json
{
  "items": [ { "...": "RideResponse" } ],
  "page": 1,
  "limit": 20,
  "total": 42
}
```

---

### WebSocket

#### `WS /api/v1/ws/rides/{ride_id}`

Subscribe to real-time ride status updates for a specific ride.

**Auth:** Access token as query parameter (not header).

**URL**

```
ws://localhost:8000/api/v1/ws/rides/{ride_id}?token=<access_token>
```

**On connect** — server sends:

```json
{
  "type": "connected",
  "ride_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "user_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Status events** — pushed when ride status changes (JSON text). The `status` field is one of:


| `status`           | Typical message      | `driver` object                        |
| ------------------ | -------------------- | -------------------------------------- |
| `requested`        | Ride requested       | No                                     |
| `searching_driver` | Searching for driver | No                                     |
| `driver_assigned`  | Driver assigned      | Yes                                    |
| `driver_arrived`   | Driver has arrived   | Yes                                    |
| `in_progress`      | Trip started         | Yes                                    |
| `completed`        | Trip completed       | Yes                                    |
| `cancelled`        | Cancelled by rider   | Yes (if a driver was already assigned) |


In dev with mock driver enabled, events usually arrive in lifecycle order: `requested` → `searching_driver` → `driver_assigned` → `driver_arrived` → `in_progress` → `completed`. `cancelled` is emitted if the rider cancels while still cancellable (before `in_progress`). See [Ride status lifecycle](#ride-status-lifecycle).

Example (`driver_assigned`):

```json
{
  "ride_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "status": "driver_assigned",
  "message": "Driver assigned",
  "created_at": "2026-05-20T10:30:05.123456+00:00",
  "driver": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Dev Driver",
    "phone": "+919999000001",
    "vehicle_model": "Toyota Etios",
    "vehicle_plate": "KA01AB1234",
    "vehicle_color": "white",
    "lat": "12.9716",
    "lng": "77.5946",
    "eta_min": 5
  }
}
```

**Close codes**


| Code   | Meaning                  |
| ------ | ------------------------ |
| `4001` | Invalid or expired token |


**Client notes**

- Connect after `POST /rides` returns `id`.
- Send periodic ping messages or empty text to keep connection alive; server reads incoming text in a loop.
- Reconnect with a fresh access token if the connection drops.

---

## Typical booking flow

```text
1. POST /auth/request-otp       → OTP sent, is_new_user flag
2. POST /auth/verify-otp        → access_token, refresh_token (account auto-created if new)
3. GET  /location/reverse-geocode?lat=...&lng=...  (pickup)
4. GET  /location/reverse-geocode?lat=...&lng=...  (drop)
5. GET  /ride-types
6. POST /rides/estimate         → fare preview
7. POST /rides                  → ride id, status searching_driver
8. WS   /ws/rides/{id}?token=... → live status events
9. (optional) POST /rides/{id}/cancel
10. GET /rides/history          → past rides
```

### cURL examples

**Request OTP**

```bash
curl -X POST http://localhost:8000/api/v1/auth/request-otp \
  -H "Content-Type: application/json" \
  -d '{"phone":"+919876543210"}'
```

**Verify OTP** (pass `name` only when the previous response had `is_new_user: true`)

```bash
curl -X POST http://localhost:8000/api/v1/auth/verify-otp \
  -H "Content-Type: application/json" \
  -d '{"phone":"+919876543210","code":"482910","name":"Krishna"}'
```

**Estimate fare**

```bash
curl -X POST http://localhost:8000/api/v1/rides/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "pickup":{"lat":"12.9716","lng":"77.5946"},
    "drop":{"lat":"12.9352","lng":"77.6245"},
    "ride_type_slug":"mini"
  }'
```

**Create ride**

```bash
curl -X POST http://localhost:8000/api/v1/rides \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: book-20260520-001" \
  -d '{
    "pickup":{"lat":"12.9716","lng":"77.5946"},
    "drop":{"lat":"12.9352","lng":"77.6245"},
    "pickup_address":"MG Road",
    "drop_address":"Koramangala",
    "ride_type_slug":"mini"
  }'
```

---

## Changelog


| Version | Scope                        |
| ------- | ---------------------------- |
| 0.1.0   | Phase 0 + Phase 1 rider APIs |


