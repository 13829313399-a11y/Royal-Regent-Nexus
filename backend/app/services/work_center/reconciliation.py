"""Bounded source scan; explicit caller transaction, no commits and no old-row writes."""
import hashlib
import json
from sqlalchemy import select, func


def reconcile(db, *, apply=False, batch_size=200):
    from app.models.auth import AuthRegistrationRequest, AuthPasswordResetRequest, SystemNotification
    from app.models.molding_sample import MoldingSampleOrder, MoldingSampleNotification
    from app.models.internal_quote import InternalQuote
    from app.models.carton_supplier_portal import SupplierShipment
    from app.services.work_center.registry import current_query
    from app.services.work_center.projection import reconcile_sources
    sources = (("molding", MoldingSampleOrder), ("internal_quote", InternalQuote),
               ("carton_supplier", SupplierShipment), ("account_requests", AuthRegistrationRequest),
               ("account_requests", AuthPasswordResetRequest), ("identity", SystemNotification))
    report = {"mode": "apply" if apply else "dry_run", "sources": {}, "projection": {"created": 0, "updated": 0, "unchanged": 0},
              "legacy": {"system_total": db.scalar(select(func.count()).select_from(SystemNotification)),
                         "molding_total": db.scalar(select(func.count()).select_from(MoldingSampleNotification)),
                         "orphaned_molding": db.scalar(select(func.count()).select_from(MoldingSampleNotification).outerjoin(MoldingSampleOrder, MoldingSampleOrder.id == MoldingSampleNotification.order_id).where(MoldingSampleOrder.id.is_(None))),
                         "invalid_system_payload": 0, "unsupported_system_type": 0}, "personal_states_changed": 0}
    supported = {"user_registration", "password_reset", "internal_quote", "carton_supplier_shipment", "identity_changed"}
    for item in db.execute(select(SystemNotification.type, SystemNotification.payload_json).execution_options(yield_per=batch_size)):
        try: json.loads(item.payload_json or "{}")
        except (ValueError, TypeError): report["legacy"]["invalid_system_payload"] += 1
        if item.type not in supported: report["legacy"]["unsupported_system_type"] += 1
    current = current_query(db, None)
    report["current_by_module"] = dict(db.execute(select(current.c.module, func.count()).group_by(current.c.module)).all())
    report["current_by_kind_lifecycle"] = [dict(row) for row in db.execute(select(current.c.module, current.c.kind, current.c.lifecycle,
        func.count().label("count")).group_by(current.c.module, current.c.kind, current.c.lifecycle)).mappings()]
    canonical = hashlib.sha256()
    for ident in db.scalars(select(current.c.id).order_by(current.c.id).execution_options(yield_per=batch_size)):
        canonical.update((ident + "\n").encode())
    report["source_canonical_sha256"] = canonical.hexdigest()
    report["legacy"]["system_status_counts"] = dict(db.execute(select(SystemNotification.status, func.count()).group_by(SystemNotification.status)).all())
    report["legacy"]["molding_status_counts"] = dict(db.execute(select(MoldingSampleNotification.status, func.count()).group_by(MoldingSampleNotification.status)).all())
    report["legacy"]["read_evidence_policy"] = "Original shared status/read_at remains in source tables; never copied into personal read history."
    for module, model in sources:
        query = select(model.id).order_by(model.id)
        if module == "identity": query = query.where(model.type == "identity_changed")
        report["sources"][model.__tablename__] = db.scalar(select(func.count()).select_from(query.subquery()))
        if not apply: continue
        last = None
        while True:
            page = list(db.scalars((query.where(model.id > last) if last else query).limit(batch_size)))
            if not page: break
            counts = reconcile_sources(db, {module: page}, legacy=True)
            for name, count in counts.items(): report["projection"][name] += count
            last = page[-1]
            db.expire_all()
    return report
