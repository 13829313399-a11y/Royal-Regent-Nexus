"""Factory-owned pricing inputs. Totals are never accepted by this API."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.customer_price_settings import CustomerPriceSettings, CustomerPriceSettingsSnapshot
from app.schemas.customer_price_settings import (
    CustomerPriceSettingsOut, CustomerPriceSettingsUpdate, CustomerPriceSettingsSnapshotOut,
)
from app.services.auth import AuthContext, add_auth_audit, can, now_text, time_window_is_active
from app.services.business_authz import is_wildcard_super_admin


DEFAULTS_PATH = Path(__file__).resolve().parents[3] / "shared" / "customerPriceDefaults.json"
DEFINITIONS = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _authorize(db, user, factory_id, permission="customer_price:settings_read"):
    department = user.profile.primary_department.strip() if user.profile else ""
    sales = department == "sales-business" if department else any(
        grant.department == "sales-business" and time_window_is_active(grant.valid_from, grant.valid_until)
        for grant in user.grants
    )
    if (sales or is_wildcard_super_admin(user)) and can(user, permission, factory_id, "sales-business"):
        return
    add_auth_audit(db, "permission_denied", user.username, user.id,
                   f"{permission}@{factory_id}/sales-business")
    db.commit()
    raise HTTPException(403, "仅限获授权的业务人员访问客户报价基础资料")


def _definition(factory_id, customer_id):
    definition = DEFINITIONS.get(customer_id)
    if not definition or definition["factoryId"] != factory_id:
        raise HTTPException(404, "该厂区未配置此客户的报价资料")
    return definition


def _default(factory_id, customer_id):
    definition = _definition(factory_id, customer_id)
    return CustomerPriceSettingsOut(
        factory_id=factory_id, customer_id=customer_id, revision=0,
        materials=definition["materials"],
        rates={key: row["value"] for key, row in definition["rates"].items()},
        texts={key: row["value"] for key, row in definition["texts"].items()},
        rate_definitions={key: {k: v for k, v in row.items() if k != "value"}
                          for key, row in definition["rates"].items()},
        text_definitions={key: {"label": row["label"]} for key, row in definition["texts"].items()},
        updated_at="", updated_by_name="",
    )


def _out(row):
    # Stored complete responses retain their own definitions and default values.
    return CustomerPriceSettingsOut.model_validate_json(row.settings_json)


def _validate(payload, definition):
    if set(payload.rates) != set(definition["rates"]):
        raise HTTPException(422, "报价参数必须完整且不能包含未知参数")
    if set(payload.texts) != set(definition["texts"]):
        raise HTTPException(422, "报价文字必须完整且不能包含未知字段")
    for key, value in payload.rates.items():
        kind = definition["rates"][key]["kind"]
        if ((kind in {"multiplier", "exchange"} and value <= 0)
                or (kind == "rate" and not 0 <= value <= 1)
                or (kind == "price" and value < 0)):
            raise HTTPException(422, f"报价参数数值无效：{key}")
    if any(len(value) > 10000 for value in payload.texts.values()):
        raise HTTPException(422, "报价文字不能超过10000字")


def _condition(factory_id, customer_id, revision):
    return (
        CustomerPriceSettings.factory_id == factory_id,
        CustomerPriceSettings.customer_id == customer_id,
        CustomerPriceSettings.revision == revision,
    )


def _conflict(db):
    db.rollback()
    raise HTTPException(409, "客户报价资料已更新，请刷新后重试")


def _audit(db, user, action, output, request=None):
    add_auth_audit(db, action, user.username, user.id, _json(output), request)


def get_settings(db: Session, factory_id: str, customer_id: str, user: AuthContext):
    _authorize(db, user, factory_id)
    _definition(factory_id, customer_id)
    row = db.get(CustomerPriceSettings, (factory_id, customer_id))
    return _out(row) if row else _default(factory_id, customer_id)


def update_settings(db: Session, factory_id: str, customer_id: str,
                    payload: CustomerPriceSettingsUpdate, user: AuthContext, request: Request | None = None):
    _authorize(db, user, factory_id)
    _authorize(db, user, factory_id, "customer_price:settings_manage")
    definition = _definition(factory_id, customer_id)
    _validate(payload, definition)
    result = CustomerPriceSettingsOut.model_validate({
        **_default(factory_id, customer_id).model_dump(),
        **payload.model_dump(), "revision": payload.revision + 1,
        "updated_at": now_text(), "updated_by_name": user.display_name,
    })
    values = dict(revision=result.revision, settings_json=result.model_dump_json(),
                  updated_at=result.updated_at, updated_by=user.id, updated_by_name=user.display_name)
    try:
        changed = db.execute(update(CustomerPriceSettings).where(
            *_condition(factory_id, customer_id, payload.revision)
        ).values(**values).execution_options(synchronize_session=False)).rowcount
        if not changed:
            if payload.revision != 0:
                _conflict(db)
            # Composite PK makes two simultaneous first saves conflict atomically.
            db.add(CustomerPriceSettings(factory_id=factory_id, customer_id=customer_id, **values))
            db.flush()
        _audit(db, user, "customer_price_settings_updated", {
            "factory_id": factory_id, "customer_id": customer_id,
            "previous_revision": payload.revision, "revision": result.revision,
        }, request)
        db.commit()
        db.expire_all()
    except IntegrityError:
        _conflict(db)
    return result


def create_snapshot(db: Session, factory_id: str, customer_id: str, revision: int,
                    user: AuthContext, request: Request | None = None):
    _authorize(db, user, factory_id)
    _authorize(db, user, factory_id, "customer_price:import_internal_quote")
    _definition(factory_id, customer_id)
    try:
        # A conditional no-op UPDATE locks the matched row until snapshot commit.
        # Reading then inserting would race a concurrent pricing update.
        changed = db.execute(update(CustomerPriceSettings).where(
            *_condition(factory_id, customer_id, revision)
        ).values(revision=revision).execution_options(synchronize_session=False)).rowcount
        if not changed:
            if revision != 0:
                _conflict(db)
            default = _default(factory_id, customer_id)
            db.add(CustomerPriceSettings(
                factory_id=factory_id, customer_id=customer_id, revision=0,
                settings_json=default.model_dump_json(), updated_at="", updated_by="", updated_by_name="",
            ))
            db.flush()
        db.expire_all()
        current = _out(db.get(CustomerPriceSettings, (factory_id, customer_id)))
        snapshot_id = str(uuid4())
        db.add(CustomerPriceSettingsSnapshot(
            id=snapshot_id, factory_id=factory_id, customer_id=customer_id, revision=revision,
            settings_json=current.model_dump_json(), created_at=now_text(), created_by=user.id,
        ))
        _audit(db, user, "customer_price_settings_snapshotted", {
            "snapshot_id": snapshot_id, "factory_id": factory_id, "customer_id": customer_id, "revision": revision,
        }, request)
        db.commit()
    except IntegrityError:
        _conflict(db)
    return CustomerPriceSettingsSnapshotOut(**current.model_dump(), snapshot_id=snapshot_id)


def get_snapshot(db: Session, snapshot_id: str, user: AuthContext):
    row = db.get(CustomerPriceSettingsSnapshot, snapshot_id)
    if row is None:
        raise HTTPException(404, "报价资料快照不存在")
    _authorize(db, user, row.factory_id)
    return CustomerPriceSettingsSnapshotOut(**_out(row).model_dump(), snapshot_id=row.id)
