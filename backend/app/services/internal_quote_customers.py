from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.internal_quote import InternalQuoteCustomer
from app.schemas.internal_quote import (
    InternalQuoteCustomerCreateRequest,
    InternalQuoteCustomerOut,
    InternalQuoteCustomerUpdateRequest,
)
from app.services.auth import (
    AuthContext,
    add_auth_audit,
    ensure_permission_in_scope,
    now_text,
)
from app.services.internal_quote import ensure_quote_read


CUSTOMER_DEPARTMENT = "sales-business"
CUSTOMER_MANAGE_PERMISSION = "internal_quote:customer_manage"


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _customer_out(customer: InternalQuoteCustomer) -> InternalQuoteCustomerOut:
    return InternalQuoteCustomerOut(
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


def _get_customer(db: Session, customer_id: str) -> InternalQuoteCustomer:
    customer = db.get(InternalQuoteCustomer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户资料不存在或已被删除")
    return customer


def _ensure_manage(db: Session, user: AuthContext, factory_id: str) -> None:
    ensure_permission_in_scope(
        db,
        user,
        CUSTOMER_MANAGE_PERMISSION,
        factory_id,
        CUSTOMER_DEPARTMENT,
    )


def _commit_unique(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="当前厂区已存在同名客户") from error


def list_customers(
    db: Session,
    factory_id: str,
    user: AuthContext,
) -> list[InternalQuoteCustomerOut]:
    ensure_quote_read(db, user, factory_id)
    customers = db.scalars(
        select(InternalQuoteCustomer)
        .where(InternalQuoteCustomer.factory_id == factory_id)
        .order_by(InternalQuoteCustomer.normalized_name, InternalQuoteCustomer.id)
    ).all()
    return [_customer_out(customer) for customer in customers]


def create_customer(
    db: Session,
    factory_id: str,
    payload: InternalQuoteCustomerCreateRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteCustomerOut:
    _ensure_manage(db, user, factory_id)
    timestamp = now_text()
    customer = InternalQuoteCustomer(
        id=f"IQC-{uuid4().hex.upper()}",
        factory_id=factory_id,
        name=payload.name,
        normalized_name=_normalized_name(payload.name),
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
        "internal_quote_customer_created",
        username=user.username,
        user_id=user.id,
        detail=f"新增厂区客户：{factory_id}/{payload.name}",
        request=request,
    )
    _commit_unique(db)
    db.refresh(customer)
    return _customer_out(customer)


def update_customer(
    db: Session,
    customer_id: str,
    payload: InternalQuoteCustomerUpdateRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteCustomerOut:
    customer = _get_customer(db, customer_id)
    _ensure_manage(db, user, customer.factory_id)
    if payload.revision != customer.revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "客户资料已被其他人更新，请刷新后重试",
                "current_revision": customer.revision,
            },
        )

    old_name = customer.name
    customer.name = payload.name
    customer.normalized_name = _normalized_name(payload.name)
    customer.revision += 1
    customer.updated_by = user.id
    customer.updated_by_name = user.display_name
    customer.updated_at = now_text()
    add_auth_audit(
        db,
        "internal_quote_customer_updated",
        username=user.username,
        user_id=user.id,
        detail=(
            f"修改厂区客户：{customer.factory_id}/{old_name}->{payload.name}，"
            f"revision {payload.revision}->{customer.revision}"
        ),
        request=request,
    )
    _commit_unique(db)
    db.refresh(customer)
    return _customer_out(customer)


def delete_customer(
    db: Session,
    customer_id: str,
    revision: int,
    user: AuthContext,
    request: Request | None = None,
) -> None:
    customer = _get_customer(db, customer_id)
    _ensure_manage(db, user, customer.factory_id)
    if revision != customer.revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "客户资料已被其他人更新，请刷新后重试",
                "current_revision": customer.revision,
            },
        )

    add_auth_audit(
        db,
        "internal_quote_customer_deleted",
        username=user.username,
        user_id=user.id,
        detail=(
            f"删除厂区客户：{customer.factory_id}/{customer.name}，"
            "仅移除后续建单选项，历史报价保留原客户名称"
        ),
        request=request,
    )
    db.delete(customer)
    db.commit()
