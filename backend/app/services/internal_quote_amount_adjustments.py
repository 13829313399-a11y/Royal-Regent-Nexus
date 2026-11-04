"""Row-owned adopted costs. Original inputs and issued workbooks stay immutable."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json

KEY = "quote_amount_adjustment"
HISTORY = "quote_amount_history"


def basis_hash(value):
    def normalize(item):
        if isinstance(item, dict):
            return {key: normalize(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        if isinstance(item, (str, int, float, Decimal)) and not isinstance(item, bool):
            try:
                number = Decimal(str(item))
                if number.is_finite():
                    return format(number.normalize(), "f")
            except InvalidOperation:
                pass
        return item
    return hashlib.sha256(json.dumps(normalize(value), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def adopt_amount(row, path, original, quantity, basis, result, *, per_carton=False):
    """Return a per-piece cost; an obsolete adjustment never contributes a cost."""
    original, quantity = Decimal(original), Decimal(quantity)
    fingerprint = basis_hash(basis)
    adjustment = row.get(KEY)
    mode, amount, status = "formula", original, "formula"
    if adjustment is not None:
        status = "pending"
        try:
            mode = adjustment["mode"]
            amount = Decimal(str(adjustment["amount_hkd"]))
            allowed = {"per_piece", "per_carton"} if per_carton else {"per_piece"}
            if mode not in allowed or not amount.is_finite() or not 0 <= amount <= 1_000_000_000:
                raise ValueError()
            reason = row.get("price_annotations", {}).get(KEY, {}).get("text", "").strip()
            if adjustment.get("basis_hash") == fingerprint and reason and not adjustment.get("requires_confirmation"):
                status = "adopted"
        except (KeyError, TypeError, ValueError, InvalidOperation, AttributeError):
            mode, amount = "per_piece", original
        if status == "pending":
            result["warnings"].append({"code": "amount_adjustment_pending", "severity": "blocking",
                                       "message": f"{row.get('name') or row.get('item') or '调价项目'}的调价依据已变化，请在汇总页重新确认或恢复公式核算"})
    effective = amount / quantity if mode == "per_carton" else amount
    if status != "adopted":
        effective = original
    result.setdefault("amount_adjustments", []).append({
        "path": path, "mode": mode, "status": status, "basis_hash": fingerprint,
        "original_per_piece_hkd": str(original),
        "original_per_carton_hkd": str(original * quantity) if per_carton else None,
        "qty_per_carton": str(quantity) if per_carton else None,
        "amount_hkd": str(amount), "effective_per_piece_hkd": str(effective),
        "allowed_modes": ["per_piece", "per_carton"] if per_carton else ["per_piece"],
        "history_count": len(row.get(HISTORY, [])),
    })
    return effective


def adjustment_catalog(code, payload, snapshot):
    # Reuse exactly the authoritative cost functions. Unrelated shipping fields
    # must not hide a carton's review controls when a draft is incomplete.
    from app.services.internal_quote_calculator import _assembly, _sales_packaging, resolve_sales_cartons, CalculationInputError
    result = {"warnings": [], "line_breakdown": [], "currency_totals": {}, "totals": {}}
    try:
        if code == "assembly":
            _assembly(payload, snapshot, result)
        elif code == "sales":
            _sales_packaging({**payload, "cartons": resolve_sales_cartons(payload)}, snapshot, result)
    except (CalculationInputError, ArithmeticError, ValueError, TypeError):
        pass
    return {tuple(item["path"]): item for item in result.get("amount_adjustments", [])}


def retain_replaced_adjustments(previous, current):
    """Unique group identity permits review, never automatic reuse after import."""
    old_groups = previous.get("groups", [])
    new_groups = current.get("groups", [])
    pending = deepcopy(previous.get("removed_amount_adjustments", []))
    for old in old_groups:
        if not isinstance(old, dict) or not (old.get(KEY) or old.get(HISTORY)):
            continue
        identity = (old.get("name"), old.get("category", "assembly"))
        matches = [row for row in new_groups if (row.get("name"), row.get("category", "assembly")) == identity]
        unique_old = sum((row.get("name"), row.get("category", "assembly")) == identity for row in old_groups) == 1
        if len(matches) == 1 and unique_old:
            target = matches[0]
            if target.get("import_batch_id") == old.get("import_batch_id") and target.get(KEY) == old.get(KEY):
                continue
            for key in (KEY, HISTORY):
                if key in old:
                    target[key] = deepcopy(old[key])
            if target.get(KEY):
                target[KEY]["requires_confirmation"] = True
                target.setdefault("price_annotations", {})[KEY] = deepcopy(old.get("price_annotations", {}).get(KEY, {}))
        else:
            pending.append({"name": old.get("name", "旧装工组"), "adjustment": deepcopy(old.get(KEY)),
                            "history": deepcopy(old.get(HISTORY, [])),
                            "price_annotations": deepcopy(old.get("price_annotations", {})),
                            "status": "source_removed"})
    if pending:
        current["removed_amount_adjustments"] = pending
    return current


def mark_stale_adjustments(code, payload, snapshot):
    catalog = adjustment_catalog(code, payload, snapshot)
    rows = [(["groups", i], row) for i, row in enumerate(payload.get("groups", []))] if code == "assembly" else []
    if code == "sales":
        for i, carton in enumerate(payload.get("cartons", [])):
            if isinstance(carton, dict):
                rows.append((["cartons", i], carton))
                rows.extend((["cartons", i, "flat_cards", j], flat) for j, flat in enumerate(carton.get("flat_cards", [])))
    for path, owner in rows:
        if not isinstance(owner, dict) or catalog.get(tuple(path), {}).get("status") == "adopted":
            continue
        if isinstance(owner.get(KEY), dict):
            owner[KEY]["requires_confirmation"] = True
    return payload
