"""Name-only business customer intake; stable source identities, no name guessing.

Private master records retain source ownership and deletion tombstones. They are
not editable through the public entry-assistance master-data API.
"""
from hashlib import sha256
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_master import CartonMasterRecord as Record
from app.models.carton_procurement import CartonCustomer, CartonImportBatch

KIND = "BUSINESS_CUSTOMER"


def catalog(factory):
    # The order center owns the supported customer/factory catalogue.
    from app.api.customer_order import CUSTOMER_FACTORY_OPTIONS, CUSTOMER_NAMES
    return {code: CUSTOMER_NAMES[code] for code, factories in CUSTOMER_FACTORY_OPTIONS.items()
            if factory in factories and code in CUSTOMER_NAMES}


def records(db, factory):
    return list(db.scalars(select(Record).where(Record.factory_id == factory, Record.kind == KIND)))


def decorate(db, factory, customers):
    sources = {json.loads(r.data_json)["customer_id"]: r for r in records(db, factory) if r.status == "ACTIVE"}
    for customer in customers:
        source = sources.get(customer.id)
        customer.business_customer_code = source.code if source else ""
        customer.business_customer_name = json.loads(source.data_json)["source_name"] if source else ""
    return customers


def source_code(db, factory, customer_id):
    return next((r.code for r in records(db, factory)
                 if r.status == "ACTIVE" and json.loads(r.data_json)["customer_id"] == customer_id), "")


def _historical_links(db, factory):
    links = {}
    for batch in db.scalars(select(CartonImportBatch).where(
            CartonImportBatch.factory_id == factory, CartonImportBatch.import_type == "WEEKLY_SCHEDULE")):
        summary = json.loads(batch.parse_summary_json or "{}")
        source = summary.get("business_source", {})
        if source.get("system") == "CUSTOMER_ORDER_CENTER" and source.get("customer_code"):
            target = summary.get("schedule_customer", {}).get("customer_code")
            if target:
                links.setdefault(source["customer_code"], set()).add(target)
    return links


def _historical_customer(db, factory, code):
    """Retain proven old handoffs, never infer a link from similar names."""
    linked_codes = _historical_links(db, factory).get(code, set())
    if len(linked_codes) > 1:
        raise HTTPException(409, "该业务客户存在多个历史仓库客户关联，请先核对历史同步记录")
    if linked_codes:
        return db.scalar(select(CartonCustomer).where(CartonCustomer.factory_id == factory,
            CartonCustomer.customer_code == next(iter(linked_codes))))
    return None


def _unique_name_customer(db, factory, name):
    normalize = lambda value: " ".join(value.split()).casefold()
    matches = [customer for customer in db.scalars(select(CartonCustomer).where(CartonCustomer.factory_id == factory))
               if normalize(customer.customer_name) == normalize(name)]
    if len(matches) != 1:
        return None
    # A name never steals another business source's established identity.
    bound_ids = {json.loads(r.data_json)["customer_id"] for r in records(db, factory)}
    if matches[0].id in bound_ids:
        return None
    # Old installations may have handoff evidence before private bindings exist.
    # Reserve those targets regardless of catalogue iteration or handoff order.
    if any(matches[0].customer_code in codes for codes in _historical_links(db, factory).values()):
        return None
    return matches[0]


def ensure(db, factory, code, user):
    """Caller holds factory lock and current source permission; never commits."""
    from app.services.carton_procurement import _audit, now_text
    name = catalog(factory).get(code)
    if not name:
        raise HTTPException(422, "该业务客户不属于当前厂区")
    source = next((r for r in records(db, factory) if r.code == code), None)
    if source:
        if source.status != "ACTIVE":
            return None
        customer = db.get(CartonCustomer, json.loads(source.data_json)["customer_id"])
        if customer is None or customer.factory_id != factory:
            raise HTTPException(409, "业务来源客户关联已失效，请联系主管核对")
        return customer
    customer = _historical_customer(db, factory, code)
    if customer is None:
        customer = _unique_name_customer(db, factory, name)
    timestamp = now_text()
    created = customer is None
    if customer is None:
        # Independent from display names and ordinary warehouse customer codes.
        customer = CartonCustomer(id="CCU-" + uuid4().hex, factory_id=factory,
            customer_code="BIZ-" + uuid4().hex[:20].upper(), customer_name=name,
            country_region="", contact_name="", contact_phone="", note="", status="ACTIVE", revision=1,
            created_by=user.id, created_by_name=user.display_name,
            updated_by=user.id, updated_by_name=user.display_name, created_at=timestamp, updated_at=timestamp)
        db.add(customer)
    elif any(json.loads(r.data_json)["customer_id"] == customer.id for r in records(db, factory)):
        raise HTTPException(409, "多个业务客户曾同步到同一仓库客户，请先核对历史关联")
    source = Record(id="CMD-" + uuid4().hex, factory_id=factory, kind=KIND,
        identity=sha256(code.encode()).hexdigest(), code=code, customer_code=customer.customer_code,
        data_json=json.dumps({"customer_id": customer.id, "source_name": name}, ensure_ascii=False),
        status="ACTIVE", preferred=0, revision=1, maintained=1, updated_at=timestamp)
    db.add(source)
    _audit(db, user, factory, "BUSINESS_CUSTOMER_IMPORTED", "carton_customer", customer.id,
        {"business_customer_code": code, "source_name": name, "created": created})
    db.flush()
    return customer


def synchronize(db, factory, user):
    before = {r.code for r in records(db, factory)}
    for code in catalog(factory):
        ensure(db, factory, code, user)
    return len({r.code for r in records(db, factory)} - before)


def resolve(db, factory, code, user):
    customer = ensure(db, factory, code, user)
    if customer is None:
        raise HTTPException(422, "该业务来源客户已在仓库删除，本次未自动恢复；请联系纸箱主管核对客户资料")
    if customer.status != "ACTIVE":
        raise HTTPException(422, "该业务来源客户已在仓库停用，请启用后重试同步")
    return customer


def remember_deletion(db, factory, customer):
    from app.services.carton_procurement import now_text
    for source in records(db, factory):
        if json.loads(source.data_json)["customer_id"] == customer.id:
            source.status = "INACTIVE"
            source.revision += 1
            source.updated_at = now_text()
