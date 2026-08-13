from dataclasses import replace
from decimal import Decimal

import pytest
from app.db import Base
from app.models.injection_scheduling_execution import InjectionSchedulingOrder
from app.models.internal_quote import InternalQuote
from app.schemas.ai import AIPageContextInput
from app.services.ai.context_builder import (
    AIPageContextValidationError,
    build_server_page_context,
    render_server_page_context,
)
from app.services.auth import (
    AuthContext,
    AuthGrantContext,
    AuthOverrideContext,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(
        engine,
        tables=(InjectionSchedulingOrder.__table__, InternalQuote.__table__),
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)()
    testing_session.add(
        InjectionSchedulingOrder(
            id="order-safe-1",
            factory_id="huaxing",
            order_no="000123",
            item_no="000045",
            product_name="SENSITIVE PRODUCT",
            order_quantity=Decimal(100),
            status="BACKLOG",
            revision=3,
            created_at="2026-08-12T10:00:00+08:00",
            updated_at="2026-08-12T10:00:00+08:00",
        )
    )
    testing_session.add(
        InternalQuote(
            id="quote-safe-1",
            factory_id="huaxing",
            workshop_code="huaxing",
            workshop_name="华兴",
            quote_no="Q-0001",
            product_name="SENSITIVE PRODUCT",
            customer="SENSITIVE CUSTOMER",
            qty=99,
            version_label="V1",
            status="drafting",
            header_revision=2,
            target_customer_price="SENSITIVE PRICE",
            created_by="seed",
            created_by_name="seed",
            created_at="2026-08-12 10:00:00",
            updated_at="2026-08-12 10:00:00",
        )
    )
    testing_session.commit()
    try:
        yield testing_session
    finally:
        testing_session.close()
        engine.dispose()


def _user(permission: str, department: str, factory_id: str = "huaxing") -> AuthContext:
    return AuthContext(
        id="selected-user",
        username="selected-user",
        display_name="选中实体用户",
        roles=("reader",),
        role_codes=("reader",),
        permissions=frozenset({permission}),
        factory_scopes=(factory_id,),
        department_scopes=(department,),
        grants=(
            AuthGrantContext(
                role_id="selected-reader",
                role_name="选中实体读取",
                factory_id=factory_id,
                department=department,
                permissions=frozenset({permission}),
                binding_id=f"selected-{factory_id}-{department}",
            ),
        ),
        active_permission_codes=frozenset({permission}),
    )


def _scheduling_context(revision: int = 3, factory_id: str = "huaxing") -> AIPageContextInput:
    return AIPageContextInput.model_validate(
        {
            "route_name": "injection-scheduling-v2",
            "path": "/modules/production/injection-scheduling",
            "factory_id": factory_id,
            "module_id": "injection-scheduling",
            "selected_entity": {
                "type": "scheduling_backlog_order",
                "id": "order-safe-1",
                "revision": revision,
            },
        }
    )


def test_selected_entity_is_reloaded_authorized_and_minimized(db: Session) -> None:
    context = build_server_page_context(
        _scheduling_context(),
        _user("injection_scheduling:read", "production"),
        db=db,
        semantic_gateway_enabled=True,
    )
    assert context is not None and context.selected_entity is not None
    assert context.selected_entity.model_dump() == {
        "type": "scheduling_backlog_order",
        "id": "order-safe-1",
        "revision": 3,
        "display_label": "000123 / 000045",
        "source_type": "FORMAL",
    }
    rendered = render_server_page_context(context)
    assert rendered is not None
    assert "SENSITIVE PRODUCT" not in rendered
    assert "order_quantity" not in rendered


def test_selected_entity_flag_stale_revision_cross_factory_and_type_fail_closed(
    db: Session,
) -> None:
    user = _user("injection_scheduling:read", "production")
    with pytest.raises(AIPageContextValidationError):
        build_server_page_context(_scheduling_context(), user, db=db)
    with pytest.raises(AIPageContextValidationError):
        build_server_page_context(
            _scheduling_context(revision=2),
            user,
            db=db,
            semantic_gateway_enabled=True,
        )
    with pytest.raises(AIPageContextValidationError):
        build_server_page_context(
            _scheduling_context(factory_id="huakang-a"),
            _user("injection_scheduling:read", "production", "huakang-a"),
            db=db,
            semantic_gateway_enabled=True,
        )
    forged_payload = _scheduling_context().model_dump(mode="json")
    forged_payload["selected_entity"] = {
        "type": "internal_quote",
        "id": "quote-safe-1",
        "revision": 2,
    }
    forged_type = AIPageContextInput.model_validate(
        forged_payload
    )
    with pytest.raises(AIPageContextValidationError):
        build_server_page_context(
            forged_type,
            user,
            db=db,
            semantic_gateway_enabled=True,
        )


def test_selected_entity_rechecks_explicit_deny(db: Session) -> None:
    user = _user("injection_scheduling:read", "production")
    denied = replace(
        user,
        overrides=(
            AuthOverrideContext(
                id="deny-selected-order",
                permission_code="injection_scheduling:read",
                effect="deny",
                factory_id="huaxing",
                department="production",
            ),
        ),
    )
    with pytest.raises(AIPageContextValidationError):
        build_server_page_context(
            _scheduling_context(),
            denied,
            db=db,
            semantic_gateway_enabled=True,
        )


def test_internal_quote_selected_entity_uses_header_revision_and_minimal_label(
    db: Session,
) -> None:
    requested = AIPageContextInput.model_validate(
        {
            "route_name": "internal-quote-desk-home",
            "path": "/modules/sales-business/internal-quote-desk",
            "factory_id": "huaxing",
            "module_id": "internal-quote",
            "selected_entity": {
                "type": "internal_quote",
                "id": "quote-safe-1",
                "revision": 2,
            },
        }
    )
    context = build_server_page_context(
        requested,
        _user("internal_quote:read", "sales-business"),
        db=db,
        semantic_gateway_enabled=True,
    )
    assert context is not None and context.selected_entity is not None
    assert context.selected_entity.display_label == "Q-0001"
    assert "SENSITIVE PRICE" not in (render_server_page_context(context) or "")
