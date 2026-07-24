from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any


GENERIC_MATERIAL_TYPES = {
    "ABS", "透明ABS", "HIPS", "GP", "PP", "1#PP", "透明PP", "POM", "PVC",
    "LDPE", "HDPE", "TPR", "K料", "PC料",
}


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _positive(value: object) -> bool:
    if value in (None, ""):
        return False
    try:
        return Decimal(str(value)) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def _match_token(value: object) -> str:
    return "".join(_text(value).upper().split())


def _same_material_family(source: object, selected: object) -> bool:
    """Return whether a concrete selected material still belongs to a generic source family."""

    source_token = _match_token(source)
    selected_token = _match_token(selected)
    if not source_token or not selected_token:
        return False
    return (
        source_token == selected_token
        or source_token in selected_token
        or selected_token in source_token
    )


def _generic_material_hint(material: object, material_type: object) -> str:
    """Return the resin-family hint carried by an engineering mold row.

    Some mold workbooks repeat the same generic family in both columns, for
    example ``1#PP`` in material and ``PP`` in material type.  That pair is not
    a concrete frozen grade and must not overwrite the grade selected later by
    Molding.
    """

    material_text = _text(material)
    material_type_text = _text(material_type)
    material_token = _match_token(material_text)
    material_type_token = _match_token(material_type_text)
    material_is_generic = material_token in GENERIC_MATERIAL_TYPES
    material_type_is_generic = material_type_token in GENERIC_MATERIAL_TYPES
    if material_is_generic and not material_type_text:
        return material_text
    if material_type_is_generic and not material_text:
        return material_type_text
    if (
        material_is_generic
        and material_type_is_generic
        and _same_material_family(material_text, material_type_text)
    ):
        return material_text if len(material_token) >= len(material_type_token) else material_type_text
    return ""


def _a_code(value: object) -> Decimal | None:
    token = _match_token(value)
    if token.endswith("A"):
        token = token[:-1]
    if not token:
        return None
    try:
        result = Decimal(token)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def _canonical_machine_code(value: object) -> str:
    code = _a_code(value)
    if code is None:
        return _text(value)
    normalized = format(code.normalize(), "f")
    return f"{normalized}A"


def _machine_selection_matches(source: object, selected: object) -> bool:
    """Return whether a saved baseline range still contains the engineering A-code."""

    source_code = _a_code(source)
    selected_text = _text(selected).replace("—", "-").replace("–", "-")
    if source_code is None or not selected_text:
        return _match_token(source) == _match_token(selected)
    bounds = selected_text.split("-", 1)
    lower = _a_code(bounds[0])
    upper = _a_code(bounds[1]) if len(bounds) == 2 else lower
    return lower is not None and upper is not None and lower <= source_code <= upper


def _source_keys(molds: list[dict[str, Any]]) -> list[str]:
    occurrences: dict[str, int] = {}
    keys: list[str] = []
    for index, mold in enumerate(molds):
        mold_no = _match_token(mold.get("mold_no"))
        source_row = _text(mold.get("source_row"))
        name = _match_token(mold.get("item") or mold.get("chinese_name"))
        base = (
            f"mold-no:{mold_no}"
            if mold_no
            else f"source-row:{source_row}"
            if source_row not in {"", "0", "0.0000"}
            else f"name:{name}"
            if name
            else f"index:{index + 1}"
        )
        occurrences[base] = occurrences.get(base, 0) + 1
        keys.append(f"{base}#{occurrences[base]}")
    return keys


