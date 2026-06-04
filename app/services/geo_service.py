import math
from dataclasses import dataclass
from decimal import Decimal

import httpx

from app.core.config import get_settings


@dataclass(frozen=True)
class RouteInfo:
    distance_km: Decimal
    duration_min: Decimal
    polyline: str | None = None


async def reverse_geocode(lat: Decimal, lng: Decimal) -> str:
    settings = get_settings()
    if settings.maps_provider == "mock":
        return f"Address at {lat}, {lng}"
    if settings.maps_provider == "google":
        return await _google_reverse(lat, lng)
    return await _mapbox_reverse(lat, lng)


async def get_route(
    pickup_lat: Decimal,
    pickup_lng: Decimal,
    drop_lat: Decimal,
    drop_lng: Decimal,
) -> RouteInfo:
    settings = get_settings()
    if settings.maps_provider == "mock":
        distance_km, duration_min = _haversine_estimate(pickup_lat, pickup_lng, drop_lat, drop_lng)
        return RouteInfo(distance_km=distance_km, duration_min=duration_min, polyline=None)
    if settings.maps_provider == "google":
        return await _google_directions(pickup_lat, pickup_lng, drop_lat, drop_lng)
    return await _mapbox_directions_route(pickup_lat, pickup_lng, drop_lat, drop_lng)


async def get_route_distance_duration(
    pickup_lat: Decimal,
    pickup_lng: Decimal,
    drop_lat: Decimal,
    drop_lng: Decimal,
) -> tuple[Decimal, Decimal]:
    route = await get_route(pickup_lat, pickup_lng, drop_lat, drop_lng)
    return route.distance_km, route.duration_min


def haversine_distance_m(lat1: Decimal, lng1: Decimal, lat2: Decimal, lng2: Decimal) -> int:
    """Great-circle distance in meters."""
    r = 6371000
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lng2) - float(lng1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return int(round(2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))))


def _haversine_estimate(
    lat1: Decimal, lng1: Decimal, lat2: Decimal, lng2: Decimal
) -> tuple[Decimal, Decimal]:
    r = 6371
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lng2) - float(lng1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    distance_km = Decimal(str(round(2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)))
    duration_min = (distance_km / Decimal("30") * Decimal("60")).quantize(Decimal("0.01"))
    return distance_km, duration_min


async def _google_reverse(lat: Decimal, lng: Decimal) -> str:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"latlng": f"{lat},{lng}", "key": settings.maps_api_key},
        )
        data = resp.json()
        if data.get("results"):
            return data["results"][0]["formatted_address"]
    return f"Address at {lat}, {lng}"


async def _google_directions(
    pickup_lat: Decimal, pickup_lng: Decimal, drop_lat: Decimal, drop_lng: Decimal
) -> RouteInfo:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params={
                "origin": f"{pickup_lat},{pickup_lng}",
                "destination": f"{drop_lat},{drop_lng}",
                "key": settings.maps_api_key,
            },
        )
        data = resp.json()
        route = data["routes"][0]
        leg = route["legs"][0]
        distance_m = leg["distance"]["value"]
        duration_s = leg["duration"]["value"]
        polyline = route.get("overview_polyline", {}).get("points")
        return RouteInfo(
            distance_km=Decimal(str(round(distance_m / 1000, 2))),
            duration_min=Decimal(str(round(duration_s / 60, 2))),
            polyline=polyline,
        )


async def _mapbox_reverse(lat: Decimal, lng: Decimal) -> str:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lng},{lat}.json",
            params={"access_token": settings.maps_api_key},
        )
        data = resp.json()
        if data.get("features"):
            return data["features"][0]["place_name"]
    return f"Address at {lat}, {lng}"


async def _mapbox_directions_route(
    pickup_lat: Decimal, pickup_lng: Decimal, drop_lat: Decimal, drop_lng: Decimal
) -> RouteInfo:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.mapbox.com/directions/v5/mapbox/driving/{pickup_lng},{pickup_lat};{drop_lng},{drop_lat}",
            params={
                "access_token": settings.maps_api_key,
                "geometries": "polyline",
            },
        )
        data = resp.json()
        route = data["routes"][0]
        return RouteInfo(
            distance_km=Decimal(str(round(route["distance"] / 1000, 2))),
            duration_min=Decimal(str(round(route["duration"] / 60, 2))),
            polyline=route.get("geometry"),
        )
