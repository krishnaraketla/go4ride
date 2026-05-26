"""OpenAPI / Swagger metadata and schema customization."""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.config import Settings

OPENAPI_TAGS = [
    {
        "name": "health",
        "description": "Service liveness (outside `/api/v1`).",
    },
    {
        "name": "auth",
        "description": "Phone OTP login, JWT refresh, and logout. Use **Authorize** with the `access_token` from verify-otp.",
    },
    {
        "name": "profile",
        "description": "Rider profile and lifetime ride statistics.",
    },
    {
        "name": "insights",
        "description": "Weekly and monthly ride analytics for the rider home screen.",
    },
    {
        "name": "addresses",
        "description": "Saved pickup/drop addresses (max 10 per user).",
    },
    {
        "name": "settings",
        "description": "Notification and app preferences.",
    },
    {
        "name": "wallet",
        "description": "Ride credit balance.",
    },
    {
        "name": "promo",
        "description": "Promo codes, referral rewards, and partner interest (stub).",
    },
    {
        "name": "email",
        "description": "Email verification and one-time credit bonus.",
    },
    {
        "name": "payment-methods",
        "description": "Saved card metadata (stub — no PAN storage).",
    },
    {
        "name": "location",
        "description": "Reverse geocoding for map pins.",
    },
    {
        "name": "rides",
        "description": "Fare estimates, booking lifecycle, history, invoices, and repeat ride.",
    },
    {
        "name": "websocket",
        "description": "Live ride status over WebSocket (not listed below — connect manually).",
    },
]

OPENAPI_DESCRIPTION = """
Ride-hailing **rider app** API (Phase 0–2). Driver and admin APIs are out of scope for this service.

## Authentication

1. `POST /api/v1/auth/request-otp` — send OTP to phone (`debug_otp` returned when `OTP_DEBUG=true`)
2. `POST /api/v1/auth/verify-otp` — exchange OTP for JWT pair; creates account on first sign-in
3. Click **Authorize** and paste the `access_token` (Bearer, no prefix)
4. `POST /api/v1/auth/refresh` — new token pair using `refresh_token` in body (no header)

## Typical booking flow

1. Reverse geocode (optional) → list ride types → estimate fare
2. `POST /api/v1/rides` with optional `Idempotency-Key` header
3. `WS /api/v1/ws/rides/{ride_id}?token={access_token}` for live updates
4. Cancel, history, repeat, or fetch invoice as needed

## WebSocket

```
WS /api/v1/ws/rides/{ride_id}?token=<access_token>
```

Events are JSON payloads published on ride status changes (mock driver advances stages in dev).

## Errors

Structured JSON errors: `{"detail": "...", "code": "..."}` with HTTP 4xx/5xx.
"""


def get_openapi_servers(settings: Settings) -> list[dict[str, str]]:
    """Build OpenAPI server list so Swagger calls the deployed host, not localhost."""
    explicit = settings.public_base_url or settings.render_external_url
    if explicit:
        url = explicit.rstrip("/")
        return [{"url": url, "description": "Current deployment"}]
    if settings.app_env == "development":
        return [{"url": "http://localhost:8000", "description": "Local development"}]
    # Same-origin fallback when no public URL env is set.
    return [{"url": "/", "description": "Current host"}]


def configure_openapi(app: FastAPI, settings: Settings) -> None:
    """Attach a customized OpenAPI schema generator to the FastAPI app."""

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=OPENAPI_TAGS,
            servers=get_openapi_servers(settings),
        )

        schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
        if "HTTPBearer" in schemes:
            bearer = schemes.pop("HTTPBearer")
            bearer["description"] = (
                "JWT access token from `POST /api/v1/auth/verify-otp`. "
                "Paste the token only (Swagger adds the Bearer prefix)."
            )
            schemes["BearerAuth"] = bearer

            for path_item in schema.get("paths", {}).values():
                for operation in path_item.values():
                    if not isinstance(operation, dict):
                        continue
                    security = operation.get("security")
                    if not security:
                        continue
                    operation["security"] = [
                        {"BearerAuth": item["HTTPBearer"]} if "HTTPBearer" in item else item
                        for item in security
                    ]

        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi
