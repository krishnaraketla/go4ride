#!/usr/bin/env python3
"""Go4Ride full-stack demo (Docker, DB, API walkthrough).

Run from repo root:
  ./scripts/dev.sh demo

Or directly:
  python scripts/demo.py

Environment:
  DEMO_RESET_DB=1     Wipe Postgres volume (./scripts/dev.sh reset-db) instead of setup
  DEMO_SKIP_SETUP=1   Skip Docker / migrate / seed (API must already be up)
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

# Allow imports from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_session import (  # noqa: E402
    API,
    DEMO_EMAIL,
    DEMO_NAME,
    DEMO_PHONE,
    DROP,
    HEALTH_URL,
    PICKUP,
    RIDE_TYPE,
    BASE_URL,
    DemoSession,
    step_addresses,
    step_email_verify,
    step_history,
    step_insights,
    step_invoice,
    step_partner_interest,
    step_payment_methods,
    step_profile,
    step_promo,
    step_referral,
    step_refresh,
    step_settings,
    step_cancel_demo_ride,
    step_logout,
    step_repeat,
    step_stats,
    step_wallet,
)

ROOT = Path(__file__).resolve().parent.parent


def run_step(label: str, cmd: list[str], *, cwd: Path = ROOT) -> None:
    print(f"\n>>> {label}")
    print(f"    {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def setup_infrastructure() -> None:
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
    server_env = os.environ.copy()
    # Faster mock lifecycle keeps the automated demo under ~30s per ride.
    server_env.setdefault("MOCK_DRIVER_ASSIGN_DELAY_SEC", "1")
    server_env.setdefault("MOCK_DRIVER_STEP_DELAY_SEC", "2")
    server_env.setdefault("SQLALCHEMY_ECHO", "false")
    _server_proc = subprocess.Popen(
        ["./scripts/dev.sh", "run"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=server_env,
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


def _logout(session: DemoSession) -> dict[str, Any]:
    return step_logout(session)


def safe_step(label: str, fn, session: DemoSession | None = None) -> bool:
    """Run a demo step; return False if it failed (demo continues)."""
    try:
        result = fn(session) if session is not None else fn()
        pp(label, result)
        return True
    except Exception as exc:
        pp(label, {"skipped": str(exc)})
        return False


def assert_ok(response: httpx.Response, step: str) -> Any:
    if response.is_error:
        print(f"FAILED [{step}] {response.status_code}: {response.text}", file=sys.stderr)
        response.raise_for_status()
    body = response.json()
    if isinstance(body, dict) and "success" in body:
        if not body.get("success"):
            response.raise_for_status()
        return body.get("data")
    return body


def require_api() -> None:
    try:
        with httpx.Client(timeout=5.0) as client:
            client.get(HEALTH_URL)
    except httpx.ConnectError as exc:
        raise SystemExit(
            f"Cannot reach API at {BASE_URL}. Start the server:\n  ./scripts/dev.sh run"
        ) from exc


def run_api_demo() -> None:
    """Auth → ride lifecycle → profile, bookings, insights, wallet, and more."""
    require_api()
    session = DemoSession()

    with httpx.Client(timeout=10.0) as client:
        health = assert_ok(client.get(HEALTH_URL), "health")
    pp("Health", health)

    with httpx.Client(timeout=15.0) as client:
        otp_resp = assert_ok(
            client.post(f"{API}/auth/request-otp", json={"phone": DEMO_PHONE}),
            "request-otp",
        )
        debug_otp = otp_resp.get("debug_otp")
        if not debug_otp:
            raise RuntimeError("No debug_otp. Set OTP_DEBUG=true in .env and restart the API.")
        pp("OTP sent", otp_resp)

        tokens = assert_ok(
            client.post(
                f"{API}/auth/verify-otp",
                json={
                    "phone": DEMO_PHONE,
                    "code": debug_otp,
                    # Name is only persisted on the first sign-in for this phone.
                    "name": DEMO_NAME,
                },
            ),
            "verify-otp",
        )
    session.access_token = tokens["access_token"]
    session.refresh_token = tokens["refresh_token"]
    session.user_id = str(tokens["user_id"])
    pp("Tokens", {**tokens, "access_token": "<redacted>", "refresh_token": "<redacted>"})

    pp("Auth refresh", step_refresh(session))

    with httpx.Client(timeout=15.0) as client:
        me = assert_ok(
            client.get(f"{API}/auth/me", headers=session.auth_headers),
            "auth/me",
        )
    pp("Auth /me", me)

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
    session.pickup_address = pickup_addr.get("formatted_address", "Pickup")
    session.drop_address = drop_addr.get("formatted_address", "Drop")
    pp("Geocode", {"pickup": pickup_addr, "drop": drop_addr})

    with httpx.Client(timeout=15.0) as client:
        quote = assert_ok(
            client.post(
                f"{API}/rides/quote",
                json={"pickup": PICKUP, "drop": DROP},
            ),
            "rides/quote",
        )
    session.pickup_address = quote.get("pickup_address", session.pickup_address)
    session.drop_address = quote.get("drop_address", session.drop_address)
    pp("Ride quote", quote)

    pp("Profile", step_profile(session))
    pp("Insights", step_insights(session))
    pp("Addresses", step_addresses(session))
    pp("Settings", step_settings(session))
    pp("Referral", step_referral(session))
    pp("Partner interest", step_partner_interest(session))

    # Cancel demo before lifecycle so we do not stack two mock-driver background runs.
    cancel_id = "—"
    if os.environ.get("DEMO_SKIP_CANCEL"):
        pp("Cancel ride (REST)", {"skipped": "DEMO_SKIP_CANCEL=1"})
    else:
        try:
            cancel_result = step_cancel_demo_ride(session)
            cancel_id = str(cancel_result["cancelled"]["id"])
            pp("Cancel ride (REST)", cancel_result)
        except Exception as exc:
            pp("Cancel ride (REST)", {"skipped": str(exc)})

    create_body = {
        "pickup": PICKUP,
        "drop": DROP,
        "pickup_address": session.pickup_address,
        "drop_address": session.drop_address,
        "ride_type_slug": RIDE_TYPE,
    }
    idempotency_key = f"demo-{uuid.uuid4()}"

    with httpx.Client(timeout=60.0) as client:
        ride = assert_ok(
            client.post(
                f"{API}/rides",
                headers={**session.auth_headers, "Idempotency-Key": idempotency_key},
                json=create_body,
            ),
            "create ride",
        )
    session.ride_id = str(ride["id"])
    pp("Created ride", ride)

    ws_url = f"ws://localhost:8000/api/v1/ws/rides/{session.ride_id}?token={session.access_token}"

    async def websocket_lifecycle_demo() -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        async with websockets.connect(ws_url, open_timeout=15) as ws:
            connected = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
            events.append(connected)
            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=8.0)
                payload = json.loads(raw)
                events.append(payload)
                print("WS event:", payload.get("status"), payload.get("message"))
                if payload.get("status") == "completed":
                    break
        return events

    ws_events = asyncio.run(websocket_lifecycle_demo())
    pp("WebSocket lifecycle", ws_events)
    session.completed_ride_id = session.ride_id
    session.save()

    pp("Ride history", step_history(session))
    pp("Repeat ride payload", step_repeat(session))
    pp("Invoice", step_invoice(session))

    safe_step("Lifetime stats", step_stats, session)
    safe_step("Promo apply", step_promo, session)
    safe_step("Email verify", step_email_verify, session)
    safe_step("Wallet", step_wallet, session)
    safe_step("Payment methods", step_payment_methods, session)

    if session.refresh_token:
        safe_step(
            "Logout",
            lambda s: _logout(s),
            session,
        )

    print(
        f"""
Go4Ride demo completed.

  User ID          : {session.user_id}
  Completed ride   : {session.completed_ride_id}
  Cancel ride      : {cancel_id}
  Demo phone       : {DEMO_PHONE}
  Demo email       : {DEMO_EMAIL}

Covers: auth (incl. refresh), profile, insights, addresses, settings,
wallet, promo, referral, email verify, payment methods, rides, history,
repeat, invoice, WebSocket lifecycle, stats, logout.
"""
    )


def main() -> None:
    os.chdir(ROOT)
    print(f"Go4Ride demo — repo root: {ROOT}")

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
