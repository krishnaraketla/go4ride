# Go4Ride API Endpoints

**Version:** 0.2.0 (Phase 0 + Phase 1 + Phase 2 — Rider app)  
**Base URL:** `http://localhost:8000` (development)  
**Prefix:** `/api/v1` for business routes

Interactive OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)

Full reference with request/response examples: [API.md](./API.md)

---

## Summary

| Area | Count | Auth |
|------|-------|------|
| Health | 1 | None |
| Auth | 6 | Mixed |
| Profile / Insights | 4 | Bearer (rider) |
| Addresses | 4 | Bearer (rider) |
| Settings | 2 | Bearer (rider) |
| Wallet / Promo / Email | 5 | Bearer (rider) |
| Payment methods | 4 | Bearer (rider) |
| Location | 1 | None |
| Fare / catalog | 2 | None |
| Rides | 8 | Bearer (rider) |
| WebSocket | 1 | Access JWT (query) |

**Total:** 37 HTTP routes + 1 WebSocket (+ `/health` outside `/api/v1`)

---

## Full endpoint table

| Area | Method | Path | Auth | Description |
|------|--------|------|------|-------------|
| Health | `GET` | `/health` | None | Liveness check |
| Auth | `POST` | `/api/v1/auth/register` | None | Send OTP for new rider |
| Auth | `POST` | `/api/v1/auth/login` | None | Send OTP for existing rider |
| Auth | `POST` | `/api/v1/auth/verify-otp` | None | Verify OTP → JWTs (`referral_code` optional on register) |
| Auth | `POST` | `/api/v1/auth/refresh` | None* | Exchange refresh token for new token pair |
| Auth | `POST` | `/api/v1/auth/logout` | None* | Revoke refresh token (body) |
| Auth | `GET` | `/api/v1/auth/me` | Bearer | Current user summary |
| Profile | `GET` | `/api/v1/profile` | Bearer (rider) | Get rider profile |
| Profile | `PATCH` | `/api/v1/profile` | Bearer (rider) | Update name, email, avatar (resets email verification if email changes) |
| Profile | `GET` | `/api/v1/stats` | Bearer (rider) | Lifetime ride stats |
| Insights | `GET` | `/api/v1/insights` | Bearer (rider) | Weekly/monthly analytics (`?period=weekly\|monthly`) |
| Addresses | `GET` | `/api/v1/addresses` | Bearer (rider) | List saved addresses (`?lat=&lng=` for distance) |
| Addresses | `POST` | `/api/v1/addresses` | Bearer (rider) | Create saved address |
| Addresses | `PATCH` | `/api/v1/addresses/{id}` | Bearer (rider) | Update saved address |
| Addresses | `DELETE` | `/api/v1/addresses/{id}` | Bearer (rider) | Delete saved address |
| Settings | `GET` | `/api/v1/settings` | Bearer (rider) | User preferences |
| Settings | `PATCH` | `/api/v1/settings` | Bearer (rider) | Update preferences |
| Wallet | `GET` | `/api/v1/wallet` | Bearer (rider) | Ride credit balance |
| Promo | `POST` | `/api/v1/promo/apply` | Bearer (rider) | Apply promo code |
| Referral | `GET` | `/api/v1/referral` | Bearer (rider) | User referral code + reward info |
| Partner | `POST` | `/api/v1/partner/interest` | Bearer (rider) | Record partner interest (stub) |
| Email | `POST` | `/api/v1/email/send-verification` | Bearer (rider) | Send email verification code |
| Email | `POST` | `/api/v1/email/verify` | Bearer (rider) | Verify email + one-time credit bonus |
| Payment | `GET` | `/api/v1/payment-methods` | Bearer (rider) | List saved cards (stub) |
| Payment | `POST` | `/api/v1/payment-methods` | Bearer (rider) | Add card metadata (stub, no PAN) |
| Payment | `PATCH` | `/api/v1/payment-methods/{id}` | Bearer (rider) | Set default card |
| Payment | `DELETE` | `/api/v1/payment-methods/{id}` | Bearer (rider) | Remove card |
| Location | `GET` | `/api/v1/location/reverse-geocode` | None | `?lat=&lng=` → formatted address |
| Fare | `GET` | `/api/v1/ride-types` | None | List ride types (mini, sedan, bike, xl) |
| Fare | `POST` | `/api/v1/rides/estimate` | None | Fare quote |
| Rides | `POST` | `/api/v1/rides` | Bearer (rider) | Create booking |
| Rides | `POST` | `/api/v1/rides/{ride_id}/cancel` | Bearer (rider) | Cancel ride |
| Rides | `POST` | `/api/v1/rides/{ride_id}/repeat` | Bearer (rider) | Prefill payload for re-booking |
| Rides | `GET` | `/api/v1/rides/{ride_id}` | Bearer (rider) | Full ride details |
| Rides | `GET` | `/api/v1/rides/{ride_id}/status` | Bearer (rider) | Lightweight status |
| Rides | `GET` | `/api/v1/rides/{ride_id}/invoice` | Bearer (rider) | Receipt / invoice stub |
| Rides | `GET` | `/api/v1/rides/history` | Bearer (rider) | Paginated history (`?status=terminal\|all\|completed\|cancelled`) |
| WebSocket | `WS` | `/api/v1/ws/rides/{ride_id}?token=` | Access JWT (query) | Live ride status events |

\*Refresh and logout take `refresh_token` in the JSON body (no `Authorization` header).

---

## Phase 2 notes

### Ride history

- Default `status=terminal` returns only `completed` and `cancelled` rides (Bookings screen).
- Each ride includes `invoice_available: true` when completed with a `final_fare`.

### Insights

`GET /api/v1/insights?period=weekly` returns `rides_count`, `total_km`, `total_spend`, `trend[]`, `comparison_pct`, and `distribution[]` by ride type.

### Credits

- Seed promo `WELCOME5` (₹5) available after `python -m app.db.seed`.
- Email verification grants `EMAIL_VERIFY_BONUS` (default ₹5) once per user.
- Referral bonus granted to referrer when a new user registers with `referral_code`.

---

## Typical booking flow

1. `POST /api/v1/auth/register` or `POST /api/v1/auth/login`
2. `POST /api/v1/auth/verify-otp` → `access_token`, `refresh_token`
3. `POST /api/v1/auth/refresh` when access token expires
4. `GET /api/v1/location/reverse-geocode` (optional)
5. `GET /api/v1/ride-types`
6. `POST /api/v1/rides/estimate`
7. `POST /api/v1/rides`
8. `WS /api/v1/ws/rides/{ride_id}?token=…`
9. `GET /api/v1/rides/history` for Bookings
10. `POST /api/v1/rides/{ride_id}/repeat` → estimate + create for “Repeat ride”
11. `POST /api/v1/auth/logout` on sign-out
