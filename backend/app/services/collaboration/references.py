"""Read-time business projections; never persist an authority-bearing snapshot."""
from urllib.parse import urlencode, quote
from app.models.molding_sample import MoldingSampleOrder
from app.models.internal_quote import InternalQuote
from sqlalchemy import select


def preload(db, references):
    rows = {}
    for kind, model in (("molding_sample", MoldingSampleOrder), ("internal_quote", InternalQuote)):
        ids = {r["resource_id"] for r in references if r["resource_type"] == kind}
        if ids:
            rows.update({(kind, row.id): row for row in db.scalars(select(model).where(model.id.in_(ids)))})
    return rows


def project(db, user, reference, preloaded=None):
    unavailable = {"available": False, "label": "该业务记录当前不可查看"}
    kind, rid, factory = reference["resource_type"], reference["resource_id"], reference["factory_id"]
    if kind == "molding_sample":
        from app.services.molding_sample import has_order_read_access, order_authorization_factory_id
        row = preloaded.get((kind, rid)) if preloaded is not None else db.get(MoldingSampleOrder, rid)
        if not row or row.factory_id != factory or not has_order_read_access(user, row):
            return unavailable
        route_factory = order_authorization_factory_id(user, row)
        path = "/modules/molding-sample?" + urlencode({"factory": route_factory, "order_id": row.id, "view": "detail"})
        return dict(available=True, resource_type=kind, resource_id=rid, factory_id=factory,
                    title=row.doc_number or row.order_number or "啤办单", status=row.status, label="啤办单", url=path)
    if kind == "internal_quote":
        from app.services.internal_quote import ALL_QUOTE_DEPARTMENTS
        from app.services.business_authz import has_permission_for_departments
        row = preloaded.get((kind, rid)) if preloaded is not None else db.get(InternalQuote, rid)
        if not row or row.factory_id != factory or not has_permission_for_departments(user, "internal_quote:read", factory, ALL_QUOTE_DEPARTMENTS):
            return unavailable
        return dict(available=True, resource_type=kind, resource_id=rid, factory_id=factory,
                    title=row.quote_no, status=row.status, label="内部报价",
                    url=f"/modules/sales-business/internal-quote-desk/{quote(rid, safe='')}/collaboration?{urlencode({'factory': factory})}")
    return unavailable