def prefill_molding_from_engineering(
    engineering_payload: dict[str, Any],
    molding_payload: dict[str, Any],
) -> dict[str, Any]:
    """Return a molding payload with engineering molds projected into injection rows.

    Engineering-owned values are refreshed whenever a quote is read. Molding-only
    values on an existing matching row are retained. Previously projected rows are
    removed when their engineering source mold no longer exists; manual rows remain.
    """

    source_rows = engineering_payload.get("molds", [])
    existing_rows = molding_payload.get("injection_lines", [])
    molds = [row for row in source_rows if isinstance(row, dict)] if isinstance(source_rows, list) else []
    existing = [deepcopy(row) for row in existing_rows if isinstance(row, dict)] if isinstance(existing_rows, list) else []
    keys = _source_keys(molds)
    used_existing: set[int] = set()
    projected: list[dict[str, Any]] = []

    def find_existing(source: dict[str, Any], source_key: str) -> int | None:
        for index, row in enumerate(existing):
            if index not in used_existing and _text(row.get("engineering_source_key")) == source_key:
                return index
        source_mold_no = _match_token(source.get("mold_no"))
        if source_mold_no:
            for index, row in enumerate(existing):
                if (
                    index not in used_existing
                    and row.get("engineering_sync_disabled") is not True
                    and _match_token(row.get("mold_no")) == source_mold_no
                ):
                    return index
        source_name = _match_token(source.get("item") or source.get("chinese_name"))
        if source_name:
            for index, row in enumerate(existing):
                if (
                    index not in used_existing
                    and row.get("engineering_sync_disabled") is not True
                    and _match_token(row.get("item")) == source_name
                ):
                    return index
        return None

    for source, source_key in zip(molds, keys, strict=True):
        existing_index = find_existing(source, source_key)
        if existing_index is None:
            row: dict[str, Any] = {
                "item": "",
                "mold_no": "",
                "material": "",
                "grade": "",
                "color": "",
                "net_weight_g": "0",
                "loss_rate_percent": molding_payload.get("injection_loss_rate_percent", "3"),
                "machine_name": "",
                "machine_code": "",
                "cavity": "",
                "sets": "1",
                "target_output": "0",
                "cycle_time_seconds": "0",
                "quantity": "1",
                "remark": "",
                "disney_mold_no": "",
                "disney_resin_cost_usd_kg": "0",
                "disney_cycle_time_seconds": "0",
                "disney_labor_rate_usd_hr": "0",
            }
        else:
            used_existing.add(existing_index)
            row = existing[existing_index]

        if row.get("engineering_sync_disabled") is True:
            row["engineering_source_key"] = source_key
            row["engineering_synced_fields"] = []
            projected.append(row)
            continue

        synced_fields: list[str] = []

        def sync_text(target: str, value: object) -> None:
            content = _text(value)
            if content:
                row[target] = content
                synced_fields.append(target)
            else:
                row.setdefault(target, "")

        def sync_positive(target: str, value: object) -> None:
            if _positive(value):
                row[target] = value
                synced_fields.append(target)
            else:
                row.setdefault(target, "0")

        sync_text("item", source.get("item") or source.get("chinese_name"))
        sync_text("mold_no", source.get("mold_no"))
        sync_text("disney_mold_no", source.get("disney_mold_no"))
        source_material = _text(source.get("material"))
        source_material_type = _text(source.get("material_type"))
        generic_material_hint = _generic_material_hint(source_material, source_material_type)
        # Mold quotations commonly put only the generic resin family (PP/PVC/ABS)
        # in either material column. Treat that as a category hint and let Molding
        # retain/select the concrete frozen material grade instead of rebuilding an
        # invalid pair such as "blank + PP" or "PP + blank" on every quote read.
        if generic_material_hint:
            selected_material = _text(row.get("material"))
            selected_grade = _text(row.get("grade"))
            if selected_grade and _same_material_family(generic_material_hint, selected_material):
                # The engineering sheet supplies only a resin family.  Keep the
                # concrete frozen material/grade selected by Molding across save
                # and quote refresh; otherwise every read would clear `grade` and
                # make an already valid section impossible to submit.
                row["material"] = selected_material
                row["grade"] = selected_grade
            else:
                sync_text("material", generic_material_hint)
                row["grade"] = ""
        else:
            sync_text("material", source_material)
            sync_text("grade", source_material_type)
        sync_text("color", source.get("color"))
        sync_positive("net_weight_g", source.get("net_weight_g"))
        sync_text("cavity", source.get("cavity"))
        sync_positive("sets", source.get("quantity"))
        source_machine_code = _canonical_machine_code(source.get("machine_code"))
        selected_machine_code = _text(row.get("machine_code"))
        if source_machine_code:
            if selected_machine_code and _machine_selection_matches(
                source_machine_code,
                selected_machine_code,
            ):
                # The Engineering sheet often carries a bare code such as 18,
                # while Molding selects the frozen baseline option 18A.  Keep
                # that concrete selection across save/read projection.
                row["machine_code"] = selected_machine_code
            else:
                row["machine_code"] = source_machine_code
                if selected_machine_code:
                    row["machine_name"] = ""
            synced_fields.append("machine_code")
        else:
            row.setdefault("machine_code", "")
        sync_positive("target_output", source.get("target_output"))
        sync_positive("cycle_time_seconds", source.get("cycle_time_seconds"))
        row["engineering_source_key"] = source_key
        row["engineering_synced_fields"] = synced_fields
        projected.append(row)

    # Keep rows created by the molding department. Stale engineering-projected
    # rows are intentionally omitted because their source mold has been removed.
    projected.extend(
        row
        for index, row in enumerate(existing)
        if index not in used_existing and not _text(row.get("engineering_source_key"))
    )
    result = deepcopy(molding_payload)
    result["injection_lines"] = projected
    return result
