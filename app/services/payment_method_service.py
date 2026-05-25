from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import not_found
from app.models.user import User
from app.models.wallet import PaymentMethod
from app.schemas.payment import PaymentMethodCreateRequest, PaymentMethodResponse, PaymentMethodUpdateRequest


async def list_payment_methods(db: AsyncSession, user: User) -> list[PaymentMethodResponse]:
    result = await db.execute(
        select(PaymentMethod)
        .where(PaymentMethod.user_id == user.id)
        .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
    )
    return [_to_response(pm) for pm in result.scalars().all()]


async def create_payment_method(
    db: AsyncSession, user: User, data: PaymentMethodCreateRequest
) -> PaymentMethodResponse:
    if data.is_default:
        await _clear_defaults(db, user.id)
    pm = PaymentMethod(
        user_id=user.id,
        brand=data.brand.upper(),
        last4=data.last4,
        exp_month=data.exp_month,
        exp_year=data.exp_year,
        is_default=data.is_default,
    )
    db.add(pm)
    await db.flush()
    count = (
        await db.execute(
            select(func.count()).select_from(PaymentMethod).where(PaymentMethod.user_id == user.id)
        )
    ).scalar() or 0
    if count == 1:
        pm.is_default = True
    return _to_response(pm)


async def update_payment_method(
    db: AsyncSession, user: User, method_id: UUID, data: PaymentMethodUpdateRequest
) -> PaymentMethodResponse:
    pm = await _get_method(db, user.id, method_id)
    if data.is_default:
        await _clear_defaults(db, user.id)
        pm.is_default = True
    return _to_response(pm)


async def delete_payment_method(db: AsyncSession, user: User, method_id: UUID) -> None:
    pm = await _get_method(db, user.id, method_id)
    was_default = pm.is_default
    await db.delete(pm)
    await db.flush()
    if was_default:
        result = await db.execute(
            select(PaymentMethod)
            .where(PaymentMethod.user_id == user.id)
            .order_by(PaymentMethod.created_at.desc())
            .limit(1)
        )
        first = result.scalar_one_or_none()
        if first:
            first.is_default = True


async def _get_method(db: AsyncSession, user_id: UUID, method_id: UUID) -> PaymentMethod:
    result = await db.execute(
        select(PaymentMethod).where(PaymentMethod.id == method_id, PaymentMethod.user_id == user_id)
    )
    pm = result.scalar_one_or_none()
    if pm is None:
        raise not_found("Payment method not found", "PAYMENT_METHOD_NOT_FOUND")
    return pm


async def _clear_defaults(db: AsyncSession, user_id: UUID) -> None:
    result = await db.execute(select(PaymentMethod).where(PaymentMethod.user_id == user_id))
    for pm in result.scalars().all():
        pm.is_default = False


def _to_response(pm: PaymentMethod) -> PaymentMethodResponse:
    return PaymentMethodResponse(
        id=pm.id,
        brand=pm.brand,
        last4=pm.last4,
        exp_month=pm.exp_month,
        exp_year=pm.exp_year,
        is_default=pm.is_default,
        created_at=pm.created_at,
    )
