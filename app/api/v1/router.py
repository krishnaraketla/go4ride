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
from app.api.v1.admin import drivers as admin_drivers
from app.api.v1.driver import (
    auth as driver_auth,
    availability as driver_availability,
    dashboard as driver_dashboard,
    insights as driver_insights,
    onboarding as driver_onboarding,
    profile as driver_profile,
    rides as driver_rides,
)

api_router = APIRouter(prefix="/api/v1")

# Rider routes
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

# Driver routes
_driver_prefix = "/driver"
api_router.include_router(driver_auth.router, prefix=_driver_prefix)
api_router.include_router(driver_profile.router, prefix=_driver_prefix)
api_router.include_router(driver_availability.router)           # already has /driver prefix internally
api_router.include_router(driver_onboarding.router, prefix=_driver_prefix)
api_router.include_router(driver_rides.router, prefix=_driver_prefix)
api_router.include_router(driver_insights.router, prefix=_driver_prefix)
api_router.include_router(driver_dashboard.router, prefix=_driver_prefix)

# Admin routes (internal — X-Admin-Key header)
api_router.include_router(admin_drivers.router, prefix="/admin")
