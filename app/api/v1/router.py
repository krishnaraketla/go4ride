from fastapi import APIRouter

from app.api.v1 import auth, location, profile, rides, ws

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(location.router)
api_router.include_router(rides.router)
api_router.include_router(profile.router)
api_router.include_router(ws.router)
