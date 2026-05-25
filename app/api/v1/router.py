from fastapi import APIRouter

from app.api.v1 import (
    addresses,
    auth,
    email as email_router,
    insights,
    location,
    payment_methods,
    profile,
    promo,
    rides,
    settings as settings_router,
    wallet,
    ws,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(location.router)
api_router.include_router(rides.router)
api_router.include_router(profile.router)
api_router.include_router(insights.router)
api_router.include_router(addresses.router)
api_router.include_router(settings_router.router)
api_router.include_router(wallet.router)
api_router.include_router(promo.router)
api_router.include_router(email_router.router)
api_router.include_router(payment_methods.router)
api_router.include_router(ws.router)
