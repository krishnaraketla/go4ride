#!/usr/bin/env python3
"""Smoke-test a Google Maps API key against the GCP APIs enabled for Go4Ride.

Usage:
  export MAPS_API_KEY=your-key
  python scripts/test_google_maps_key.py

  python scripts/test_google_maps_key.py --key YOUR_KEY

Reads MAPS_API_KEY from the environment, or from .env in the repo root if unset.

Tests only these GCP-selected APIs:
  1. Geocoding API
  2. Maps SDK for Android        (SKIP — client SDK)
  3. Maps SDK for iOS            (SKIP — client SDK)
  4. Places API                  (legacy Nearby Search)
  5. Places API (New)            (searchNearby)
  6. Routes API                  (computeRoutes)
  7. Distance Matrix API
  8. Directions API

Use a server key (no app restriction) for HTTP checks. Mobile SDK keys should be
restricted separately by package/bundle ID + certificate fingerprint.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]

# San Francisco coords used in tests/docs (reverse-geocode, quote, ETA).
PICKUP_LAT, PICKUP_LNG = 37.7749, -122.4194
DROP_LAT, DROP_LNG = 37.7599, -122.4148

GOOGLE_STATUS_HINTS: dict[str, str] = {
    "REQUEST_DENIED": "Key invalid, restricted, or required API not enabled in GCP.",
    "OVER_QUERY_LIMIT": "Quota exceeded for this key or billing not enabled.",
    "INVALID_REQUEST": "Malformed request — check coordinates and parameters.",
    "ZERO_RESULTS": "No results for these coordinates (key may still be valid).",
    "PERMISSION_DENIED": "Key invalid, restricted, or required API not enabled in GCP.",
    "UNAUTHENTICATED": "API key missing or invalid.",
}


@dataclass
class CheckResult:
    name: str
    url: str
    ok: bool
    status: str
    detail: str
    skipped: bool = False


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, str]) -> dict[str, Any]:
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


async def _post_json(
    client: httpx.AsyncClient,
    url: str,
    key: str,
    body: dict[str, Any],
    field_mask: str,
) -> tuple[int, dict[str, Any]]:
    resp = await client.post(
        url,
        json=body,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": field_mask,
        },
    )
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}
    return resp.status_code, data


def _legacy_status_detail(data: dict[str, Any]) -> tuple[str, str]:
    status = data.get("status", "UNKNOWN")
    detail = GOOGLE_STATUS_HINTS.get(status, data.get("error_message", ""))
    return status, detail


def _new_api_status_detail(status_code: int, data: dict[str, Any]) -> tuple[str, str]:
    if "error" in data:
        err = data["error"]
        status = err.get("status", f"HTTP_{status_code}")
        detail = err.get("message", GOOGLE_STATUS_HINTS.get(status, str(err)))
        return status, detail
    if status_code >= 400:
        return f"HTTP_{status_code}", data.get("raw", str(data))[:200]
    return "OK", ""


async def check_geocoding_api(client: httpx.AsyncClient, key: str) -> CheckResult:
    name = "Geocoding API"
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"latlng": f"{PICKUP_LAT},{PICKUP_LNG}", "key": key}
    data = await _get(client, url, params)
    status, detail = _legacy_status_detail(data)
    ok = status == "OK" and bool(data.get("results"))
    if ok:
        detail = data["results"][0]["formatted_address"]
    return CheckResult(name, url, ok, status, detail)


async def check_maps_sdk_android(_client: httpx.AsyncClient, _key: str) -> CheckResult:
    return CheckResult(
        "Maps SDK for Android",
        "(client SDK — no REST endpoint)",
        True,
        "SKIP",
        "Restrict key by Android package name + SHA-1 in GCP. Test from the app.",
        skipped=True,
    )


async def check_maps_sdk_ios(_client: httpx.AsyncClient, _key: str) -> CheckResult:
    return CheckResult(
        "Maps SDK for iOS",
        "(client SDK — no REST endpoint)",
        True,
        "SKIP",
        "Restrict key by iOS bundle ID in GCP. Test from the app.",
        skipped=True,
    )


async def check_places_api(client: httpx.AsyncClient, key: str) -> CheckResult:
    """Legacy Places API — Nearby Search."""
    name = "Places API"
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{PICKUP_LAT},{PICKUP_LNG}",
        "radius": "500",
        "type": "restaurant",
        "key": key,
    }
    data = await _get(client, url, params)
    status, detail = _legacy_status_detail(data)
    ok = status in ("OK", "ZERO_RESULTS") and "error_message" not in data
    if status == "OK" and data.get("results"):
        detail = f"Found: {data['results'][0].get('name', '(unnamed)')}"
    elif status == "ZERO_RESULTS":
        detail = "No results nearby (key accepted)"
        ok = True
    return CheckResult(name, url, ok, status, detail)


async def check_places_api_new(client: httpx.AsyncClient, key: str) -> CheckResult:
    name = "Places API (New)"
    url = "https://places.googleapis.com/v1/places:searchNearby"
    body = {
        "includedTypes": ["restaurant"],
        "maxResultCount": 1,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": PICKUP_LAT, "longitude": PICKUP_LNG},
                "radius": 500.0,
            }
        },
    }
    status_code, data = await _post_json(client, url, key, body, "places.displayName")
    if status_code == 200 and data.get("places"):
        place_name = data["places"][0].get("displayName", {}).get("text", "(unnamed)")
        return CheckResult(name, url, True, "OK", f"Found: {place_name}")
    status, detail = _new_api_status_detail(status_code, data)
    return CheckResult(name, url, False, status, detail)


async def check_routes_api(client: httpx.AsyncClient, key: str) -> CheckResult:
    name = "Routes API"
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    body = {
        "origin": {
            "location": {"latLng": {"latitude": PICKUP_LAT, "longitude": PICKUP_LNG}}
        },
        "destination": {
            "location": {"latLng": {"latitude": DROP_LAT, "longitude": DROP_LNG}}
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }
    status_code, data = await _post_json(
        client, url, key, body, "routes.distanceMeters,routes.duration"
    )
    if status_code == 200 and data.get("routes"):
        route = data["routes"][0]
        meters = route.get("distanceMeters", 0)
        duration = route.get("duration", "")
        return CheckResult(name, url, True, "OK", f"{meters / 1000:.1f} km, duration {duration}")
    status, detail = _new_api_status_detail(status_code, data)
    return CheckResult(name, url, False, status, detail)


async def check_distance_matrix_api(client: httpx.AsyncClient, key: str) -> CheckResult:
    name = "Distance Matrix API"
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": f"{PICKUP_LAT},{PICKUP_LNG}",
        "destinations": f"{DROP_LAT},{DROP_LNG}",
        "mode": "driving",
        "departure_time": "now",
        "key": key,
    }
    data = await _get(client, url, params)
    status, detail = _legacy_status_detail(data)
    element_status = ""
    ok = status == "OK"
    if ok:
        rows = data.get("rows") or []
        element = rows[0]["elements"][0] if rows and rows[0].get("elements") else {}
        element_status = element.get("status", "UNKNOWN")
        ok = element_status == "OK"
        if ok:
            duration = element.get("duration_in_traffic") or element.get("duration")
            eta_min = max(1, int(round(duration["value"] / 60))) if duration else 0
            traffic = "yes" if element.get("duration_in_traffic") else "no"
            detail = f"ETA {eta_min} min (traffic: {traffic})"
        else:
            detail = GOOGLE_STATUS_HINTS.get(element_status, element_status)
    status_out = f"{status}" + (f" / element {element_status}" if element_status else "")
    return CheckResult(name, url, ok, status_out, detail)


async def check_directions_api(client: httpx.AsyncClient, key: str) -> CheckResult:
    name = "Directions API"
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{PICKUP_LAT},{PICKUP_LNG}",
        "destination": f"{DROP_LAT},{DROP_LNG}",
        "departure_time": "now",
        "key": key,
    }
    data = await _get(client, url, params)
    status, detail = _legacy_status_detail(data)
    ok = status == "OK" and bool(data.get("routes"))
    if ok:
        leg = data["routes"][0]["legs"][0]
        km = leg["distance"]["value"] / 1000
        duration = leg.get("duration_in_traffic") or leg.get("duration")
        min_ = duration["value"] / 60 if duration else 0
        traffic = "yes" if leg.get("duration_in_traffic") else "no"
        detail = f"{km:.1f} km, {min_:.0f} min (traffic: {traffic})"
    return CheckResult(name, url, ok, status, detail)


# Order matches GCP "Selected APIs" list.
ENABLED_API_CHECKS = [
    check_geocoding_api,
    check_maps_sdk_android,
    check_maps_sdk_ios,
    check_places_api,
    check_places_api_new,
    check_routes_api,
    check_distance_matrix_api,
    check_directions_api,
]


async def run_checks(key: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for check in ENABLED_API_CHECKS:
            try:
                results.append(await check(client, key))
            except httpx.HTTPError as exc:
                results.append(
                    CheckResult(check.__name__, "", False, "HTTP_ERROR", str(exc))
                )
    return results


def _print_results(results: list[CheckResult]) -> int:
    print(
        f"Testing Google Maps API key "
        f"(pickup {PICKUP_LAT},{PICKUP_LNG} → drop {DROP_LAT},{DROP_LNG})\n"
    )
    failed = 0
    skipped = 0
    for r in results:
        if r.skipped:
            mark = "SKIP"
            skipped += 1
        elif r.ok:
            mark = "PASS"
        else:
            mark = "FAIL"
            failed += 1
        print(f"[{mark}] {r.name}")
        print(f"       status: {r.status}")
        if r.detail:
            print(f"       detail: {r.detail}")
        if r.url and not r.skipped:
            print(f"       url:    {r.url}")
        print()

    http_checks = [r for r in results if not r.skipped]
    passed = sum(1 for r in http_checks if r.ok)
    print(f"Result: {passed}/{len(http_checks)} HTTP checks passed", end="")
    if skipped:
        print(f" ({skipped} SDK checks skipped)", end="")
    print()
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--key",
        help="Google Maps API key (default: MAPS_API_KEY env or .env)",
    )
    args = parser.parse_args()

    _load_env_file(ROOT / ".env")
    key = args.key or os.environ.get("MAPS_API_KEY", "").strip()
    if not key:
        print("Error: set MAPS_API_KEY or pass --key", file=sys.stderr)
        sys.exit(2)

    masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "(hidden)"
    print(f"Using key: {masked}\n")

    exit_code = _print_results(asyncio.run(run_checks(key)))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
