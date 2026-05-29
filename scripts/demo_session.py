"""Shared demo session and API steps for interactive demos."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
import websockets

ROOT = Path(__file__).resolve().parent.parent
SESSION_PATH = ROOT / ".demo_session.json"
BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1"
HEALTH_URL = f"{BASE_URL}/health"

DEMO_PHONE = "9876543210"
DEMO_NAME = "Go4Ride Demo Rider"
DEMO_EMAIL = "demo-rider@go4ride.example"
PICKUP = {"lat": "12.9716", "lng": "77.5946"}
DROP = {"lat": "12.9352", "lng": "77.6245"}
RIDE_TYPE = "mini"
HTTP_TIMEOUT = 30.0


@dataclass
class DemoSession:
    access_token: str | None = None
    refresh_token: str | None = None
    user_id: str | None = None
    ride_id: str | None = None
    completed_ride_id: str | None = None
    address_id: str | None = None
    payment_method_id: str | None = None
    pickup_address: str | None = None
    drop_address: str | None = None
    idempotency_key: str | None = None
    last_estimate: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def auth_headers(self) -> dict[str, str]:
        if not self.access_token:
            raise RuntimeError("Not authenticated. Run Auth first.")
        return {"Authorization": f"Bearer {self.access_token}"}

    @property
    def ws_url(self) -> str:
        if not self.ride_id or not self.access_token:
            raise RuntimeError("Need ride_id and access_token for WebSocket.")
        return f"ws://localhost:8000/api/v1/ws/rides/{self.ride_id}?token={self.access_token}"

    def summary(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "ride_id": self.ride_id,
            "authenticated": bool(self.access_token),
            "pickup_address": self.pickup_address,
            "drop_address": self.drop_address,
        }

    def save(self, path: Path = SESSION_PATH) -> None:
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = SESSION_PATH) -> DemoSession:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def require_api() -> None:
    try:
        with httpx.Client(timeout=5.0) as client:
            client.get(HEALTH_URL)
    except httpx.ConnectError as exc:
        raise SystemExit(
            f"Cannot reach API at {BASE_URL}. Start the server:\n  ./scripts/dev.sh run"
        ) from exc


def assert_ok(response: httpx.Response, step: str) -> Any:
    if response.is_error:
        body = response.json() if response.content else {}
        if isinstance(body, dict) and body.get("success") is False:
            code = (body.get("data") or {}).get("code")
            raise RuntimeError(f"[{step}] {response.status_code}: {body.get('message')} ({code})")
        raise RuntimeError(f"[{step}] {response.status_code}: {response.text}")
    body = response.json()
    if isinstance(body, dict) and "success" in body:
        if not body.get("success"):
            code = (body.get("data") or {}).get("code")
            raise RuntimeError(f"[{step}]: {body.get('message')} ({code})")
        return body.get("data")
    return body


def step_health() -> dict[str, Any]:
    require_api()
    with httpx.Client(timeout=10.0) as client:
        return assert_ok(client.get(HEALTH_URL), "health")


def step_auth(session: DemoSession) -> dict[str, Any]:
    require_api()
    with httpx.Client(timeout=15.0) as client:
        otp_resp = assert_ok(
            client.post(f"{API}/auth/request-otp", json={"phone": DEMO_PHONE}),
            "request-otp",
        )
        debug_otp = otp_resp.get("debug_otp")
        if not debug_otp:
            raise RuntimeError("No debug_otp. Set OTP_DEBUG=true in .env and restart API.")

        tokens = assert_ok(
            client.post(
                f"{API}/auth/verify-otp",
                json={
                    "phone": DEMO_PHONE,
                    "code": debug_otp,
                    # Name is only used the first time this phone signs in.
                    "name": DEMO_NAME,
                },
            ),
            "verify-otp",
        )
        session.access_token = tokens["access_token"]
        session.refresh_token = tokens.get("refresh_token")
        session.user_id = str(tokens["user_id"])

        me = assert_ok(
            client.get(f"{API}/auth/me", headers=session.auth_headers),
            "auth/me",
        )
    session.save()
    return {
        "otp": otp_resp,
        "tokens": {**tokens, "access_token": "<redacted>"},
        "me": me,
    }


def step_geocode(session: DemoSession) -> dict[str, Any]:
    require_api()
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
    session.pickup_address = pickup_addr.get(
        "formatted_address", f"Pickup {PICKUP['lat']}, {PICKUP['lng']}"
    )
    session.drop_address = drop_addr.get(
        "formatted_address", f"Drop {DROP['lat']}, {DROP['lng']}"
    )
    session.save()
    return {"pickup": pickup_addr, "drop": drop_addr}


def step_estimate(session: DemoSession) -> dict[str, Any]:
    require_api()
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
    session.last_estimate = estimate
    session.save()
    return {"ride_types": ride_types, "estimate": estimate}


def step_create_ride(session: DemoSession) -> dict[str, Any]:
    if not session.access_token:
        raise RuntimeError("Authenticate first (menu: Auth).")
    if not session.pickup_address or not session.drop_address:
        step_geocode(session)

    session.idempotency_key = session.idempotency_key or f"demo-{uuid.uuid4()}"
    body = {
        "pickup": PICKUP,
        "drop": DROP,
        "pickup_address": session.pickup_address,
        "drop_address": session.drop_address,
        "ride_type_slug": RIDE_TYPE,
    }
    with httpx.Client(timeout=60.0) as client:
        ride = assert_ok(
            client.post(
                f"{API}/rides",
                headers={**session.auth_headers, "Idempotency-Key": session.idempotency_key},
                json=body,
            ),
            "create ride",
        )
    session.ride_id = str(ride["id"])
    session.save()
    return ride


def step_ride_status(session: DemoSession) -> dict[str, Any]:
    if not session.ride_id:
        raise RuntimeError("Create a ride first.")
    with httpx.Client(timeout=15.0) as client:
        status = assert_ok(
            client.get(
                f"{API}/rides/{session.ride_id}/status",
                headers=session.auth_headers,
            ),
            "ride status",
        )
        details = assert_ok(
            client.get(
                f"{API}/rides/{session.ride_id}",
                headers=session.auth_headers,
            ),
            "ride details",
        )
    return {"status": status, "details": details}


def step_cancel(session: DemoSession) -> dict[str, Any]:
    if not session.ride_id:
        raise RuntimeError("Create a ride first.")
    with httpx.Client(timeout=15.0) as client:
        return assert_ok(
            client.post(
                f"{API}/rides/{session.ride_id}/cancel",
                headers=session.auth_headers,
            ),
            "cancel ride",
        )


async def step_ws_listen(
    session: DemoSession,
    *,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    stop_event: asyncio.Event | None = None,
) -> list[dict[str, Any]]:
    if not session.ride_id or not session.access_token:
        raise RuntimeError("Create a ride and authenticate first.")

    events: list[dict[str, Any]] = []
    async with websockets.connect(session.ws_url, open_timeout=15) as ws:
        connected = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
        events.append(connected)
        if on_event:
            on_event(connected)

        while stop_event is None or not stop_event.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            payload = json.loads(raw)
            events.append(payload)
            if on_event:
                on_event(payload)
    return events


def step_stats(session: DemoSession) -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        return assert_ok(
            client.get(f"{API}/stats", headers=session.auth_headers),
            "stats",
        )


def step_logout(session: DemoSession) -> dict[str, Any]:
    if not session.refresh_token:
        raise RuntimeError("No refresh token in session.")
    with httpx.Client(timeout=15.0) as client:
        data = assert_ok(
            client.post(
                f"{API}/auth/logout",
                json={"refresh_token": session.refresh_token},
            ),
            "logout",
        )
    session.access_token = None
    session.refresh_token = None
    session.save()
    return data


def step_refresh(session: DemoSession) -> dict[str, Any]:
    if not session.refresh_token:
        raise RuntimeError("Authenticate first.")
    with httpx.Client(timeout=15.0) as client:
        tokens = assert_ok(
            client.post(f"{API}/auth/refresh", json={"refresh_token": session.refresh_token}),
            "auth/refresh",
        )
    session.access_token = tokens["access_token"]
    session.refresh_token = tokens["refresh_token"]
    session.save()
    return {**tokens, "access_token": "<redacted>", "refresh_token": "<redacted>"}


def step_profile(session: DemoSession) -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        before = assert_ok(client.get(f"{API}/profile", headers=session.auth_headers), "profile GET")
        after = assert_ok(
            client.patch(
                f"{API}/profile",
                headers=session.auth_headers,
                json={"name": f"{DEMO_NAME} (updated)", "email": DEMO_EMAIL},
            ),
            "profile PATCH",
        )
    return {"before": before, "after": after}


def step_insights(session: DemoSession, period: str = "weekly") -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        weekly = assert_ok(
            client.get(f"{API}/insights", headers=session.auth_headers, params={"period": period}),
            "insights",
        )
        monthly = assert_ok(
            client.get(f"{API}/insights", headers=session.auth_headers, params={"period": "monthly"}),
            "insights monthly",
        )
    return {"weekly": weekly, "monthly": monthly}


def step_addresses(session: DemoSession) -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        created = assert_ok(
            client.post(
                f"{API}/addresses",
                headers=session.auth_headers,
                json={
                    "label": "Home",
                    "address_line": "742 Demo Street, Bangalore",
                    "lat": PICKUP["lat"],
                    "lng": PICKUP["lng"],
                    "is_default": True,
                },
            ),
            "addresses POST",
        )
        session.address_id = str(created["id"])
        listed = assert_ok(
            client.get(
                f"{API}/addresses",
                headers=session.auth_headers,
                params={"lat": PICKUP["lat"], "lng": PICKUP["lng"]},
            ),
            "addresses GET",
        )
    session.save()
    return {"created": created, "listed": listed}


def step_settings(session: DemoSession) -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        current = assert_ok(client.get(f"{API}/settings", headers=session.auth_headers), "settings GET")
        updated = assert_ok(
            client.patch(
                f"{API}/settings",
                headers=session.auth_headers,
                json={"notifications_enabled": False, "language": "en"},
            ),
            "settings PATCH",
        )
    return {"before": current, "after": updated}


def step_wallet(session: DemoSession) -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        return assert_ok(client.get(f"{API}/wallet", headers=session.auth_headers), "wallet")


def step_promo(session: DemoSession, code: str = "WELCOME5") -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        return assert_ok(
            client.post(f"{API}/promo/apply", headers=session.auth_headers, json={"code": code}),
            "promo/apply",
        )


def step_referral(session: DemoSession) -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        return assert_ok(client.get(f"{API}/referral", headers=session.auth_headers), "referral")


def step_email_verify(session: DemoSession) -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        sent = assert_ok(
            client.post(f"{API}/email/send-verification", headers=session.auth_headers),
            "email/send-verification",
        )
        debug_code = sent.get("debug_code")
        if not debug_code:
            raise RuntimeError("No debug_code. Set OTP_DEBUG=true in .env.")
        verified = assert_ok(
            client.post(
                f"{API}/email/verify",
                headers=session.auth_headers,
                json={"code": debug_code},
            ),
            "email/verify",
        )
        wallet = assert_ok(client.get(f"{API}/wallet", headers=session.auth_headers), "wallet")
    return {"sent": sent, "verified": verified, "wallet": wallet}


def step_payment_methods(session: DemoSession) -> dict[str, Any]:
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        listed = assert_ok(
            client.get(f"{API}/payment-methods", headers=session.auth_headers),
            "payment-methods GET",
        )
        existing = next((c for c in listed if c.get("last4") == "4242"), None)
        if existing:
            session.payment_method_id = str(existing["id"])
            session.save()
            return {"note": "Using existing card", "listed": listed}

        created = assert_ok(
            client.post(
                f"{API}/payment-methods",
                headers=session.auth_headers,
                json={
                    "brand": "VISA",
                    "last4": "4242",
                    "exp_month": 12,
                    "exp_year": 2026,
                    "is_default": not listed,
                },
            ),
            "payment-methods POST",
        )
        session.payment_method_id = str(created["id"])
        listed = assert_ok(
            client.get(f"{API}/payment-methods", headers=session.auth_headers),
            "payment-methods GET",
        )
    session.save()
    return {"created": created, "listed": listed}


def step_history(session: DemoSession, status: str = "terminal") -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        terminal = assert_ok(
            client.get(
                f"{API}/rides/history",
                headers=session.auth_headers,
                params={"status": status, "limit": 5},
            ),
            "rides/history",
        )
        completed = assert_ok(
            client.get(
                f"{API}/rides/history",
                headers=session.auth_headers,
                params={"status": "completed", "limit": 5},
            ),
            "rides/history completed",
        )
    return {"terminal": terminal, "completed": completed}


def step_repeat(session: DemoSession) -> dict[str, Any]:
    ride_id = session.completed_ride_id or session.ride_id
    if not ride_id:
        raise RuntimeError("Complete a ride first (menu: Create ride + WS or full demo).")
    with httpx.Client(timeout=15.0) as client:
        return assert_ok(
            client.post(f"{API}/rides/{ride_id}/repeat", headers=session.auth_headers),
            "rides/repeat",
        )


def step_invoice(session: DemoSession) -> dict[str, Any]:
    ride_id = session.completed_ride_id or session.ride_id
    if not ride_id:
        raise RuntimeError("Need a completed ride for invoice demo.")
    with httpx.Client(timeout=15.0) as client:
        return assert_ok(
            client.get(f"{API}/rides/{ride_id}/invoice", headers=session.auth_headers),
            "rides/invoice",
        )


def step_cancel_demo_ride(session: DemoSession) -> dict[str, Any]:
    """Create a ride and cancel immediately via REST (no full WS lifecycle wait)."""
    if not session.access_token:
        raise RuntimeError("Authenticate first.")
    if not session.pickup_address or not session.drop_address:
        step_geocode(session)

    body = {
        "pickup": PICKUP,
        "drop": DROP,
        "pickup_address": session.pickup_address,
        "drop_address": session.drop_address,
        "ride_type_slug": RIDE_TYPE,
    }
    with httpx.Client(timeout=30.0) as client:
        ride = assert_ok(
            client.post(
                f"{API}/rides",
                headers={**session.auth_headers, "Idempotency-Key": f"demo-cancel-{uuid.uuid4()}"},
                json=body,
            ),
            "create ride (cancel demo)",
        )
        # Cancel before mock driver assign delay (default 1–2s in demo server env).
        cancelled = assert_ok(
            client.post(
                f"{API}/rides/{ride['id']}/cancel",
                headers=session.auth_headers,
            ),
            "cancel ride",
        )
    return {"created": ride, "cancelled": cancelled}


def step_partner_interest(session: DemoSession) -> dict[str, Any]:
    with httpx.Client(timeout=15.0) as client:
        return assert_ok(
            client.post(
                f"{API}/partner/interest",
                headers=session.auth_headers,
                json={"message": "Interested in partner program (demo)"},
            ),
            "partner/interest",
        )
