# Go4Ride API Endpoints

**Version:** 0.1.0 (Phase 0 + Phase 1 — Rider app)  
**Base URL:** `http://localhost:8000` (development)  
**Prefix:** `/api/v1` for business routes

Interactive OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)

Full reference with request/response examples: [API.md](./API.md)

---

## Summary

| Area | Count | Auth |
|------|-------|------|
| Health | 1 | None |
| Auth | 5 | Mixed |
| Profile | 3 | Bearer (rider) |
| Location | 1 | None |
| Fare / catalog | 2 | None |
| Rides | 5 | Bearer (rider) |
| WebSocket | 1 | Access JWT (query) |

**Total:** 17 HTTP routes + 1 WebSocket (+ `/health` outside `/api/v1`)

---

## Full endpoint table

| Area | Method | Path | Auth | Description |
|------|--------|------|------|-------------|
| Health | `GET` | `/health` | None | Liveness check |
| Auth | `POST` | `/api/v1/auth/register` | None | Send OTP for new rider |
| Auth | `POST` | `/api/v1/auth/login` | None | Send OTP for existing rider |
| Auth | `POST` | `/api/v1/auth/verify-otp` | None | Verify OTP → `access_token` + `refresh_token` |
| Auth | `POST` | `/api/v1/auth/logout` | None* | Revoke refresh token (body) |
| Auth | `GET` | `/api/v1/auth/me` | Bearer | Current user (id, phone, name, role) |
| Profile | `GET` | `/api/v1/profile` | Bearer (rider) | Get rider profile |
| Profile | `PATCH` | `/api/v1/profile` | Bearer (rider) | Update name, email, avatar |
| Profile | `GET` | `/api/v1/stats` | Bearer (rider) | Ride stats (total rides, spend, etc.) |
| Location | `GET` | `/api/v1/location/reverse-geocode` | None | `?lat=&lng=` → formatted address |
| Fare / catalog | `GET` | `/api/v1/ride-types` | None | List active ride types (mini, sedan) |
| Fare | `POST` | `/api/v1/rides/estimate` | None | Fare quote (distance, duration, estimated fare) |
| Rides | `POST` | `/api/v1/rides` | Bearer (rider) | Create booking |
| Rides | `POST` | `/api/v1/rides/{ride_id}/cancel` | Bearer (rider) | Cancel until `in_progress` (through `driver_arrived`) |
| Rides | `GET` | `/api/v1/rides/{ride_id}` | Bearer (rider) | Full ride details |
| Rides | `GET` | `/api/v1/rides/{ride_id}/status` | Bearer (rider) | Lightweight status |
| Rides | `GET` | `/api/v1/rides/history` | Bearer (rider) | Paginated history (`?page=&limit=`) |
| WebSocket | `WS` | `/api/v1/ws/rides/{ride_id}?token=` | Access JWT (query) | Live ride status events |

\*Logout does not use `Authorization`; it takes `refresh_token` in the JSON body.

---

## Auth API

Base path: `/api/v1/auth`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/auth/register` | None | Send OTP for registration |
| `POST` | `/api/v1/auth/login` | None | Send OTP for login |
| `POST` | `/api/v1/auth/verify-otp` | None | Verify OTP, issue JWTs, create user on register |
| `POST` | `/api/v1/auth/logout` | None* | Revoke refresh token |
| `GET` | `/api/v1/auth/me` | Bearer | Authenticated user summary |

### Token pair

| Token | Lifetime (default) | Use |
|-------|-------------------|-----|
| `access_token` | 15 minutes | API requests + WebSocket `token` query param |
| `refresh_token` | 7 days | Returned on verify-otp; send to logout to revoke |

---

## Profile API

Base path: `/api/v1`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/profile` | Bearer (rider) | Get profile |
| `PATCH` | `/api/v1/profile` | Bearer (rider) | Update profile |
| `GET` | `/api/v1/stats` | Bearer (rider) | Rider statistics |

---

## Location API

Base path: `/api/v1/location`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/location/reverse-geocode` | None | Coordinates → address (`lat`, `lng` query params) |

---

## Fare API

There is no `/fare` prefix. Fare and catalog routes live under `/api/v1`:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/ride-types` | None | Vehicle types for booking UI |
| `POST` | `/api/v1/rides/estimate` | None | Pre-booking fare estimate |

---

## Rides API

Base path: `/api/v1`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/rides` | Bearer (rider) | Create ride (optional `Idempotency-Key` header) |
| `POST` | `/api/v1/rides/{ride_id}/cancel` | Bearer (rider) | Cancel ride |
| `GET` | `/api/v1/rides/{ride_id}` | Bearer (rider) | Ride details |
| `GET` | `/api/v1/rides/{ride_id}/status` | Bearer (rider) | Current status only |
| `GET` | `/api/v1/rides/history` | Bearer (rider) | Paginated ride list |

### Ride status (Phase 1.5 mock in dev)

```
requested → searching_driver → driver_assigned → driver_arrived → in_progress → completed
                            ↘ cancelled (rider cancel, until in_progress)
```

With `MOCK_DRIVER_ENABLED=true` (default in development), transitions after `searching_driver` run automatically. Cancellable through `driver_arrived`.

---

## WebSocket

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `WS` | `/api/v1/ws/rides/{ride_id}?token=<access_token>` | Access JWT | Real-time ride status events |

---

## Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Service liveness (not under `/api/v1`) |

---

## Not implemented

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/api/v1/auth/refresh` | Refresh token issued on login but no refresh endpoint yet; re-login via OTP when access expires |

---

## Typical booking flow

1. `POST /api/v1/auth/register` or `POST /api/v1/auth/login`
2. `POST /api/v1/auth/verify-otp` → `access_token`, `refresh_token`
3. `GET /api/v1/location/reverse-geocode` (optional, for addresses)
4. `GET /api/v1/ride-types`
5. `POST /api/v1/rides/estimate`
6. `POST /api/v1/rides` (with `Authorization: Bearer …`)
7. `WS /api/v1/ws/rides/{ride_id}?token=…` for live updates
8. `GET /api/v1/rides/{ride_id}/status` or `GET /api/v1/rides/{ride_id}` as needed
9. `POST /api/v1/rides/{ride_id}/cancel` (if cancelling)
10. `POST /api/v1/auth/logout` on sign-out
