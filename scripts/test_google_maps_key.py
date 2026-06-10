#!/usr/bin/env python3
"""Smoke-test a Google Maps API key against the endpoints used by go4ride.

Usage:
  export MAPS_API_KEY=your-key
  python scripts/test_google_maps_key.py

  python scripts/test_google_maps_key.py --key YOUR_KEY

Reads MAPS_API_KEY from the environment, or from .env in the repo root if unset.
Enable in GCP: Geocoding API, Directions API, Distance Matrix API.
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

# Bangalore coords used in tests/docs (reverse-geocode, quote, ETA).
PICKUP_LAT, PICKUP_LNG = "12.9716", "77.5946"
DROP_LAT, DROP_LNG = "12.9352", "77.6245"

GOOGLE_STATUS_HINTS: dict[str, str] = {
    "REQUEST_DENIED": "Key invalid, restricted, or required API not enabled in GCP.",
    "OVER_QUERY_LIMIT": "Quota exceeded for this key or billing not enabled.",
    "INVALID_REQUEST": "Malformed request — check coordinates and parameters.",
    "ZERO_RESULTS": "No results for these coordinates (key may still be valid).",
}


@dataclass
class CheckResult:
    name: str
    url: str
    ok: bool
    status: str
    detail: str


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


async def check_geocoding(client: httpx.AsyncClient, key: str) -> CheckResult:
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"latlng": f"{PICKUP_LAT},{PICKUP_LNG}", "key": key}
    data = await _get(client, url, params)
    status = data.get("status", "UNKNOWN")
    ok = status == "OK" and bool(data.get("results"))
    address = data["results"][0]["formatted_address"] if ok else ""
    detail = address if ok else GOOGLE_STATUS_HINTS.get(status, data.get("error_message", ""))
    return CheckResult("Geocoding (reverse)", url, ok, status, detail)


async def check_directions_route(client: httpx.AsyncClient, key: str) -> CheckResult:
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{PICKUP_LAT},{PICKUP_LNG}",
        "destination": f"{DROP_LAT},{DROP_LNG}",
        "key": key,
    }
    data = await _get(client, url, params)
    status = data.get("status", "UNKNOWN")
    ok = status == "OK" and bool(data.get("routes"))
    if ok:
        leg = data["routes"][0]["legs"][0]
        km = leg["distance"]["value"] / 1000
        min_ = leg["duration"]["value"] / 60
        detail = f"{km:.1f} km, {min_:.0f} min"
    else:
        detail = GOOGLE_STATUS_HINTS.get(status, data.get("error_message", ""))
    return CheckResult("Directions (route)", url, ok, status, detail)


async def check_directions_eta(client: httpx.AsyncClient, key: str) -> CheckResult:
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{PICKUP_LAT},{PICKUP_LNG}",
        "destination": f"{DROP_LAT},{DROP_LNG}",
        "departure_time": "now",
        "key": key,
    }
    data = await _get(client, url, params)
    status = data.get("status", "UNKNOWN")
    ok = status == "OK" and bool(data.get("routes"))
    if ok:
        leg = data["routes"][0]["legs"][0]
        duration = leg.get("duration_in_traffic") or leg.get("duration")
        eta_min = max(1, int(round(duration["value"] / 60))) if duration else 0
        detail = f"ETA {eta_min} min (duration_in_traffic={'yes' if leg.get('duration_in_traffic') else 'no'})"
    else:
        detail = GOOGLE_STATUS_HINTS.get(status, data.get("error_message", ""))
    return CheckResult("Directions (ETA / traffic)", url, ok, status, detail)


async def check_distance_matrix(client: httpx.AsyncClient, key: str) -> CheckResult:
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": f"{PICKUP_LAT},{PICKUP_LNG}",
        "destinations": f"{DROP_LAT},{DROP_LNG}",
        "mode": "driving",
        "departure_time": "now",
        "key": key,
    }
    data = await _get(client, url, params)
    status = data.get("status", "UNKNOWN")
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
            detail = f"ETA {eta_min} min (duration_in_traffic={'yes' if element.get('duration_in_traffic') else 'no'})"
        else:
            detail = GOOGLE_STATUS_HINTS.get(element_status, element_status)
    else:
        detail = GOOGLE_STATUS_HINTS.get(status, data.get("error_message", ""))
    status_out = f"{status}" + (f" / element {element_status}" if element_status else "")
    return CheckResult("Distance Matrix (driver ETA)", url, ok, status_out, detail)


async def run_checks(key: str) -> list[CheckResult]:
    checks = [
        check_geocoding,
        check_directions_route,
        check_directions_eta,
        check_distance_matrix,
    ]
    results: list[CheckResult] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for check in checks:
            try:
                results.append(await check(client, key))
            except httpx.HTTPError as exc:
                results.append(
                    CheckResult(check.__name__, "", False, "HTTP_ERROR", str(exc))
                )
    return results


def _print_results(results: list[CheckResult]) -> int:
    print(f"Testing Google Maps API key (pickup {PICKUP_LAT},{PICKUP_LNG} → drop {DROP_LAT},{DROP_LNG})\n")
    failed = 0
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        print(f"[{mark}] {r.name}")
        print(f"       status: {r.status}")
        if r.detail:
            print(f"       detail: {r.detail}")
        if not r.ok:
            failed += 1
        print()
    passed = len(results) - failed
    print(f"Result: {passed}/{len(results)} checks passed")
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
