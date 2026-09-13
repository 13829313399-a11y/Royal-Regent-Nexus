"""Read-only historical selection and atomic, independent new-quote seeding."""
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import defer

from app.models.internal_quote import InternalQuote, InternalQuoteAttachment, InternalQuoteReferenceSet, InternalQuoteSection
from app.services.auth import now_text
from app.services.business_authz import ensure_permission_for_departments
from app.services.internal_quote_calculator import canonical_json, content_hash
from app.services.internal_quote_prefill import _source_keys


def ensure_history_access(db, user, factory_id):
    for permission in ("internal_quote:read", "internal_quote:create", "internal_quote:clone"):
        ensure_permission_for_departments(db, user, permission, factory_id, ("sales-business", "engineering"))


def _object(value):
    result = json.loads(value or "{}")
    return result if isinstance(result, dict) else {}


def _rows(value):
    return [row for row in (value or []) if isinstance(row, dict)] if isinstance(value, list) else []


def _justplay(quote):
    return quote.factory_id == "huakang-b" and "".join(c for c in quote.customer.lower() if c.isalnum()) == "justplay"


@dataclass
class HistorySource:
    quote: InternalQuote
    sections: list
    attachments: list

    @cached_property
    def payloads(self):
        return {section.department: _object(section.payload_json) for section in self.sections if section.is_required}

    @cached_property
    def components(self):
        if not _justplay(self.quote):
            return []
        return _rows(self.payloads.get("sales", {}).get("pricing_components")) or [{"id": "__legacy_main__", "name": "主体（旧版整款）"}]

    @cached_property
    def fingerprint(self):
        return content_hash({
            "quote_id": self.quote.id,
            "header": [self.quote.header_revision, self.quote.reference_snapshot_id, self.quote.status],
            "sections": [[s.department, s.revision, s.is_required, s.payload_json] for s in self.sections],
            "attachments": [[a.id, a.department, a.sha256] for a in self.attachments],
        })

    def describe(self, component_id=""):
        q = self.quote
        return {"quote_id": q.id, "quote_no": q.quote_no, "batch_quote_no": q.batch_quote_no,
                "product_name": q.product_name, "customer": q.customer, "region_code": q.region_code,
                "version_label": q.version_label, "status": q.status, "qty": q.qty,
                "fingerprint": self.fingerprint, "component_id": component_id,
                "component_name": next((str(c.get("name")) for c in self.components if c.get("id") == component_id), ""),
                "is_justplay": _justplay(q), "components": self.components,
                "component_sections": self.component_section_map,
                "participating_sections": [s.department for s in self.sections if s.is_required],
                "updated_at": q.updated_at}

    @cached_property
    def component_section_map(self):
        return {str(c["id"]): self.component_sections(str(c["id"])) for c in self.components}

    def component_sections(self, component_id):
        result = []
        for code, fields in ROW_FIELDS.items():
            payload = self.payloads.get(code, {})
            if code == "electronic" and "quote_groups" in payload:
                from app.services.internal_quote_electronic import electronic_quote_groups
                for group in electronic_quote_groups(payload):
                    normalized = _normalized_rows(code, group, Decimal("1"))
                    has_rows = bool(_select_tree(normalized.get("components"), self, component_id))
                    has_expenses = component_id == str(self.components[0]["id"]) and any(
                        _decimal(group.get(stem + suffix)) > 0 for stem in ("bonding", "smt", "labor", "testing", "packaging") for suffix in ("_rmb", "_hkd"))
                    if has_rows or has_expenses:
                        result.append(code)
                        break
                continue
            if payload.get("quote_mode") == "quick" and code in {"painting", "electronic", "sewing"}:
                candidates = [payload.get("quick_quote", {})] if code == "painting" else _rows(payload.get("quick_quotes"))
            else:
                candidates = [row for field in fields for row in _rows(payload.get(field))]
            if any(not _shared(code, row) for row in _select_tree(candidates, self, component_id)):
                result.append(code)
            elif code == "electronic" and component_id == str(self.components[0]["id"]) and any(
                _decimal(payload.get(stem + suffix)) > 0 for stem in ("bonding", "smt", "labor", "testing", "packaging") for suffix in ("_rmb", "_hkd")):
                result.append(code)
        return result


def _load_source(db, quote):
    return HistorySource(quote, list(db.scalars(select(InternalQuoteSection).where(
        InternalQuoteSection.quote_id == quote.id).order_by(InternalQuoteSection.department)).all()),
        list(db.scalars(select(InternalQuoteAttachment).options(defer(InternalQuoteAttachment.content)).where(
            InternalQuoteAttachment.quote_id == quote.id).order_by(InternalQuoteAttachment.id)).all()))


