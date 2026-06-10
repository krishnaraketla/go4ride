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

Driver matching APIs use the same response envelope as rider routes. In development (`MOCK_DRIVER_ENABLED=true`), rides auto-advance through the full lifecycle using a seeded mock driver. In production (`MOCK_DRIVER_ENABLED=false`), rides stay at `searching_driver` until a real driver accepts via `GET /driver/rides/search`.

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

**Auth:** Bearer (rider) for create/cancel/status/detail/history. `POST /rides/quote` is public.

#### `POST /rides/quote`

Preview all active ride types with fare and ETA for a route (single Directions/route call + reverse geocode).

**Auth:** None

**Request body**

```json
{
  "pickup": { "lat": "12.9716", "lng": "77.5946" },
  "drop": { "lat": "12.9352", "lng": "77.6245" }
}
```

**Response `200`** (`data` payload)

```json
{
  "pickup_address": "MG Road, Bengaluru, Karnataka, India",
  "drop_address": "Koramangala, Bengaluru, Karnataka, India",
  "route": {
    "distance_km": "5.20",
    "duration_min": "18.00",
    "polyline": null
  },
  "currency": "INR",
  "surge_multiplier": "1.00",
  "quote_expires_at": "2026-06-02T10:35:00Z",
  "options": [
    {
      "slug": "mini",
      "name": "Go4 Mini",
      "description": "Affordable compact rides",
      "icon_url": null,
      "available": true,
      "drivers_nearby": 1,
      "estimated_fare": "120.00",
      "pickup_eta_min": 5,
      "trip_duration_min": 18,
      "total_eta_min": 23
    }
  ]
}
```

**Errors:** `404 FARE_RULE_NOT_FOUND`

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

**Status events** — pushed when ride status changes (JSON text). Each event includes `"type": "status"`. The `status` field is one of:


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
  "type": "status",
  "ride_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "status": "driver_assigned",
  "message": "Driver assigned",
  "created_at": "2026-05-20T10:30:05.123456+00:00",
  "route_polyline": "encoded_pickup_to_drop_polyline",
  "leg_polyline": "encoded_driver_to_pickup_polyline",
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

**Location update events** — pushed while a driver is on an active ride and sends GPS pings (`PATCH /driver/location`). Throttled to at most one event every 10 seconds per ride.

```json
{
  "type": "location_update",
  "ride_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "status": "driver_assigned",
  "route_polyline": "encoded_pickup_to_drop_polyline",
  "leg_polyline": "encoded_driver_to_pickup_polyline",
  "driver": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Dev Driver",
    "lat": "12.9710",
    "lng": "77.5940",
    "eta_min": 4
  },
  "updated_at": "2026-05-20T10:31:00.123456+00:00"
}
```

Driver `eta_min` uses Google Distance Matrix when `MAPS_PROVIDER=google` (falls back to haversine estimate in mock mode).

**Close codes**


| Code   | Meaning                         |
| ------ | ------------------------------- |
| `4001` | Invalid or expired token        |
| `4003` | Ride not found or not your ride |


**Client notes**

- Connect after `POST /rides` returns `id`.
- Send periodic ping messages or empty text to keep connection alive; server reads incoming text in a loop.
- Reconnect with a fresh access token if the connection drops.

---

## Typical booking flow

```text
1. POST /auth/request-otp       → OTP sent, is_new_user flag
2. POST /auth/verify-otp        → access_token, refresh_token (account auto-created if new)
3. POST /rides/quote            → all types, fares, ETAs, addresses (pickup/drop lat/lng only)
4. POST /rides                  → ride id, status searching_driver (use quote addresses)
5. WS   /ws/rides/{id}?token=... → live status events (no polling)
6. (optional) POST /rides/{id}/cancel
7. GET /rides/history           → past rides
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

**Quote ride (all types)**

```bash
curl -X POST http://localhost:8000/api/v1/rides/quote \
  -H "Content-Type: application/json" \
  -d '{
    "pickup":{"lat":"12.9716","lng":"77.5946"},
    "drop":{"lat":"12.9352","lng":"77.6245"}
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

## Driver auth

Base path: `/api/v1/driver/auth`

Uses the same request bodies and OTP response shape as rider auth (`phone` / `code`). Driver verify returns driver-specific fields in `data` (`driver_id`, `onboarding`, `profile`). A `DriverProfile` is auto-created at `step1` for new drivers. The nested `onboarding` object drives frontend routing — no separate status poll endpoint.

### `POST /driver/auth/request-otp`

**Request body**

```json
{ "phone": "+919876543210" }
```

**Response `200`**

```json
{
  "success": true,
  "message": "OTP sent",
  "data": {
    "expires_in_minutes": 10,
    "is_new_user": false,
    "debug_otp": "482910"
  }
}
```

**Errors:** `400 WRONG_ROLE` if the phone is registered as a rider.

---

### `POST /driver/auth/verify-otp`

**Request body**

```json
{
  "phone": "+919876543210",
  "code": "482910",
  "name": "Dev Driver"
}
```

Optional: `fcm_token`, `platform` (stored when push token is provided).

**Response `200`**

