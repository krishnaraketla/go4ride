from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_driver
from app.core.exceptions import bad_request, not_found
from app.db.session import get_db
from app.models.driver import DriverProfile
from app.models.enums import KycStatus
from app.models.ride import RideType
from app.models.user import User
from app.schemas.driver import (
    DriverEarningsResponse,
    DriverProfileResponse,
    DriverStatsResponse,
    MenuInbox,
    MenuItem,
    MenuProfileSummary,
    MenuSubscription,
    MenuWallet,
    ProfileMenuResponse,
    UpdateDriverProfileRequest,
)
from app.schemas.response import ApiResponse, ok

router = APIRouter(prefix="/profile", tags=["Driver Profile"])


@router.get("", response_model=ApiResponse[DriverProfileResponse])
async def get_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile = await _get_or_404(db, driver.id)
    return ok(_to_response(driver, profile), message="Profile retrieved")


@router.patch("", response_model=ApiResponse[DriverProfileResponse])
async def update_profile(
    body: UpdateDriverProfileRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile = await _get_or_404(db, driver.id)

    if body.name is not None:
        driver.name = body.name
    if body.vehicle_model is not None:
        profile.vehicle_model = body.vehicle_model
    if body.vehicle_plate is not None:
        profile.vehicle_plate = body.vehicle_plate
    if body.vehicle_color is not None:
        profile.vehicle_color = body.vehicle_color

    if body.ride_type_slug is not None:
        rt_result = await db.execute(
            select(RideType).where(RideType.slug == body.ride_type_slug)
        )
        ride_type = rt_result.scalar_one_or_none()
        if ride_type is None:
            raise not_found("Ride type not found", "RIDE_TYPE_NOT_FOUND")
        profile.ride_type_id = ride_type.id

    await db.commit()
    await db.refresh(profile)
    return ok(_to_response(driver, profile), message="Profile updated")


@router.post("", response_model=ApiResponse[DriverProfileResponse], status_code=201)
async def create_profile(
    body: UpdateDriverProfileRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Called during driver onboarding to create the profile for the first time."""
    existing = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver.id)
    )
    if existing.scalar_one_or_none() is not None:
        raise bad_request("Profile already exists", "PROFILE_EXISTS")

    if not body.vehicle_model or not body.vehicle_plate or not body.vehicle_color:
        raise bad_request(
            "vehicle_model, vehicle_plate and vehicle_color are required",
            "MISSING_FIELDS",
        )

    ride_type_id = None
    if body.ride_type_slug:
        rt_result = await db.execute(
            select(RideType).where(RideType.slug == body.ride_type_slug)
        )
        ride_type = rt_result.scalar_one_or_none()
        if ride_type is None:
            raise not_found("Ride type not found", "RIDE_TYPE_NOT_FOUND")
        ride_type_id = ride_type.id

    profile = DriverProfile(
        user_id=driver.id,
        vehicle_model=body.vehicle_model,
        vehicle_plate=body.vehicle_plate,
        vehicle_color=body.vehicle_color,
        ride_type_id=ride_type_id,
        kyc_status=KycStatus.pending,
    )
    db.add(profile)
    if body.name:
        driver.name = body.name
    await db.commit()
    await db.refresh(profile)
    return ok(_to_response(driver, profile), message="Profile created")


@router.get("/stats", response_model=ApiResponse[DriverStatsResponse])
async def get_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile = await _get_or_404(db, driver.id)
    return ok(
        DriverStatsResponse(
            total_rides=profile.total_rides or 0,
            completed_rides=profile.total_rides or 0,
            cancelled_rides=0,
            acceptance_rate=1.0,
            rating=profile.rating,
        ),
        message="Stats retrieved",
    )


@router.get("/earnings", response_model=ApiResponse[DriverEarningsResponse])
async def get_earnings(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    return ok(
        DriverEarningsResponse(
            today=Decimal("0.00"),
            this_week=Decimal("0.00"),
            this_month=Decimal("0.00"),
            total=Decimal("0.00"),
            currency="INR",
        ),
        message="Earnings retrieved",
    )


@router.get("/menu", response_model=ApiResponse[ProfileMenuResponse])
async def get_profile_menu(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Aggregated side-menu endpoint — returns everything the menu screen needs in one call."""
    result = await db.execute(
        select(DriverProfile)
        .where(DriverProfile.user_id == driver.id)
        .options(selectinload(DriverProfile.ride_type))
    )
    profile = result.scalar_one_or_none()
    rating = float(profile.rating) if profile and profile.rating else None

    menu_items = [
        MenuItem(key="inbox",           label="Inbox",           badge=0,    visible=True),
        MenuItem(key="rate_card",       label="My Rate Card",    visible=True),
        MenuItem(key="wallet",          label="Wallet",          visible=True),
        MenuItem(key="instant_payout",  label="Instant Payout",  visible=True),
        MenuItem(key="subscription",    label="My Subscription", visible=True),
        MenuItem(key="ride_filters",    label="Ride Filters",    visible=True),
        MenuItem(key="insights",        label="Insights",        visible=True),
        MenuItem(key="manage_vehicles", label="Manage Vehicles", visible=True),
        MenuItem(key="documents",       label="Documents",       visible=True),
        MenuItem(key="refer_rider",     label="Refer a Rider",   visible=True),
        MenuItem(key="refer_driver",    label="Refer a Driver",  visible=True),
        MenuItem(key="account",         label="Account",         visible=True),
    ]

    return ok(
        ProfileMenuResponse(
            profile=MenuProfileSummary(
                driver_id=str(driver.id),
                name=driver.name,
                avatar_url=getattr(driver, "avatar_url", None),
                phone=driver.phone,
                rating=rating,
            ),
            inbox=MenuInbox(unread_count=0),
            wallet=MenuWallet(balance=0.0, currency="INR"),
            subscription=MenuSubscription(),
            menu_items=menu_items,
        ),
        message="Profile menu retrieved",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_or_404(db: AsyncSession, driver_id) -> DriverProfile:
    result = await db.execute(
        select(DriverProfile)
        .where(DriverProfile.user_id == driver_id)
        .options(selectinload(DriverProfile.ride_type))
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise not_found("Driver profile not found. Complete onboarding first.", "PROFILE_NOT_FOUND")
    return profile


def _to_response(driver: User, profile: DriverProfile) -> DriverProfileResponse:
    return DriverProfileResponse(
        driver_id=driver.id,
        name=driver.name,
        phone=driver.phone,
        vehicle_model=profile.vehicle_model,
        vehicle_plate=profile.vehicle_plate,
        vehicle_color=profile.vehicle_color,
        ride_type_slug=profile.ride_type.slug if profile.ride_type else None,
        driver_status=profile.driver_status,
        kyc_status=profile.kyc_status,
        rating=profile.rating,
        total_rides=profile.total_rides or 0,
    )