def list_history_products(db, user, factory_id, *, keyword="", customer="", region_code="", page=1, page_size=10):
    ensure_history_access(db, user, factory_id)
    filters = [InternalQuote.factory_id == factory_id, InternalQuote.archived_at == ""]
    if keyword.strip():
        term = "%" + keyword.strip().replace("%", "\\%").replace("_", "\\_") + "%"
        filters.append(or_(*(column.ilike(term, escape="\\") for column in (
            InternalQuote.quote_no, InternalQuote.batch_quote_no, InternalQuote.product_name, InternalQuote.customer))))
    if customer:
        filters.append(InternalQuote.customer == customer)
    if region_code:
        filters.append(InternalQuote.region_code == region_code)
    total = db.scalar(select(func.count()).select_from(InternalQuote).where(*filters)) or 0
    quotes = db.scalars(select(InternalQuote).where(*filters).order_by(
        InternalQuote.updated_at.desc(), InternalQuote.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_load_source(db, quote).describe() for quote in quotes], "total": total,
            "page": page, "page_size": page_size}


def prepare_history_sources(db, payload, user):
    refs = [ref for product in payload.products for ref in [product.history_source, *(product.component_sources or [])] if ref]
    if not refs:
        return {}
    ensure_history_access(db, user, payload.factory_id)
    sources = {}
    # Lock in stable order so a concurrent source edit cannot change the selected snapshot mid-copy.
    for quote_id in sorted({ref.quote_id for ref in refs}):
        quote = db.scalar(select(InternalQuote).where(InternalQuote.id == quote_id,
                          InternalQuote.factory_id == payload.factory_id).with_for_update())
        if quote is None or quote.archived_at:
            raise HTTPException(404, "历史产品不存在、已归档或不属于当前厂区")
        sources[quote_id] = _load_source(db, quote)
    target_justplay = payload.factory_id == "huakang-b" and "".join(c for c in payload.customer.lower() if c.isalnum()) == "justplay"
    for ref in refs:
        source = sources[ref.quote_id]
        if source.fingerprint != ref.fingerprint:
            raise HTTPException(409, f"历史产品 {source.quote.product_name} 已更新，请重新选择后建单")
        if _justplay(source.quote) != target_justplay:
            raise HTTPException(400, "普通客与 JustPlay 的报价结构不同，不能互相引用")
        if ref.component_id and ref.component_id not in {str(c.get("id")) for c in source.components}:
            raise HTTPException(400, "所选配件不属于该历史产品")
    for product in payload.products:
        if target_justplay and product.history_source and product.component_sources is None:
            raise HTTPException(400, "JustPlay 整款引用必须明确各分项来源，请重新选择历史产品")
    return sources


def _clean(value):
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()
                if key not in {"import_batch_id", "import_source_batch_id", "source_sha256", "history_sources", "markup_override"}}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    return deepcopy(value)


def history_price_snapshot(db, product, sources, current):
    result = deepcopy(current)
    refs = [ref for ref in [product.history_source, *(product.component_sources or [])] if ref]
    if not refs or product.history_reference_mode == "current":
        return result
    merged = {}
    for quote_id in dict.fromkeys(ref.quote_id for ref in refs):
        source = sources[quote_id]
        reference = db.get(InternalQuoteReferenceSet, source.quote.reference_snapshot_id)
        if not reference or reference.quote_id != quote_id:
            raise HTTPException(409, "历史产品缺少冻结参考表，请选择使用当前参考表后重试")
        old = _object(reference.snapshot_json)
        for field in ("material_prices", "legacy_material_prices", "machine_prices"):
            values = old.get(field)
            if not isinstance(values, (dict, list)):
                continue
            entries = values.items() if isinstance(values, dict) else (
                (str(row.get("range") or row.get("machine_code") or row.get("machine") or index), row)
                for index, row in enumerate(_rows(values)))
            target = merged.setdefault(field, {})
            for key, value in entries:
                if key in target and canonical_json(target[key]) != canonical_json(value):
                    raise HTTPException(409, f"历史产品的材料/机型参考价存在冲突（{key}），请为本款选择‘当前参考表’后重新建单")
                target[key] = deepcopy(value)
    for field, values in merged.items():
        result[field] = list(values.values()) if field == "machine_prices" else values
    return result