```json
{
  "success": true,
  "message": "Signed in successfully",
  "data": {
    "driver_id": "550e8400-e29b-41d4-a716-446655440001",
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer",
    "token_expires_in": 900,
    "is_new_driver": true,
    "onboarding": {
      "onboarding_status": "step1",
      "profile_status": false,
      "kyc_rejection_reason": null,
      "face_verification_completed": false,
      "estimated_review_time": null
    },
    "profile": {
      "name": "Dev Driver",
      "phone": "+919876543210",
      "avatar_url": null
    }
  }
}
```

`onboarding.onboarding_status` values: `step1`, `step2`, `application_submitted`, `kyc_approved`, `kyc_rejected`. `onboarding.profile_status` is `true` only when `onboarding_status` is `kyc_approved` (route to Home).

### `POST /driver/auth/refresh`

Same as rider refresh, plus `onboarding` in `data` so the app can resume routing without a status poll.

---

## Driver onboarding

Base path: `/api/v1/driver/onboarding`

**Flow:** `POST /documents` (all 4 files) → `step2` → `PATCH /vehicle` (incremental saves; auto-submits when complete) → `application_submitted` → optional `POST /face-verification` → admin approve → `kyc_approved`.

All submit endpoints use `multipart/form-data`. Each response includes an updated `onboarding` object for navigation.

### `POST /driver/onboarding/documents`

Upload all KYC documents in one request. **Auth:** Bearer driver token.

**Multipart fields:** `license`, `registration`, `insurance` (files; JPEG, PNG, or PDF; max 10 MB each).

**Precondition:** `onboarding_status` is `step1` or `kyc_rejected`.

**Response `201`:** `onboarding` (status becomes `step2`), `documents[]` with `type`, `id`, `status`, `created_at`.

### `GET /driver/onboarding/status`

Return current onboarding state for app routing. **Auth:** Bearer driver token.

**Response `200`**

```json
{
  "success": true,
  "message": "OK",
  "data": {
    "onboarding": {
      "onboarding_status": "application_submitted",
      "profile_status": false,
      "kyc_rejection_reason": null,
      "face_verification_completed": false,
      "estimated_review_time": "15 minutes"
    }
  }
}
```

### `PATCH /driver/onboarding/vehicle`

Save vehicle details, operating city, and photos incrementally. Auto-submits the application for admin review once all required fields are present. **Auth:** Bearer driver token.

**Form fields (all optional; send only what you are updating):** `vehicle_type` (`auto` | `taxi` | `cab`), `make`, `model`, `year`, `plate_number`, `color`, `city_slug` (must match an active seeded city, e.g. `bangalore`).

**File fields (optional):** `photo_front`, `photo_back`, `photo_left`, `photo_right`.

**Precondition:** documents complete (`step2` or `kyc_rejected` with all 4 docs). At least one field must be provided per request.

**Response `200`:** `onboarding`, `submitted_at` (set only when the application auto-submits; otherwise `null`).

### `POST /driver/onboarding/face-verification`

Optional face photo while application is under review. **Auth:** Bearer driver token.

**Multipart field:** `photo` (file).

**Precondition:** `onboarding_status` is `application_submitted`.

**Response `200`:** `onboarding` with `face_verification_completed: true`.

---

## Admin (internal)

Base path: `/api/v1/admin`

Protected by `X-Admin-Key` header matching `ADMIN_API_KEY` in server config. When `ADMIN_API_KEY` is unset, admin routes return `503 ADMIN_NOT_CONFIGURED`.

Used for driver KYC review after `PATCH /driver/onboarding/vehicle` auto-submits the application.

### `GET /admin/driver-applications`

List driver applications.

**Auth:** `X-Admin-Key`

**Query params:** `status` (default `application_submitted`), `page` (default 1), `limit` (default 20, max 100)

**Response `200`**

```json
{
  "success": true,
  "message": "Driver applications retrieved",
  "data": {
    "applications": [
      {
        "driver_id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Krishna",
        "phone": "+919876543210",
        "onboarding_status": "application_submitted",
        "kyc_status": "submitted",
        "vehicle_make": "Maruti",
        "vehicle_model": "Swift",
        "vehicle_plate": "KA01AB1234",
        "documents_count": 2,
        "submitted_at": "2026-06-09T10:00:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "limit": 20
  }
}
```

---

### `GET /admin/driver-applications/{driver_id}`

Application detail including presigned document view URLs (15 min TTL).

**Auth:** `X-Admin-Key`

**Errors:** `404 NOT_FOUND`

---

### `POST /admin/driver-applications/{driver_id}/approve`

Approve KYC. Sets `onboarding_status=kyc_approved`, `kyc_status=approved`, and marks all documents approved.

**Auth:** `X-Admin-Key`

**Precondition:** `onboarding_status=application_submitted` or `kyc_status=submitted`

**Errors:** `400 INVALID_STATUS`, `404 NOT_FOUND`

---

### `POST /admin/driver-applications/{driver_id}/reject`

Reject KYC with a reason.

**Auth:** `X-Admin-Key`

**Request body**

```json
{
  "reason": "License photo is unreadable"
}
```

**Errors:** `400 INVALID_STATUS`, `404 NOT_FOUND`

---

**Example: list pending applications**

```bash
curl http://localhost:8000/api/v1/admin/driver-applications \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

**Example: approve**

```bash
curl -X POST http://localhost:8000/api/v1/admin/driver-applications/{driver_id}/approve \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

---

## Changelog


| Version | Scope                        |
| ------- | ---------------------------- |
| 0.1.0   | Phase 0 + Phase 1 rider APIs |


