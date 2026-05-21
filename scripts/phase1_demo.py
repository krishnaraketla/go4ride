# %% [markdown]
# # Go4Ride Phase 1 — Interactive demo
#
# Run cell-by-cell in VS Code / Cursor (Python: Run Cell) or Jupyter after converting.
#
# **Prerequisites** (from repo root; use Python 3.11+ project venv, not conda mlp):
# ```bash
# conda deactivate
# ./scripts/dev.sh setup
# ./scripts/dev.sh run          # separate terminal
# ./scripts/dev.sh demo         # or run this file
# ```

# %% Setup
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from typing import Any

import httpx

BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1"
HEALTH_URL = f"{BASE_URL}/health"

# Re-run safe: use login if phone already registered
DEMO_PHONE = "9876543210"
DEMO_NAME = "Phase1 Demo Rider"

# Bangalore-ish coordinates (mock maps uses haversine)
PICKUP = {"lat": "12.9716", "lng": "77.5946"}
DROP = {"lat": "12.9352", "lng": "77.6245"}
RIDE_TYPE = "mini"


def pp(label: str, data: Any) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(data, indent=2, default=str))


def assert_ok(response: httpx.Response, step: str) -> dict[str, Any]:
    if response.is_error:
        print(f"FAILED [{step}] {response.status_code}: {response.text}", file=sys.stderr)
        response.raise_for_status()
    return response.json()


def require_api() -> None:
    try:
        with httpx.Client(timeout=5.0) as client:
            client.get(HEALTH_URL)
    except httpx.ConnectError as exc:
        raise SystemExit(
            f"Cannot reach API at {BASE_URL}. Start dependencies and the server:\n"
            "  docker compose up -d && alembic upgrade head && python -m app.db.seed\n"
            "  uvicorn app.main:app --reload --port 8000"
        ) from exc


# %% 0. Health check
require_api()
with httpx.Client(timeout=10.0) as client:
    health = assert_ok(client.get(HEALTH_URL), "health")
pp("Health", health)

# %% 1. Authentication — OTP register/login + verify
access_token: str
refresh_token: str
user_id: str