def _assigned(row, source, inherited=""):
    valid = {str(c.get("id")) for c in source.components}
    value = str(row.get("pricing_component_id") or inherited)
    return value if value in valid else str(source.components[0].get("id")) if source.components else ""


def _select_tree(rows, source, component_id, inherited=""):
    selected = []
    for original in _rows(rows):
        owner = _assigned(original, source, inherited)
        children = _select_tree(original.get("children"), source, component_id, owner)
        if owner == component_id:
            row = deepcopy(original)
            if "children" in row:
                row["children"] = children
            selected.append(row)
        else:
            for child in children:
                if not child.get("item") and original.get("item"):
                    child["item"] = original["item"]
            selected.extend(children)
    return selected


def _shared(code, row):
    if code == "engineering":
        return row.get("category") == "packaging"
    if code == "assembly":
        return row.get("category") in {"packaging", "mixed_pack"} or any(
            term in str(row.get("name", "")).lower() for term in ("包装", "pack"))
    return False


ROW_FIELDS = {"engineering": ("materials", "molds"), "molding": ("injection_lines", "blow_lines", "caixing_tool_plan_rows"),
              "electronic": ("components",), "painting": ("rows",), "sewing": ("groups",),
              "assembly": ("groups",), "slush": ("lines",), "hair": ("lines",),
              "sales": ("customer_supplied_materials",)}


def _decimal(value):
    return Decimal(str(value or 0))


def _normalized_rows(code, payload, fx):
    """Normalize mixed quick/detail sources into existing editable detail contracts."""
    result = deepcopy(payload)
    if result.get("quote_mode") != "quick":
        return result
    if code == "electronic":
        result["components"] = [{**r, "quantity": 1, "children": []} for r in _rows(result.get("quick_quotes"))]
    elif code == "sewing":
        result["groups"] = [{**r, "name": r.get("doll_name", "历史车缝"), "category": "clothes", "materials": [],
                             "labor_rmb": str(_decimal(r.get("unit_price_hkd")) * fx)} for r in _rows(result.get("quick_quotes"))]
    elif code == "painting":
        r = result.get("quick_quote") or {}
        result["rows"] = [{**r, "name": "历史快捷喷油（人工及含税油漆）", "position": "历史快捷报价",
                           "cost_allocation": "direct",
                           "remark": "沿用快捷报价拆分：散枪为人工，油色为含13%税油漆；不按70%/30%分摊。",
                           "operations": {"spray": {"quantity": 1, "unit_price_hkd": r.get("spray_labor_hkd", 0)},
                                          "paint": {"quantity": 1, "unit_price_hkd": str(_decimal(r.get("paint_hkd")) * Decimal("1.13"))}}}]
    result["quote_mode"] = "detail"
    result.pop("quick_quotes", None)
    result.pop("quick_quote", None)
    return result


def _rebind(value, component_id):
    if isinstance(value, dict):
        result = {key: _rebind(item, component_id) for key, item in value.items()}
        if "pricing_component_id" in result:
            result["pricing_component_id"] = component_id
        return result
    if isinstance(value, list):
        return [_rebind(item, component_id) for item in value]
    return value


def _select_electronic_groups(original, source, source_component, target_component, fx, prefix):
    """Keep margins and shared expense allocation local to each source quote."""
    from app.services.internal_quote_electronic import electronic_quote_groups
    selected = []
    def raw_cost(rows):
        return sum((_decimal(row.get("quantity", 1)) * (_decimal(row["unit_price_rmb"]) if "unit_price_rmb" in row
                   else _decimal(row.get("unit_price_hkd")) * fx) + raw_cost(_rows(row.get("children"))) for row in _rows(rows)), Decimal(0))
    for index, group in enumerate(electronic_quote_groups(original)):
        normalized = _normalized_rows("electronic", group, fx)
        rows = _select_tree(normalized.get("components"), source, source_component)
        all_cost, picked_cost = raw_cost(normalized.get("components")), raw_cost(rows)
        share = picked_cost / all_cost if all_cost else Decimal(int(source_component == str(source.components[0]["id"])))
        picked = _rebind(_clean(normalized), target_component)
        picked.update(id="history-" + content_hash({"source": prefix, "group": group["id"]})[:32], components=[{**_rebind(_clean(row), target_component), "pricing_component_id": target_component} for row in rows])
        picked.pop("quick_quotes", None)
        has_expenses = False
        for stem in ("bonding", "smt", "labor", "testing", "packaging", "tax_credit_difference"):
            for suffix in ("_rmb", "_hkd"):
                key = stem + suffix
                if key in picked:
                    picked[key] = str(_decimal(picked[key]) * share)
                    has_expenses |= bool(_decimal(picked[key]))
        if rows or has_expenses:
            selected.append(picked)
    return selected


