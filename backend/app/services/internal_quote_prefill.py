from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4
import unicodedata


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
    return "".join(unicodedata.normalize("NFKC", _text(value)).upper().split())


def material_family(value: object) -> str:
    token = _match_token(value)
    return {"1#PP": "PP"}.get(token, token)


def _same_material_family(source: object, selected: object) -> bool:
    """Return whether a concrete selected material still belongs to a generic source family."""

    source_token = _match_token(source)
    selected_token = _match_token(selected)
    if not source_token or not selected_token:
        return False
    return material_family(source_token) == material_family(selected_token)


def normalize_engineering_mold_identities(payload: dict[str, Any], existing_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Allocate identity on mutable drafts only; never rewrite stored history."""
    result = deepcopy(payload)
    seen_molds: set[str] = set()
    seen_parts: set[str] = set()
    existing_molds = (existing_payload or {}).get("molds", []) or []
    molds = [mold for mold in result.get("molds", []) or [] if isinstance(mold, dict)]
    previous_keys = _source_keys(molds)
    for mold, previous_key in zip(molds, previous_keys, strict=True):
        mold_id = _text(mold.get("mold_id"))
        had_identity = bool(mold_id)
        candidates = [old for old in existing_molds if isinstance(old, dict)
                      and ((_match_token(mold.get("mold_no")) and _match_token(mold.get("mold_no")) == _match_token(old.get("mold_no")))
                           or (not _match_token(mold.get("mold_no")) and _match_token(mold.get("item") or mold.get("chinese_name"))
                               and _match_token(mold.get("item") or mold.get("chinese_name")) == _match_token(old.get("item") or old.get("chinese_name"))))]
        if not mold_id and len(candidates) == 1:
            mold_id = _text(candidates[0].get("mold_id"))
            if mold_id and candidates[0].get("legacy_source_key"):
                mold["legacy_source_key"] = candidates[0]["legacy_source_key"]
        if not mold_id or mold_id in seen_molds:
            if not had_identity and not mold_id:
                mold["legacy_source_key"] = previous_key
            else:
                # A copied stable row receives a new identity, not its old alias.
                mold.pop("legacy_source_key", None)
            mold_id = f"mold-{uuid4().hex}"
        mold["mold_id"] = mold_id
        seen_molds.add(mold_id)
        for part in mold.get("parts", []) or []:
            if not isinstance(part, dict):
                continue
            part_id = _text(part.get("part_id") or part.get("id"))
            if not part_id and len(candidates) == 1:
                matching_parts = [old for old in candidates[0].get("parts", []) or [] if isinstance(old, dict)
                                  and _match_token(old.get("name")) == _match_token(part.get("name")) and _match_token(part.get("name"))]
                if len(matching_parts) == 1:
                    part_id = _text(matching_parts[0].get("part_id") or matching_parts[0].get("id"))
            if not part_id or part_id in seen_parts:
                part_id = f"part-{uuid4().hex}"
            part["part_id"] = part_id
            seen_parts.add(part_id)
    return result


def reuse_huadeng_import_identities(fragment: dict[str, Any], existing_payload: dict[str, Any], *, factory_id: str) -> dict[str, Any]:
    """An explicit reimport may reuse only unique, unchanged source coordinates.

    Names alone cannot resolve moved rows; duplicate names on different source
    rows remain distinct. Ambiguous matches keep fresh IDs and orphan blocking.
    """
    result = deepcopy(fragment)
    if factory_id != "huadeng":
        return result
    def source_row(row):
        try:
            value = Decimal(str(row.get("source_row", 0)))
            return int(value) if value.is_finite() and value > 0 and value == int(value) else 0
        except (ValueError, TypeError, InvalidOperation):
            return 0
    def mold_key(row):
        return (_match_token(row.get("mold_no")), source_row(row))
    old_molds = [row for row in existing_payload.get("molds", []) or []
                 if isinstance(row, dict) and row.get("molding_profile") == "huadeng_parts_v1"]
    new_molds = [row for row in result.get("molds", []) or [] if isinstance(row, dict)]
    for mold in new_molds:
        key = mold_key(mold)
        candidates = [old for old in old_molds if mold_key(old) == key]
        if not key[0] or not key[1] or len(candidates) != 1 or sum(mold_key(other) == key for other in new_molds) != 1:
            continue
        old = candidates[0]
        if not old.get("mold_id"):
            continue
        mold["mold_id"] = old["mold_id"]
        old_parts = [part for part in old.get("parts", []) or [] if isinstance(part, dict)]
        new_parts = [part for part in mold.get("parts", []) or [] if isinstance(part, dict)]
        def part_key(part):
            return source_row(part), _match_token(part.get("name"))
        for part in new_parts:
            key = part_key(part)
            matches = [previous for previous in old_parts if part_key(previous) == key]
            if key[0] and key[1] and len(matches) == 1 and sum(part_key(other) == key for other in new_parts) == 1 and matches[0].get("part_id"):
                part["part_id"] = matches[0]["part_id"]
    return result


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


def _inherited_part_target(value: object, parent: object) -> object:
    # Existing imports use zero for an absent child capacity. Only blank/zero
    # inherit; malformed or negative values must reach validation unchanged.
    if not _text(value):
        return parent
    try:
        if Decimal(str(value)) == 0:
            return parent
    except (InvalidOperation, TypeError, ValueError):
        pass
    return value


def _huadeng_part_sources(molds: list[dict[str, Any]], factory_id: str) -> list[dict[str, Any]]:
    """Expand only explicitly imported Huadeng groups; never migrate old molds."""
    sources = []
    for mold_index, mold in enumerate(molds):
        if factory_id != "huadeng" or mold.get("molding_profile") != "huadeng_parts_v1":
            sources.append(mold)
            continue
        for part_index, part in enumerate(mold.get("parts", []) or []):
            if not isinstance(part, dict):
                continue
            source = {**mold, "parts": [], "mold_id": _text(mold.get("mold_id")) or f"pending-mold:{mold_index}",
                      "_part_id": _text(part.get("part_id")) or f"pending-part:{part_index}",
                      "_invalid_identity": not (mold.get("mold_id") and part.get("part_id")),
                      "item": part.get("name", ""), "chinese_name": part.get("name", ""),
                      "material": part.get("material", ""), "material_type": part.get("material_type", ""),
                      "color": part.get("color", ""), "net_weight_g": part.get("unit_net_weight_g", "0"),
                      "cavity": part.get("output_count") or "0", "quantity": part.get("quantity", "0"),
                      "machine_code": part.get("machine_code") or mold.get("machine_code", ""),
                      "target_output": _inherited_part_target(part.get("target_output"), mold.get("target_output", "0")),
                      "remark": part.get("remark", ""), "source_row": part.get("source_row", 0),
                      "image_attachment_ids": deepcopy(part.get("image_attachment_ids", [])),
                      "legacy_source_key": ""}
            sources.append(source)
    return sources


def _source_keys(molds: list[dict[str, Any]]) -> list[str]:
    occurrences: dict[str, int] = {}
    keys: list[str] = []
    for index, mold in enumerate(molds):
        if _text(mold.get("mold_id")):
            suffix = f"/part-id:{mold['_part_id']}" if mold.get("_part_id") else ""
            keys.append(f"mold-id:{_text(mold['mold_id'])}{suffix}")
            continue
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
    *,
    remove_missing_only: bool = False,
    factory_id: str = "",
) -> dict[str, Any]:
    """Return a molding payload with engineering molds projected into injection rows.

    Engineering-owned values are refreshed whenever a quote is read. Molding-only
    values on an existing matching row are retained. Orphaned projected rows stay
    visible for explicit resolution; manual rows remain independent.
    """

    if molding_payload.get("engineering_prefill_paused") is True:
        return deepcopy(molding_payload)
    source_rows = engineering_payload.get("molds", [])
    existing_rows = molding_payload.get("injection_lines", [])
    molds = [row for row in source_rows if isinstance(row, dict)] if isinstance(source_rows, list) else []
    molds = _huadeng_part_sources(molds, factory_id)
    existing = [deepcopy(row) for row in existing_rows if isinstance(row, dict)] if isinstance(existing_rows, list) else []
    if not molds and not existing:
        # Opening/recalculating a new quote must not manufacture an empty input
        # field that makes an untouched department look edited or invalid.
        return deepcopy(molding_payload)
    keys = _source_keys(molds)
    legacy_keys = [_text(source.get("legacy_source_key")) if source.get("mold_id") else key
                   for source, key in zip(molds, keys, strict=True)]
    if remove_missing_only:
        # Dependency invalidation may identify removed sources, but it must not
        # discard department work or introduce new unsaved Engineering inputs.
        active_keys = set(keys) | set(legacy_keys)
        active_ids = {_text(mold.get("mold_id")) for mold in molds} - {""}
        for row in existing:
            if row.get("engineering_sync_disabled") is True:
                row.pop("engineering_source_missing", None)
            elif (_text(row.get("engineering_source_key"))
                  and _text(row.get("engineering_source_key")) not in active_keys
                  and (row.get("engineering_part_id") or _text(row.get("engineering_mold_id")) not in active_ids)):
                row["engineering_source_missing"] = True
        result = deepcopy(molding_payload)
        result["injection_lines"] = existing
        return result
    used_existing: set[int] = set()
    projected: list[dict[str, Any]] = []

    def find_existing(source: dict[str, Any], source_key: str, legacy_matches: list[int]) -> int | None:
        for index, row in enumerate(existing):
            if index not in used_existing and _text(row.get("engineering_source_key")) == source_key:
                return index
        source_mold_id = _text(source.get("mold_id"))
        if source_mold_id:
            for index, row in enumerate(existing):
                if index not in used_existing and _text(row.get("engineering_mold_id")) == source_mold_id and _text(row.get("engineering_part_id")) == _text(source.get("_part_id")):
                    return index
        if source.get("_part_id"):
            return None
        # An explicit historical association outranks name/number heuristics,
        # including when an unlinked manual supplement has the same labels.
        if len(legacy_matches) == 1 and legacy_matches[0] not in used_existing:
            return legacy_matches[0]
        source_mold_no = _match_token(source.get("mold_no"))
        if source_mold_no:
            candidates = [index for index, row in enumerate(existing) if (
                    index not in used_existing
                    and row.get("engineering_sync_disabled") is not True
                    and not _text(row.get("engineering_mold_id"))
                    and _match_token(row.get("mold_no")) == source_mold_no
                )]
            if len(candidates) == 1 and sum(_match_token(mold.get("mold_no")) == source_mold_no for mold in molds) == 1:
                return candidates[0]
        source_name = _match_token(source.get("item") or source.get("chinese_name"))
        if source_name:
            candidates = [index for index, row in enumerate(existing) if (
                    index not in used_existing
                    and row.get("engineering_sync_disabled") is not True
                    and not _text(row.get("engineering_mold_id"))
                    and (not source_mold_no or not _match_token(row.get("mold_no")) or _match_token(row.get("mold_no")) == source_mold_no)
                    and _match_token(row.get("item")) == source_name
                )]
            if len(candidates) == 1 and sum(_match_token(mold.get("item") or mold.get("chinese_name")) == source_name for mold in molds) == 1:
                return candidates[0]
        return None

    for source, source_key, legacy_key in zip(molds, keys, legacy_keys, strict=True):
        legacy_matches = [index for index, row in enumerate(existing) if legacy_key
                          and not _text(row.get("engineering_mold_id"))
                          and _text(row.get("engineering_source_key")) == legacy_key]
        associated_matches = sorted(set(legacy_matches + [index for index, row in enumerate(existing)
                                    if _text(row.get("engineering_source_key")) == source_key
                                    or (source.get("mold_id") and row.get("engineering_mold_id") == source["mold_id"] and _text(row.get("engineering_part_id")) == _text(source.get("_part_id")))]))
        if legacy_matches and (len(associated_matches) > 1 or legacy_keys.count(legacy_key) > 1):
            # Ambiguous historical associations must never create replacement
            # prices or choose a row by name. Preserve all affected work, blocked.
            for index in associated_matches:
                if index not in used_existing:
                    row = existing[index]
                    row["engineering_linkage_conflict"] = True
                    projected.append(row)
                    used_existing.add(index)
            continue
        existing_index = find_existing(source, source_key, legacy_matches)
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
                "sets": "0",
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

        row.pop("engineering_linkage_conflict", None)
        if source.get("mold_id") and existing_index in legacy_matches:
            # First ID adoption migrates only the explicit old association.
            row["engineering_mold_id"] = source["mold_id"]
            row["engineering_source_key"] = source_key
            if not row.get("line_id"):
                row["line_id"] = f"injection:{source['mold_id']}"

        # Detached rows retain source identity only to suppress replacement.
        # Preserve department values before applying any Engineering metadata.
        if row.get("engineering_sync_disabled") is True:
            row.pop("engineering_source_missing", None)
            projected.append(row)
            continue

        if source.get("mold_id"):
            row["engineering_mold_id"] = source["mold_id"]
            row.setdefault("line_id", f"injection:{source['mold_id']}" + (f":{source['_part_id']}" if source.get("_part_id") else ""))
        row["cost_scope"] = "huadeng_part" if source.get("_part_id") else "whole_mold"
        if source.get("_part_id"):
            if source.get("_invalid_identity"):
                row["engineering_linkage_conflict"] = True
            row["engineering_part_id"] = source["_part_id"]
            row["engineering_remark"] = _text(source.get("remark"))
            row["engineering_source_row"] = source.get("source_row", 0)
            row["image_attachment_ids"] = deepcopy(source.get("image_attachment_ids", []))
            row["engineering_labor_mode"] = "transfer" if "转水口" in _text(source.get("remark")) else "shared"
            row["labor_job_id"] = f"mold-id:{source['mold_id']}/job:" + (source["_part_id"] if row["engineering_labor_mode"] == "transfer" else "shared")
            if existing_index is None:
                row["remark"] = _text(source.get("remark"))
        row["engineering_parts"] = deepcopy(source.get("parts", []))
        row.pop("engineering_source_missing", None)

        previous_synced_fields = set(row.get("engineering_synced_fields", []))
        synced_fields: list[str] = []

        def sync_text(target: str, value: object) -> None:
            content = _text(value)
            if content:
                row[target] = content
                synced_fields.append(target)
            else:
                if target in previous_synced_fields:
                    row[target] = ""
                else:
                    row.setdefault(target, "")

        def sync_positive(target: str, value: object) -> None:
            if _positive(value):
                row[target] = value
                synced_fields.append(target)
            else:
                if target in previous_synced_fields:
                    row[target] = "0"
                else:
                    row.setdefault(target, "0")

        sync_text("item", source.get("item") or source.get("chinese_name"))
        sync_text("mold_no", source.get("mold_no"))
        sync_text("disney_mold_no", source.get("disney_mold_no"))
        if source.get("pricing_component_id") or "pricing_component_id" in previous_synced_fields:
            sync_text("pricing_component_id", source.get("pricing_component_id"))
        source_material = _text(source.get("material"))
        source_material_type = _text(source.get("material_type"))
        generic_material_hint = _generic_material_hint(source_material, source_material_type) or (source_material_type if source.get("_part_id") and not source_material else "")
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
        if source.get("_part_id"):
            sync_positive("quantity", 1)
        source_machine_code = _canonical_machine_code(source.get("machine_code"))
        selected_machine_code = _text(row.get("machine_code"))
        if source_machine_code:
            if selected_machine_code and ((source.get("_part_id") and row.get("engineering_machine_hint") == source_machine_code) or _machine_selection_matches(
                source_machine_code,
                selected_machine_code,
            )):
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
            if "machine_code" in previous_synced_fields:
                row["machine_code"] = ""
                row["machine_name"] = ""
            else:
                row.setdefault("machine_code", "")
        if source.get("_part_id"):
            row["engineering_machine_hint"] = source_machine_code
        if source.get("_part_id"):
            row["target_output"] = source.get("target_output")
            synced_fields.append("target_output")
        else:
            sync_positive("target_output", source.get("target_output"))
        sync_positive("cycle_time_seconds", source.get("cycle_time_seconds"))
        row["engineering_source_key"] = source_key
        row["engineering_synced_fields"] = synced_fields
        projected.append(row)

    # Keep department work, including unresolved rows whose source was removed.
    for index, row in enumerate(existing):
        if index in used_existing:
            continue
        row.pop("engineering_linkage_conflict", None)
        if row.get("engineering_sync_disabled") is True:
            row.pop("engineering_source_missing", None)
        elif _text(row.get("engineering_source_key")):
            # Never delete department work implicitly when a source mold is
            # removed. Keep it visible and block pricing until explicitly resolved.
            row["engineering_source_missing"] = True
        projected.append(row)
    result = deepcopy(molding_payload)
    result["injection_lines"] = projected
    return result
