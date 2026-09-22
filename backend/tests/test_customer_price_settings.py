import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.customer_price_settings import router
from app.db import get_db
from app.models.auth import AuthAuditLog
from app.models.customer_price_settings import CustomerPriceSettings, CustomerPriceSettingsSnapshot
from app.schemas.customer_price_settings import CustomerPriceSettingsUpdate
from app.services import customer_price_settings as service
from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, AuthProfileContext, get_current_user


PERMISSIONS = frozenset({"customer_price:settings_read", "customer_price:settings_manage", "customer_price:import_internal_quote"})


def user(permissions=PERMISSIONS, factory="huaxing", department="sales-business"):
    return AuthContext(
        id="sales-user", username="sales", display_name="业务人员", roles=("sales",), role_codes=("sales",),
        permissions=permissions, factory_scopes=(factory,), department_scopes=(department,),
        profile=AuthProfileContext(primary_factory_id=factory, primary_department=department),
        grants=(AuthGrantContext("sales-role", "Sales", factory, department, permissions),),
    )


def create_tables(engine):
    for model in (AuthAuditLog, CustomerPriceSettings, CustomerPriceSettingsSnapshot):
        model.__table__.create(engine)


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    create_tables(engine)
    app = FastAPI()
    app.include_router(router)
    context = {"user": user()}
    def db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_user] = lambda: context["user"]
    with TestClient(app) as client:
        yield client, context, engine
    engine.dispose()


URL = "/api/customer-price/settings?factory_id=huaxing&customer_id=buzzbee"
SNAPSHOTS = "/api/customer-price/settings/snapshots?factory_id=huaxing&customer_id=buzzbee"


def payload(client):
    result = client.get(URL).json()
    return {key: result[key] for key in ("revision", "materials", "rates", "texts")}


def test_defaults_read_only_and_all_customer_definitions(api):
    client, context, engine = api
    result = client.get(URL)
    assert result.status_code == 200
    data = result.json()
    assert data["revision"] == 0
    assert data["rates"]["injection_multiplier"] == 1
    assert data["rate_definitions"]["po_rate"]["kind"] == "rate"
    assert next(x["price"] for x in data["materials"] if x["material"] == "C-ABS镜片") == 23.1
    with Session(engine) as db:
        assert db.scalars(select(CustomerPriceSettings)).all() == []
    for customer, definition in service.DEFINITIONS.items():
        context["user"] = user(factory=definition["factoryId"])
        assert client.get(f'/api/customer-price/settings?factory_id={definition["factoryId"]}&customer_id={customer}').status_code == 200


@pytest.mark.parametrize("department", ["engineering", "production", "management"])
def test_non_sales_cannot_read_even_with_granted_permissions(api, department):
    client, context, _ = api
    context["user"] = user(PERMISSIONS | {"internal_quote:baseline_manage"}, department=department)
    assert client.get(URL).status_code == 403
    assert client.post(SNAPSHOTS, json={"revision": 0}).status_code == 403


def test_permission_factory_and_explicit_deny_boundaries(api):
    client, context, _ = api
    body = payload(client)
    context["user"] = user(frozenset({"customer_price:read", "internal_quote:baseline_manage"}))
    assert client.get(URL).status_code == 403
    context["user"] = user(frozenset({"customer_price:settings_read"}))
    assert client.get(URL).status_code == 200
    assert client.put(URL, json=body).status_code == 403
    assert client.post(SNAPSHOTS, json={"revision": 0}).status_code == 403
    context["user"] = user(factory="huakang-a")
    assert client.get(URL).status_code == 403
    context["user"] = replace(user(), overrides=(AuthOverrideContext(
        "deny", "customer_price:settings_read", "deny", "huaxing", "sales-business"),))
    assert client.get(URL).status_code == 403
    context["user"] = user()
    assert client.get(URL.replace("buzzbee", "three-sixty")).status_code == 404


def test_pricing_read_does_not_inherit_cross_factory_read_and_admin_denies_apply(api):
    client, context, _ = api
    original = user(factory="huakang-a")
    grant = replace(original.grants[0], role_id="position_sales_supervisor", unrestricted_department=True,
                    scope_mode="cross_factory_read", read_permissions=frozenset({"customer_price:settings_read"}))
    context["user"] = replace(original, grants=(grant,))
    assert client.get(URL).status_code == 403
    admin = replace(user(department="management"), grants=(AuthGrantContext(
        "admin", "Admin", "*", "*", frozenset(), role_code="admin"),))
    context["user"] = admin
    assert client.get(URL).status_code == 200
    context["user"] = replace(admin, overrides=(AuthOverrideContext(
        "deny", "customer_price:settings_read", "deny", "huaxing", "sales-business"),))
    assert client.get(URL).status_code == 403


def test_only_sales_positions_receive_settings_permissions():
    from app.services.system_positions import SYSTEM_POSITION_DEFINITIONS
    read_roles = {row.role_id for row in SYSTEM_POSITION_DEFINITIONS if "customer_price:settings_read" in row.permission_codes}
    manage_roles = {row.role_id for row in SYSTEM_POSITION_DEFINITIONS if "customer_price:settings_manage" in row.permission_codes}
    assert read_roles == {"position_sales_business", "position_sales_supervisor", "position_sales_manager"}
    assert manage_roles == {"position_sales_supervisor", "position_sales_manager"}


