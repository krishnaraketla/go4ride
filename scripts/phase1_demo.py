#!/usr/bin/env python3
"""Go4Ride Phase 1 — full-stack demo (Docker, DB, API walkthrough).

Run from repo root:
  ./scripts/dev.sh demo

Or directly:
  python scripts/phase1_demo.py

Environment:
  DEMO_RESET_DB=1   Wipe Postgres volume (./scripts/dev.sh reset-db) instead of setup
  DEMO_SKIP_SETUP=1 Skip Docker / migrate / seed (API must already be up)
  DEMO_SKIP_SERVER=1  Do not auto-start uvicorn (run ./scripts/dev.sh run yourself)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import websockets

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1"
HEALTH_URL = f"{BASE_URL}/health"

DEMO_PHONE = "9876543210"
DEMO_NAME = "Phase1 Demo Rider"

PICKUP = {"lat": "12.9716", "lng": "77.5946"}
DROP = {"lat": "12.9352", "lng": "77.6245"}
RIDE_TYPE = "mini"


def run_step(label: str, cmd: list[str], *, cwd: Path = ROOT) -> None:
    print(f"\n>>> {label}")
    print(f"    {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def setup_infrastructure() -> None:
    """Notebook prerequisites: Docker + DB migrate/seed."""
    if os.environ.get("DEMO_SKIP_SETUP"):
        print("DEMO_SKIP_SETUP=1 — skipping Docker and dev.sh setup")
        return

    run_step("Docker compose down", ["docker", "compose", "down"])
    run_step("Docker compose up -d", ["docker", "compose", "up", "-d"])

    if os.environ.get("DEMO_RESET_DB"):
        run_step("Reset database", ["./scripts/dev.sh", "reset-db"])
    else:
        run_step("Dev setup (venv, migrate, seed)", ["./scripts/dev.sh", "setup"])


_server_proc: subprocess.Popen[bytes] | None = None


def stop_api_server() -> None:
    """Stop uvicorn on port 8000 (demo-spawned or already running)."""
    global _server_proc
    if _server_proc is not None and _server_proc.poll() is None:
        _server_proc.terminate()
        try:
            _server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _server_proc.kill()
        _server_proc = None

    try:
        pids = subprocess.check_output(
            ["lsof", "-ti", ":8000"],
            cwd=ROOT,
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return

    for pid in pids.splitlines():
        if pid:
            subprocess.run(["kill", pid], check=False)


def ensure_api_server(*, force_restart: bool = False) -> None:
    """Start uvicorn in the background if /health is not reachable."""
    if os.environ.get("DEMO_SKIP_SERVER"):
        require_api()
        return

    if force_restart:
        stop_api_server()
        time.sleep(1)
    else:
        try:
            with httpx.Client(timeout=3.0) as client:
                client.get(HEALTH_URL)
            print(f"\nAPI already running at {BASE_URL}")
            return
        except (httpx.ConnectError, httpx.ReadError):
            pass

    print("\n>>> Starting API (./scripts/dev.sh run) in background...")
    global _server_proc
    _server_proc = subprocess.Popen(
        ["./scripts/dev.sh", "run"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    deadline = time.monotonic() + 45.0
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=3.0) as client:
                client.get(HEALTH_URL)
            print(f"API ready at {BASE_URL}")
            return
        except (httpx.ConnectError, httpx.ReadError):
            if _server_proc.poll() is not None:
                err = _server_proc.stderr.read().decode() if _server_proc.stderr else ""
                raise SystemExit(f"uvicorn exited early:\n{err}") from None
            time.sleep(0.5)

    raise SystemExit(f"API did not become ready at {BASE_URL} within 45s")


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
            f"Cannot reach API at {BASE_URL}. Start the server:\n"
            "  ./scripts/dev.sh run"
        ) from exc


def run_api_demo() -> None:
    """Phase 1 API walkthrough (auth → ride → WebSocket cancel → stats)."""
    require_api()
    with httpx.Client(timeout=10.0) as client:
        health = assert_ok(client.get(HEALTH_URL), "health")
    pp("Health", health)

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

    auth_headers = {"Authorization": f"Bearer {access_token}"}

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

    with httpx.Client(timeout=15.0) as client:
        profile = assert_ok(
            client.get(f"{API}/profile", headers=auth_headers),
            "profile GET",
        )
        updated = assert_ok(
            client.patch(
                f"{API}/profile",
                headers=auth_headers,
                json={"name": "Phase1 Demo (updated)", "email": "phase1-demo@example.com"},
            ),
            "profile PATCH",
        )
    pp("Profile (before)", profile)
    pp("Profile (after PATCH)", updated)

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
                headers={**auth_headers, "Idempotency-Key": idempotency_key},
                json=create_body,
            ),
            "create ride",
        )
        ride_dup = assert_ok(
            client.post(
                f"{API}/rides",
                headers={**auth_headers, "Idempotency-Key": idempotency_key},
                json=create_body,
            ),
            "create ride (idempotent replay)",
        )
    ride_id = str(ride["id"])
    pp("Created ride", ride)
    assert ride["id"] == ride_dup["id"], "Idempotency-Key should return the same ride"
    print("Idempotency check: OK (same ride_id on replay)")

    with httpx.Client(timeout=15.0) as client:
        status = assert_ok(
            client.get(f"{API}/rides/{ride_id}/status", headers=auth_headers),
            "ride status",
        )
        details = assert_ok(
            client.get(f"{API}/rides/{ride_id}", headers=auth_headers),
            "ride details",
        )
        history = assert_ok(
            client.get(f"{API}/rides/history", headers=auth_headers, params={"page": 1, "limit": 5}),
            "ride history",
        )
    pp("Ride status", status)
    pp("Ride details", details)
    pp("Ride history (first page)", history)

    assert status["status"] == "searching_driver", (
        f"Phase 1 stub expects searching_driver, got {status['status']}"
    )
    print("Phase 1 lifecycle check: OK (status is searching_driver)")

    ws_url = f"ws://localhost:8000/api/v1/ws/rides/{ride_id}?token={access_token}"

    async def websocket_cancel_demo() -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        async with websockets.connect(ws_url, open_timeout=15) as ws:
            connected = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
            events.append(connected)
            print("WS connected:", connected)

            async with httpx.AsyncClient() as client:
                cancel_resp = await client.post(
                    f"{API}/rides/{ride_id}/cancel",
                    headers=auth_headers,
                    timeout=15.0,
                )
                cancel_resp.raise_for_status()
                cancelled_ride = cancel_resp.json()
                print("REST cancel:", cancelled_ride.get("status"))

            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                payload = json.loads(raw)
                events.append(payload)
                if payload.get("status") == "cancelled":
                    break
        return events

    ws_events = asyncio.run(websocket_cancel_demo())
    pp("WebSocket events", ws_events)
    assert any(e.get("status") == "cancelled" for e in ws_events), "Expected cancelled event on WS"
    print("WebSocket + Redis pub/sub check: OK")

    with httpx.Client(timeout=15.0) as client:
        stats = assert_ok(client.get(f"{API}/stats", headers=auth_headers), "stats")
    pp("Rider stats", stats)

    with httpx.Client(timeout=15.0) as client:
        logout = client.post(
            f"{API}/auth/logout",
            json={"refresh_token": refresh_token},
        )
        assert logout.status_code == 200, logout.text
    pp("Logout", logout.json())

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


def main() -> None:
    os.chdir(ROOT)
    print(f"Go4Ride Phase 1 demo — repo root: {ROOT}")

    ran_setup = not os.environ.get("DEMO_SKIP_SETUP")
    setup_infrastructure()
    ensure_api_server(force_restart=ran_setup and not os.environ.get("DEMO_SKIP_SERVER"))
    run_api_demo()


if __name__ == "__main__":
    try:
        main()
    finally:
        if _server_proc is not None and _server_proc.poll() is None:
            _server_proc.terminate()
            try:
                _server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _server_proc.kill()