def seed_history_product(db, quote, product, sources, initial_payloads, snapshot, user):
    """Return payloads and source evidence; attachments are copied in the caller's transaction."""
    if not product.history_source and not any(product.component_sources or []):
        return initial_payloads, [], set()
    whole = sources[product.history_source.quote_id] if product.history_source else None
    payloads = _clean(whole.payloads) if whole else {}
    evidence = []
    attachment_jobs = []
    required = set()
    fx = _decimal(snapshot.get("fx", {}).get("rmb_hkd", ".85"))

    def collect(source, ref, target_component=""):
        if not ref.component_id:
            required.update(s.department for s in source.sections if s.is_required)
        description = source.describe(ref.component_id)
        description.pop("components", None)
        description.pop("component_sections", None)
        evidence.append({**description, "target_component_id": target_component,
                         "reference_snapshot_id": source.quote.reference_snapshot_id,
                         "section_revisions": {s.department: s.revision for s in source.sections},
                         "reference_price_mode": product.history_reference_mode})

    if whole:
        collect(whole, product.history_source)
        quote.cloned_from_quote_id = whole.quote.id
        # Full-product support documents and ordinary product images are safe independent copies.
        attachment_jobs.extend((whole, a, a.department) for a in whole.attachments
                               if not a.department.startswith("component-image:") and
                               (a.department != "product-image" or not _justplay(quote)))
    if _justplay(quote):
        grouped_electronic = any("quote_groups" in sources[ref.quote_id].payloads.get("electronic", {})
                                 for ref in (product.component_sources or []) if ref)
        # Shared packaging belongs only to the complete-product source, never to each accessory.
        for code, fields in ROW_FIELDS.items():
            base = payloads.setdefault(code, {})
            for field in fields:
                base[field] = [row for row in _rows(base.get(field)) if _shared(code, row)]
            base.pop("quick_quotes", None)
            base.pop("quick_quote", None)
            if code in {"electronic", "painting", "sewing"}:
                base["quote_mode"] = "detail"
        electronic = payloads["electronic"]
        electronic.pop("quote_groups", None)
        if grouped_electronic:
            electronic.clear()
            electronic["quote_groups"] = []
        for field in list(electronic):
            if field.endswith(("_rmb", "_hkd")):
                electronic.pop(field)
        mold_links = []
        for index, ref in enumerate(product.component_sources or []):
            if ref is None:
                continue
            source = sources[ref.quote_id]
            target_component = f"component-{index + 1:02d}"
            collect(source, ref, target_component)
            selected_payloads = {}
            source_molds = _rows(source.payloads.get("engineering", {}).get("molds"))
            # Match by source index rather than object identity (payloads are decoded on access).
            old_keys = {i: key for i, key in enumerate(_source_keys(source_molds))}
            for code, fields in ROW_FIELDS.items():
                original = source.payloads.get(code, {})
                if code == "electronic" and grouped_electronic:
                    groups = _select_electronic_groups(original, source, ref.component_id, target_component, fx, source.quote.id)
                    for group in groups:
                        existing = next((item for item in electronic["quote_groups"] if item["id"] == group["id"]), None)
                        if existing is None:
                            electronic["quote_groups"].append(deepcopy(group))
                        else:
                            existing["components"].extend(group["components"])
                            for stem in ("bonding", "smt", "labor", "testing", "packaging", "tax_credit_difference"):
                                for suffix in ("_rmb", "_hkd"):
                                    key = stem + suffix
                                    if key in group:
                                        existing[key] = str(_decimal(existing.get(key)) + _decimal(group[key]))
                    selected_payloads[code] = {"quote_groups": groups}
                    if groups:
                        required.add(code)
                    continue
                normalized = _normalized_rows(code, original, fx)
                selected_payloads[code] = {}
                for field in fields:
                    rows = _select_tree(normalized.get(field), source, ref.component_id)
                    rows = [row for row in rows if not _shared(code, row)]
                    if rows:
                        required.add(code)
                    for row in rows:
                        if code == "engineering" and field == "molds":
                            source_index = next((i for i, mold in enumerate(source_molds) if mold == row), None)
                            mold_links.append((len(payloads[code][field]), source.quote.id, target_component, old_keys.get(source_index, "")))
                        rebound = _rebind(_clean(row), target_component)
                        rebound["pricing_component_id"] = target_component
                        if code == "molding" and rebound.get("engineering_source_key"):
                            rebound["_history_link"] = [source.quote.id, target_component, rebound["engineering_source_key"]]
                        payloads[code][field].append(rebound)
                        selected_payloads[code].setdefault(field, []).append(rebound)
                if code == "electronic":
                    # Shared electronic expenses follow the existing proportional component allocation.
                    def raw_cost(rows):
                        return sum((_decimal(r.get("quantity", 1)) * (_decimal(r["unit_price_rmb"]) if "unit_price_rmb" in r
                                   else _decimal(r.get("unit_price_hkd")) * fx) + raw_cost(_rows(r.get("children"))) for r in rows), Decimal(0))
                    all_cost = raw_cost(_rows(normalized.get("components")))
                    picked_cost = raw_cost(_rows(selected_payloads[code].get("components")))
                    share = picked_cost / all_cost if all_cost else Decimal(int(ref.component_id == str(source.components[0].get("id"))))
                    for stem in ("bonding", "smt", "labor", "testing", "packaging"):
                        amount = _decimal(original.get(stem + "_rmb")) if stem + "_rmb" in original else _decimal(original.get(stem + "_hkd")) * fx
                        if amount * share:
                            required.add(code)
                        electronic[stem + "_rmb"] = str(_decimal(electronic.get(stem + "_rmb")) + amount * share)
            # Only the selected component picture and referenced embedded images accompany a partial selection.
            serialized = canonical_json(selected_payloads)
            for attachment in source.attachments:
                if attachment.department == f"component-image:{ref.component_id}":
                    attachment_jobs.append((source, attachment, f"component-image:{target_component}"))
                elif ref.component_id == "__legacy_main__" and attachment.department == "product-image":
                    attachment_jobs.append((source, attachment, f"component-image:{target_component}"))
                elif attachment.id in serialized:
                    attachment_jobs.append((source, attachment, attachment.department))
        new_keys = _source_keys(_rows(payloads["engineering"].get("molds")))
        link_map = {(source_id, target_id, old_key): new_keys[index] for index, source_id, target_id, old_key in mold_links if old_key}
        for row in payloads["molding"]["injection_lines"]:
            link = row.pop("_history_link", None)
            if link:
                key = link_map.get(tuple(link))
                if key:
                    row["engineering_source_key"] = key
                else:
                    row.pop("engineering_source_key", None)
                    row.pop("engineering_synced_fields", None)
        sales = payloads.setdefault("sales", {})
        sales.update(_object(initial_payloads["sales"]))
        if whole and "justplay_packaging" in whole.payloads.get("sales", {}):
            sales["justplay_packaging"] = _clean(whole.payloads["sales"]["justplay_packaging"])

    sales = payloads.setdefault("sales", {})
    # New quotation commercial settings and regional freight never inherit old final prices.
    for field in ("shipping", "scenarios", "indonesia_freight_hkd"):
        sales.pop(field, None)
    if whole and whole.quote.region_code != quote.region_code:
        sales["freight_calc"] = {"enabled": False, "freight_enabled": False, "lifting_enabled": False}
    for field in ("profit_rate_percent",):
        payloads.get("electronic", {}).pop(field, None)
        for group in payloads.get("electronic", {}).get("quote_groups", []):
            group.pop(field, None)
    for code, field in (("molding", "injection_loss_rate_percent"), ("assembly", "labor_base_hkd")):
        payloads.get(code, {}).pop(field, None)

    # Deduplicate attachments and replace embedded IDs; no link points back into another quote.
    replacements = {}
    seen = set()
    for source, attachment, department in attachment_jobs:
        key = (attachment.id, department)
        if key in seen:
            continue
        seen.add(key)
        new_id = f"IQATT-{uuid4().hex}"
        replacements.setdefault(attachment.id, new_id)
        db.add(InternalQuoteAttachment(id=new_id, quote_id=quote.id, factory_id=quote.factory_id,
            department=department, file_name=attachment.file_name, content_type=attachment.content_type,
            size_bytes=attachment.size_bytes, sha256=attachment.sha256, content=attachment.content,
            uploaded_by=user.id, uploaded_by_name=user.display_name, uploaded_at=now_text()))
    def replace_ids(value):
        if isinstance(value, dict):
            return {key: replace_ids(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace_ids(item) for item in value]
        return replacements.get(value, value) if isinstance(value, str) else value
    return {code: canonical_json(replace_ids(value)) for code, value in payloads.items()}, evidence, required