@pytest.mark.parametrize("change", [
    lambda p: p["rates"].update(hkd_usd=0),
    lambda p: p["rates"].update(po_rate=1.1),
    lambda p: p["rates"].update(detail_multiplier=-1),
    lambda p: p["rates"].update(detail_multiplier=True),
    lambda p: p["rates"].update(unknown=1),
    lambda p: p["rates"].pop("po_rate"),
    lambda p: p["texts"].update(unknown="secret"),
    lambda p: p["materials"].append(p["materials"][0]),
    lambda p: p["materials"][0].update(price=-1),
    lambda p: p["materials"][0].update(unit="g"),
    lambda p: p.update(final_total=123),
    lambda p: p.update(revision=True),
])
def test_malformed_settings_rejected(api, change):
    client, _, _ = api
    body = payload(client)
    change(body)
    assert client.put(URL, json=body).status_code == 422
    assert client.get(URL).json()["revision"] == 0


def test_nonfinite_rate_rejected(api):
    client, _, _ = api
    body = payload(client)
    body["rates"]["hkd_usd"] = float("inf")
    assert client.put(URL, content=json.dumps(body), headers={"Content-Type": "application/json"}).status_code == 422


def test_revision_conflicts_and_immutable_snapshots(api):
    client, context, engine = api
    default_snapshot = client.post(SNAPSHOTS, json={"revision": 0}).json()
    second = client.post(SNAPSHOTS, json={"revision": 0}).json()
    assert second["snapshot_id"] != default_snapshot["snapshot_id"]
    body = payload(client)
    body["rates"]["detail_multiplier"] = 1.23
    result = client.put(URL, json=body)
    assert result.status_code == 200
    assert result.json()["revision"] == 1
    assert client.put(URL, json=body).status_code == 409
    assert client.post(SNAPSHOTS, json={"revision": 0}).status_code == 409
    assert client.post(SNAPSHOTS, json={"revision": 1, "rates": {"detail_multiplier": 9}}).status_code == 422
    snapshot = client.post(SNAPSHOTS, json={"revision": 1}).json()
    assert snapshot["rates"]["detail_multiplier"] == 1.23
    path = "/api/customer-price/settings/snapshots/" + default_snapshot["snapshot_id"]
    assert client.get(path).json() == default_snapshot
    context["user"] = user(factory="huakang-a")
    assert client.get(path).status_code == 403
    with Session(engine) as db:
        audit = db.scalars(select(AuthAuditLog).where(AuthAuditLog.action == "customer_price_settings_updated")).all()
        assert len(audit) == 1
        assert json.loads(audit[0].detail)["revision"] == 1
        assert set(json.loads(audit[0].detail)) == {"factory_id", "customer_id", "previous_revision", "revision"}
        row = db.get(CustomerPriceSettingsSnapshot, snapshot["snapshot_id"])
        row.settings_json = "{}"
        with pytest.raises(ValueError, match="immutable"):
            db.commit()


@pytest.mark.parametrize("existing", [False, True])
def test_simultaneous_saves_have_one_winner(tmp_path, existing):
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}", connect_args={"timeout": 15})
    create_tables(engine)
    body = service._default("huaxing", "buzzbee").model_dump(include={"revision", "materials", "rates", "texts"})
    if existing:
        with Session(engine) as db:
            saved = service.update_settings(db, "huaxing", "buzzbee", CustomerPriceSettingsUpdate(**body), user())
            body["revision"] = saved.revision
    barrier = Barrier(2)
    def save(value):
        request = CustomerPriceSettingsUpdate(**body)
        request.rates["detail_multiplier"] = value
        with Session(engine) as db:
            barrier.wait()
            try:
                return service.update_settings(db, "huaxing", "buzzbee", request, user()).revision
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(save, [1.1, 1.2]))
    assert sorted(results) == [2 if existing else 1, 409]
    engine.dispose()


def test_migration_database_guards(tmp_path):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20260922_0118_customer_price_settings.py"
    spec = importlib.util.spec_from_file_location("pricing_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "20260917_0117"
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
            module.upgrade()
        connection.execute(text("INSERT INTO customer_price_settings_snapshots VALUES ('s','huaxing','buzzbee',0,'{}','','u')"))
        for statement in ("UPDATE customer_price_settings_snapshots SET revision=1", "DELETE FROM customer_price_settings_snapshots"):
            with pytest.raises(DatabaseError, match="immutable"):
                connection.execute(text(statement))
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="Cannot discard"):
                module.downgrade()
    engine.dispose()


def test_snapshot_and_update_race_preserves_the_selected_revision(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot-race.db'}", connect_args={"timeout": 15})
    create_tables(engine)
    body = service._default("huaxing", "buzzbee").model_dump(include={"revision", "materials", "rates", "texts"})
    with Session(engine) as db:
        service.update_settings(db, "huaxing", "buzzbee", CustomerPriceSettingsUpdate(**body), user())
    body["revision"] = 1
    body["rates"]["detail_multiplier"] = 2
    barrier = Barrier(2)
    def snapshot():
        with Session(engine) as db:
            barrier.wait()
            try:
                return service.create_snapshot(db, "huaxing", "buzzbee", 1, user())
            except HTTPException as exc:
                assert exc.status_code == 409
                return None
    def save():
        with Session(engine) as db:
            barrier.wait()
            return service.update_settings(db, "huaxing", "buzzbee", CustomerPriceSettingsUpdate(**body), user())
    with ThreadPoolExecutor(max_workers=2) as executor:
        snap_future, save_future = executor.submit(snapshot), executor.submit(save)
        snap, saved = snap_future.result(), save_future.result()
    assert saved.revision == 2
    if snap:
        assert snap.revision == 1
        assert snap.rates["detail_multiplier"] == 1.05
    engine.dispose()
