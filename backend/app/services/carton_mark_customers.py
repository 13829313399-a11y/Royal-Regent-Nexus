from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.carton_mark import CartonMarkCustomer
from app.schemas.carton_mark import (
    CartonMarkCustomerCreateRequest,
    CartonMarkCustomerOut,
    CartonMarkCustomerUpdateRequest,
)
from app.services.auth import AuthContext, add_auth_audit, now_text
from app.services.carton_mark_library import (
    CARTON_MARK_WRITE_DEPARTMENTS,
    ensure_carton_mark_scope,
)
from app.services.carton_procurement import require_carton_factory


CARTON_MARK_CUSTOMER_MANAGE_PERMISSION = "carton_mark:customer_manage"


def normalize_carton_mark_customer_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _customer_out(customer: CartonMarkCustomer) -> CartonMarkCustomerOut:
    return CartonMarkCustomerOut(
        id=customer.id,
        factory_id=customer.factory_id,
        name=customer.name,
        revision=customer.revision,
        created_by=customer.created_by,
        created_by_name=customer.created_by_name,
        created_at=customer.created_at,
        updated_by=customer.updated_by,
        updated_by_name=customer.updated_by_name,
        updated_at=customer.updated_at,
    )


def _get_customer(
    db: Session,
    *,
    factory_id: str,
    customer_id: str,
) -> CartonMarkCustomer:
    customer = db.scalar(
        select(CartonMarkCustomer).where(
            CartonMarkCustomer.id == customer_id,
            CartonMarkCustomer.factory_id == factory_id,
        )
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="箱唛客户不存在或已被删除")
    return customer


def _commit_unique(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="当前厂区已存在同名箱唛客户") from error


def list_carton_mark_customers(
    db: Session,
    *,
    factory_id: str,
) -> list[CartonMarkCustomerOut]:
    factory_id = require_carton_factory(factory_id)
    customers = db.scalars(
        select(CartonMarkCustomer)
        .where(CartonMarkCustomer.factory_id == factory_id)
        .order_by(CartonMarkCustomer.normalized_name, CartonMarkCustomer.id)
    ).all()
    return [_customer_out(customer) for customer in customers]


def create_carton_mark_customer(
    db: Session,
    user: AuthContext,
    *,
    factory_id: str,
    payload: CartonMarkCustomerCreateRequest,
    request: Request | None = None,
) -> CartonMarkCustomerOut:
    factory_id = ensure_carton_mark_scope(
        db,
        user,
        CARTON_MARK_CUSTOMER_MANAGE_PERMISSION,
        factory_id,
        CARTON_MARK_WRITE_DEPARTMENTS,
    )
    timestamp = now_text()
    customer = CartonMarkCustomer(
        id=f"CMC-{uuid4().hex.upper()}",
        factory_id=factory_id,
        name=payload.name,
        normalized_name=normalize_carton_mark_customer_name(payload.name),
        revision=1,
        created_by=user.id,
        created_by_name=user.display_name,
        created_at=timestamp,
        updated_by=user.id,
        updated_by_name=user.display_name,
        updated_at=timestamp,
    )
    db.add(customer)
    add_auth_audit(
        db,
        "carton_mark_customer_created",
        username=user.username,
        user_id=user.id,
        detail=f"新增箱唛客户：{factory_id}/{payload.name}",
        request=request,
    )
    _commit_unique(db)
    db.refresh(customer)
    return _customer_out(customer)


def update_carton_mark_customer(
    db: Session,
    user: AuthContext,
    *,
    factory_id: str,
    customer_id: str,
    payload: CartonMarkCustomerUpdateRequest,
    request: Request | None = None,
) -> CartonMarkCustomerOut:
    factory_id = ensure_carton_mark_scope(
        db,
        user,
        CARTON_MARK_CUSTOMER_MANAGE_PERMISSION,
        factory_id,
        CARTON_MARK_WRITE_DEPARTMENTS,
    )
    customer = _get_customer(db, factory_id=factory_id, customer_id=customer_id)
    if customer.revision != payload.revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "箱唛客户已被其他人更新，请刷新后重试",
                "current_revision": customer.revision,
            },
        )
    old_name = customer.name
    customer.name = payload.name
    customer.normalized_name = normalize_carton_mark_customer_name(payload.name)
    customer.revision += 1
    customer.updated_by = user.id
    customer.updated_by_name = user.display_name
    customer.updated_at = now_text()
    add_auth_audit(
        db,
        "carton_mark_customer_updated",
        username=user.username,
        user_id=user.id,
        detail=f"修改箱唛客户：{factory_id}/{old_name}->{payload.name}",
        request=request,
    )
    _commit_unique(db)
    db.refresh(customer)
    return _customer_out(customer)


def delete_carton_mark_customer(
    db: Session,
    user: AuthContext,
    *,
    factory_id: str,
    customer_id: str,
    revision: int,
    request: Request | None = None,
) -> None:
    factory_id = ensure_carton_mark_scope(
        db,
        user,
        CARTON_MARK_CUSTOMER_MANAGE_PERMISSION,
        factory_id,
        CARTON_MARK_WRITE_DEPARTMENTS,
    )
    customer = _get_customer(db, factory_id=factory_id, customer_id=customer_id)
    if customer.revision != revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "箱唛客户已被其他人更新，请刷新后重试",
                "current_revision": customer.revision,
            },
        )
    add_auth_audit(
        db,
        "carton_mark_customer_deleted",
        username=user.username,
        user_id=user.id,
        detail=(
            f"删除箱唛客户：{factory_id}/{customer.name}；"
            "仅移除后续上传选项，历史箱唛归档名称保持不变"
        ),
        request=request,
    )
    db.delete(customer)
    db.commit()