with httpx.Client(timeout=15.0) as client:
    reg = client.post(
        f"{API}/auth/register",
        json={"phone": DEMO_PHONE, "name": DEMO_NAME},
    )
    if reg.status_code == 409:
        pp("Auth", {"note": "Phone exists — using login", "code": reg.json().get("code")})
        otp_resp = assert_ok(
            client.post(f"{API}/auth/login", json={"phone": DEMO_PHONE}),
            "login",
        )
        purpose = "login"
    else:
        otp_resp = assert_ok(reg, "register")
        purpose = "register"

    debug_otp = otp_resp.get("debug_otp")
    if not debug_otp:
        raise RuntimeError(
            "No debug_otp in response. Set OTP_DEBUG=true in .env and restart the API."
        )
    pp("OTP sent", otp_resp)

    tokens = assert_ok(
        client.post(
            f"{API}/auth/verify-otp",
            json={
                "phone": DEMO_PHONE,
                "code": debug_otp,
                "purpose": purpose,
                "name": DEMO_NAME if purpose == "register" else None,
            },
        ),
        "verify-otp",
    )
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    user_id = str(tokens["user_id"])
    pp("Tokens", {**tokens, "access_token": "<redacted>", "refresh_token": "<redacted>"})

    me = assert_ok(
        client.get(
            f"{API}/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        ),
        "auth/me",
    )
    pp("Auth /me", me)

AUTH_HEADERS = {"Authorization": f"Bearer {access_token}"}

# %% 2. Location — reverse geocode pickup & drop
with httpx.Client(timeout=15.0) as client:
    pickup_addr = assert_ok(
        client.get(
            f"{API}/location/reverse-geocode",
            params={"lat": PICKUP["lat"], "lng": PICKUP["lng"]},
        ),
        "reverse-geocode pickup",
    )
    drop_addr = assert_ok(
        client.get(
            f"{API}/location/reverse-geocode",
            params={"lat": DROP["lat"], "lng": DROP["lng"]},
        ),
        "reverse-geocode drop",
    )
pp("Pickup address", pickup_addr)
pp("Drop address", drop_addr)

pickup_address = pickup_addr.get(
    "formatted_address", f"Pickup {PICKUP['lat']}, {PICKUP['lng']}"
)
drop_address = drop_addr.get("formatted_address", f"Drop {DROP['lat']}, {DROP['lng']}")

# %% 3. Ride types & fare estimate
with httpx.Client(timeout=15.0) as client:
    ride_types = assert_ok(client.get(f"{API}/ride-types"), "ride-types")
    estimate = assert_ok(
        client.post(
            f"{API}/rides/estimate",
            json={
                "pickup": PICKUP,
                "drop": DROP,
                "ride_type_slug": RIDE_TYPE,
            },
        ),
        "rides/estimate",
    )
pp("Ride types", ride_types)
pp("Fare estimate", estimate)

# %% 4. Profile — GET & PATCH
with httpx.Client(timeout=15.0) as client:
    profile = assert_ok(
        client.get(f"{API}/profile", headers=AUTH_HEADERS),
        "profile GET",
    )
    updated = assert_ok(
        client.patch(
            f"{API}/profile",
            headers=AUTH_HEADERS,
            json={"name": "Phase1 Demo (updated)", "email": "phase1-demo@example.com"},
        ),
        "profile PATCH",
    )
pp("Profile (before)", profile)
pp("Profile (after PATCH)", updated)

# %% 5. Create ride (+ idempotency key)
ride_id: str
idempotency_key = f"demo-{uuid.uuid4()}"

create_body = {
    "pickup": PICKUP,
    "drop": DROP,
    "pickup_address": pickup_address,
    "drop_address": drop_address,
    "ride_type_slug": RIDE_TYPE,
}

with httpx.Client(timeout=20.0) as client:
    ride = assert_ok(
        client.post(
            f"{API}/rides",
            headers={**AUTH_HEADERS, "Idempotency-Key": idempotency_key},
            json=create_body,
        ),
        "create ride",
    )
    ride_dup = assert_ok(
        client.post(
            f"{API}/rides",
            headers={**AUTH_HEADERS, "Idempotency-Key": idempotency_key},
            json=create_body,
        ),
        "create ride (idempotent replay)",
    )
ride_id = str(ride["id"])
pp("Created ride", ride)
assert ride["id"] == ride_dup["id"], "Idempotency-Key should return the same ride"
print("Idempotency check: OK (same ride_id on replay)")

# %% 6. Ride status, details & history
with httpx.Client(timeout=15.0) as client:
    status = assert_ok(
        client.get(f"{API}/rides/{ride_id}/status", headers=AUTH_HEADERS),
        "ride status",
    )
    details = assert_ok(
        client.get(f"{API}/rides/{ride_id}", headers=AUTH_HEADERS),
        "ride details",
    )
    history = assert_ok(
        client.get(f"{API}/rides/history", headers=AUTH_HEADERS, params={"page": 1, "limit": 5}),
        "ride history",
    )
pp("Ride status", status)
pp("Ride details", details)
pp("Ride history (first page)", history)

assert status["status"] == "searching_driver", (
    f"Phase 1 stub expects searching_driver, got {status['status']}"
)
print("Phase 1 lifecycle check: OK (status is searching_driver)")

# %% 7. WebSocket — receive live event on cancel
WS_URL = f"ws://localhost:8000/api/v1/ws/rides/{ride_id}?token={access_token}"


async def websocket_cancel_demo() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    async with httpx.AsyncClient() as client:
        async with client.websocket_connect(WS_URL, timeout=15.0) as ws:
            connected = json.loads(await ws.receive_text())
            events.append(connected)
            print("WS connected:", connected)

            # Cancel triggers Redis publish → WS subscribers
            cancel_resp = await client.post(
                f"{API}/rides/{ride_id}/cancel",
                headers=AUTH_HEADERS,
                timeout=15.0,
            )
            cancel_resp.raise_for_status()
            cancelled_ride = cancel_resp.json()
            print("REST cancel:", cancelled_ride.get("status"))

            # Wait for status event (skip Redis protocol noise)
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=5.0)
                payload = json.loads(raw)
                events.append(payload)
                if payload.get("status") == "cancelled":
                    break

    return events


ws_events = asyncio.run(websocket_cancel_demo())
pp("WebSocket events", ws_events)
assert any(e.get("status") == "cancelled" for e in ws_events), "Expected cancelled event on WS"
print("WebSocket + Redis pub/sub check: OK")

# %% 8. Rider stats
with httpx.Client(timeout=15.0) as client:
    stats = assert_ok(client.get(f"{API}/stats", headers=AUTH_HEADERS), "stats")
pp("Rider stats", stats)

# %% 9. Logout
with httpx.Client(timeout=15.0) as client:
    logout = client.post(
        f"{API}/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout.status_code == 200, logout.text
pp("Logout", logout.json())

# %% Summary
print(
    f"""
Phase 1 demo completed successfully.

  User ID     : {user_id}
  Ride ID     : {ride_id}
  Final status: cancelled (via REST + WS)

Endpoints exercised:
  GET  /health
  POST /api/v1/auth/register|login, verify-otp, logout
  GET  /api/v1/auth/me
  GET  /api/v1/location/reverse-geocode
  GET  /api/v1/ride-types
  POST /api/v1/rides/estimate
  GET/PATCH /api/v1/profile
  POST /api/v1/rides (+ Idempotency-Key)
  GET  /api/v1/rides/{{id}}/status, /rides/{{id}}, /rides/history
  WS   /api/v1/ws/rides/{{id}}
  GET  /api/v1/stats
"""
)
