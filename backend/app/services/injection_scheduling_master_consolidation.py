from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.injection_scheduling_shared import (
    InjectionSchedulingCommercialRateRule,
    InjectionSchedulingCompanyFactoryMembership,
    InjectionSchedulingFactoryMoldCapability,
    InjectionSchedulingFieldEvidence,
    InjectionSchedulingMasterDataProposal,
    InjectionSchedulingMoldAlias,
    InjectionSchedulingMoldDefinition,
    InjectionSchedulingMoldOutputSpec,
)
from app.services.injection_scheduling_demand_import import normalize_identifier
from app.services.injection_scheduling_excel import (
    _arm_type,
    _fixture_type,
    _WorkbookReader,
)
from app.services.injection_scheduling_execution import _now
from app.services.injection_scheduling_master_import import (
    _header_mapping,
    _row_payload,
)
from app.services.injection_scheduling_rules import normalize_class_text

CONSOLIDATION_SCHEMA_VERSION = "huaxing-master-consolidation-v1"
MOLD_BUNDLE_ENTITY = "MOLD_DEFINITION_BUNDLE"
CAPABILITY_BUNDLE_ENTITY = "FACTORY_MOLD_CAPABILITY_BUNDLE"
RATE_BUNDLE_ENTITY = "COMMERCIAL_RATE_RULE"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _decimal(value: object) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return result


def _positive_decimal_text(value: object) -> str:
    parsed = _decimal(value)
    if parsed is None or parsed <= 0:
        return ""
    return format(parsed.normalize(), "f")


def _positive_int(value: object) -> int | None:
    parsed = _decimal(value)
    if parsed is None or parsed <= 0 or parsed != parsed.to_integral_value():
        return None
    return int(parsed)


def _mold_key(value: object) -> str:
    return re.sub(r"\s+", "", normalize_identifier(value))


def _normalized_text(value: object) -> str:
    return re.sub(r"\s+", " ", normalize_identifier(value)).strip()


def _source_ref(
    *,
    sheet_name: str,
    source_row: int,
    source_file_name: str,
    source_file_hash: str,
    lineage: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "sheet_name": sheet_name,
        "source_row": source_row,
        "source_file_name": source_file_name,
        "source_file_hash": source_file_hash,
        "lineage": lineage,
    }


def _first_nonblank(rows: list[dict[str, Any]], field: str) -> str:
    for row in rows:
        value = str(row["values"].get(field, "")).strip()
        if value:
            return value
    return ""


def _distinct(rows: list[dict[str, Any]], field: str) -> list[str]:
    values: dict[str, str] = {}
    for row in rows:
        value = str(row["values"].get(field, "")).strip()
        if value:
            values.setdefault(_normalized_text(value), value)
    return sorted(values.values(), key=_normalized_text)


def _representative(rows: list[dict[str, Any]], field: str) -> str:
    values = [
        str(row["values"].get(field, "")).strip()
        for row in rows
        if str(row["values"].get(field, "")).strip()
    ]
    if not values:
        return ""
    counts = Counter(_normalized_text(value) for value in values)
    best_key = min(counts, key=lambda key: (-counts[key], key))
    return next(value for value in values if _normalized_text(value) == best_key)


def _read_role_rows(
    reader: _WorkbookReader,
    *,
    sheet_name: str,
    role: str,
    source_file_name: str,
    source_file_hash: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = list(reader.rows(sheet_name))
    header_row, mapping, mapping_evidence, ambiguous = _header_mapping(
        reader, rows, role
    )
    required = "source_mold_no"
    if not header_row or required not in mapping or ambiguous:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MASTER_DATA_MAPPING_REQUIRED",
                "message": f"{sheet_name} 表头无法唯一映射",
                "ambiguous_fields": ambiguous,
            },
        )
    result: list[dict[str, Any]] = []
    for source_row, cells in rows:
        if source_row <= header_row:
            continue
        values, lineage = _row_payload(reader, cells=cells, mapping=mapping)
        mold_no = values.get("source_mold_no", "").strip()
        if not mold_no:
            continue
        result.append(
            {
                "source_row": source_row,
                "mold_key": _mold_key(mold_no),
                "values": values,
                "source": _source_ref(
                    sheet_name=sheet_name,
                    source_row=source_row,
                    source_file_name=source_file_name,
                    source_file_hash=source_file_hash,
                    lineage=lineage,
                ),
            }
        )
    return result, {
        "sheet_name": sheet_name,
        "role": role,
        "header_row": header_row,
        "mapping": mapping_evidence,
        "row_count": len(result),
    }


def _output_identity(values: dict[str, str]) -> tuple[str, ...]:
    return (
        _normalized_text(values.get("item_no", "")),
        _normalized_text(values.get("product_name", "")),
        _normalized_text(values.get("material_name", "")),
        _normalized_text(values.get("color_name", "")),
        _positive_decimal_text(values.get("cavity_count", "")),
        _positive_decimal_text(values.get("whole_shot_net_weight_g", "")),
        _positive_decimal_text(values.get("whole_shot_gross_weight_g", "")),
        _positive_decimal_text(values.get("nominal_daily_capacity", "")),
    )


def _build_outputs(price_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in price_rows:
        groups[_output_identity(row["values"])].append(row)
    item_counts = Counter(identity[0] for identity in groups if identity[0])
    outputs: list[dict[str, Any]] = []
    for identity, rows in sorted(groups.items()):
        values = rows[0]["values"]
        output_key = _digest({"mold_key": rows[0]["mold_key"], "identity": identity})
        item_no = values.get("item_no", "").strip()
        variant_code = ""
        if item_no and item_counts[_normalized_text(item_no)] > 1:
            variant_code = f"src-{output_key[:12]}"
        outputs.append(
            {
                "output_key": output_key,
                "item_no": item_no,
                "variant_code": variant_code,
                "product_name": values.get("product_name", "").strip(),
                "cavity_count": _positive_int(values.get("cavity_count", "")),
                "whole_shot_net_weight_g": _positive_decimal_text(
                    values.get("whole_shot_net_weight_g", "")
                ),
                "whole_shot_gross_weight_g": _positive_decimal_text(
                    values.get("whole_shot_gross_weight_g", "")
                ),
                "default_material": values.get("material_name", "").strip(),
                "default_color": values.get("color_name", "").strip(),
                "nominal_daily_capacity": _positive_decimal_text(
                    values.get("nominal_daily_capacity", "")
                ),
                "source_rows": [row["source"] for row in rows],
            }
        )
    return outputs


def consolidate_master_data_workbook(
    content: bytes,
    source_file_name: str,
    *,
    factory_id: str,
) -> dict[str, Any]:
    """Merge 单价 and 机安 evidence without silently resolving conflicts.

    Machine/capability fields come from 机安 whenever the mold exists there.  Only
    price-only molds fall back to 单价.  Price amounts are preserved as proposals;
    this function deliberately does not guess currency, tax mode or applicability.
    """

    source_file_hash = hashlib.sha256(content).hexdigest()
    reader = _WorkbookReader(content)
    try:
        missing = [name for name in ("单价", "机安") if name not in reader.sheet_paths]
        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "MASTER_DATA_SHEET_MISSING",
                    "message": f"缺少工作表：{', '.join(missing)}",
                },
            )
        price_rows, price_mapping = _read_role_rows(
            reader,
            sheet_name="单价",
            role="PRICE_RULE_SOURCE",
            source_file_name=source_file_name,
            source_file_hash=source_file_hash,
        )
        machine_rows, machine_mapping = _read_role_rows(
            reader,
            sheet_name="机安",
            role="MOLD_DEFINITION_SOURCE",
            source_file_name=source_file_name,
            source_file_hash=source_file_hash,
        )
    finally:
        reader.close()

    price_by_mold: dict[str, list[dict[str, Any]]] = defaultdict(list)
    machine_by_mold: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in price_rows:
        if row["mold_key"]:
            price_by_mold[row["mold_key"]].append(row)
    for row in machine_rows:
        if row["mold_key"]:
            machine_by_mold[row["mold_key"]].append(row)

    mold_entries: list[dict[str, Any]] = []
    capability_entries: list[dict[str, Any]] = []
    review_entries: list[dict[str, Any]] = []
    all_keys = sorted(set(price_by_mold) | set(machine_by_mold))
    for mold_key in all_keys:
        prices = price_by_mold.get(mold_key, [])
        machines = machine_by_mold.get(mold_key, [])
        preferred_rows = machines if machines else prices
        mold_no = _first_nonblank(preferred_rows, "source_mold_no")
        raw_aliases = sorted(
            {
                str(row["values"].get("source_mold_no", "")).strip()
                for row in prices + machines
                if str(row["values"].get("source_mold_no", "")).strip()
            },
            key=_normalized_text,
        )
        class_field = (
            "recommended_machine_class_raw" if machines else "fallback_machine_class_raw"
        )
        class_values = _distinct(preferred_rows, class_field)
        capability_fields = (
            class_field,
            "required_arm_type",
            "required_fixture_type",
            "length_mm",
            "width_mm",
            "height_mm",
            "weight_kg",
        )
        conflicts = {
            field: _distinct(preferred_rows, field)
            for field in capability_fields
            if len(_distinct(preferred_rows, field)) > 1
        }
        if conflicts:
            review_entries.append(
                {
                    "mold_key": mold_key,
                    "display_mold_no": mold_no,
                    "code": "CAPABILITY_SOURCE_CONFLICT",
                    "source_priority": "机安" if machines else "单价回退",
                    "conflicts": conflicts,
                    "source_rows": [row["source"] for row in preferred_rows],
                }
            )
            continue

        outputs = _build_outputs(prices)
        raw_class = class_values[0] if class_values else ""
        normalized_class = normalize_class_text(raw_class)
        standard_name = _representative(machines, "standard_name")
        if not standard_name and len(outputs) == 1:
            standard_name = outputs[0]["product_name"]
        mold_entry = {
            "mold_key": mold_key,
            "canonical_mold_no": mold_no,
            "display_mold_no": mold_no,
            "raw_aliases": raw_aliases,
            "standard_name": standard_name,
            "recommended_machine_class_raw": raw_class,
            "mold_a_class": int(normalized_class.a_class)
            if normalized_class.a_class is not None
            and normalized_class.a_class == normalized_class.a_class.to_integral_value()
            else None,
            "normalization_status": normalized_class.status,
            "normalization_reason_codes": list(normalized_class.reason_codes),
            "process_tags": list(normalized_class.process_tags),
            "special_machine_type": normalized_class.special_machine_type,
            "default_arm_type": _arm_type(
                _first_nonblank(machines, "required_arm_type")
            ),
            "default_fixture_type": _fixture_type(
                _first_nonblank(machines, "required_fixture_type")
            ),
            "engineering": {
                "length_mm": _positive_decimal_text(
                    _first_nonblank(machines, "length_mm")
                ),
                "width_mm": _positive_decimal_text(
                    _first_nonblank(machines, "width_mm")
                ),
                "height_mm": _positive_decimal_text(
                    _first_nonblank(machines, "height_mm")
                ),
                "weight_kg": _positive_decimal_text(
                    _first_nonblank(machines, "weight_kg")
                ),
                "engineering_weight_g": _positive_decimal_text(
                    _first_nonblank(machines, "engineering_weight_g")
                ),
            },
            "outputs": outputs,
            "source_priority": {
                "machine_class": "机安" if machines else "单价回退",
                "arm_and_fixture": "机安" if machines else "无机安证据",
                "price": "单价",
            },
            "source_rows": [row["source"] for row in machines + prices],
        }
        mold_entries.append(mold_entry)
        capability_entries.append(
            {
                "mold_key": mold_key,
                "canonical_mold_no": mold_no,
                "machine_class": mold_entry["mold_a_class"],
                "machine_class_raw": raw_class,
                "required_arm_type": mold_entry["default_arm_type"],
                "required_fixture_type": mold_entry["default_fixture_type"],
                "process_limits": {
                    **mold_entry["engineering"],
                    "automation_mode": _first_nonblank(machines, "automation_mode"),
                    "engineering_advice": _first_nonblank(
                        machines, "engineering_advice"
                    ),
                },
                "source_priority": "机安" if machines else "单价回退",
                "source_rows": [row["source"] for row in preferred_rows],
            }
        )

    rate_entries: list[dict[str, Any]] = []
    invalid_rate_rows: list[dict[str, Any]] = []
    output_lookup: dict[tuple[str, tuple[str, ...]], str] = {}
    for mold in mold_entries:
        for output in mold["outputs"]:
            first_source = output["source_rows"][0]
            source_row = next(
                row
                for row in price_by_mold[mold["mold_key"]]
                if row["source"]["source_row"] == first_source["source_row"]
            )
            output_lookup[(mold["mold_key"], _output_identity(source_row["values"]))] = output[
                "output_key"
            ]
    seen_rates: set[str] = set()
    for row in price_rows:
        values = row["values"]
        amount = _positive_decimal_text(values.get("rate_value_raw", ""))
        if not amount:
            invalid_rate_rows.append(
                {
                    "mold_key": row["mold_key"],
                    "code": "RATE_MISSING_OR_INVALID",
                    "source": row["source"],
                }
            )
            continue
        output_key = output_lookup.get(
            (row["mold_key"], _output_identity(values)), ""
        )
        rate = {
            "rate_key": "",
            "mold_key": row["mold_key"],
            "canonical_mold_no": values.get("source_mold_no", "").strip(),
            "output_key": output_key,
            "item_no": values.get("item_no", "").strip(),
            "product_name": values.get("product_name", "").strip(),
            "customer_text": values.get("customer_text", "").strip(),
            "amount": amount,
            "pricing_basis": values.get("pricing_unit", "").strip(),
            "currency": values.get("currency", "").strip(),
            "tax_mode": values.get("tax_mode", "").strip(),
            "activation_blockers": [
                label
                for value, label in (
                    (values.get("pricing_unit", ""), "计价口径"),
                    (values.get("currency", ""), "币种"),
                    (values.get("tax_mode", ""), "税制"),
                    ("", "owner/厂区/客户/合同适用范围"),
                )
                if not str(value).strip()
            ],
            "source": row["source"],
        }
        rate["rate_key"] = _digest(
            {
                key: rate[key]
                for key in (
                    "mold_key",
                    "output_key",
                    "item_no",
                    "product_name",
                    "customer_text",
                    "amount",
                )
            }
        )
        if rate["rate_key"] in seen_rates:
            continue
        seen_rates.add(rate["rate_key"])
        rate_entries.append(rate)

    result = {
        "schema_version": CONSOLIDATION_SCHEMA_VERSION,
        "factory_id": factory_id,
        "source_file_name": source_file_name,
        "source_file_hash": source_file_hash,
        "source_size_bytes": len(content),
        "mappings": [machine_mapping, price_mapping],
        "mold_entries": mold_entries,
        "capability_entries": capability_entries,
        "rate_entries": rate_entries,
        "review_entries": review_entries,
        "invalid_rate_rows": invalid_rate_rows,
        "summary": {
            "price_source_rows": len(price_rows),
            "machine_source_rows": len(machine_rows),
            "mold_candidate_count": len(mold_entries),
            "capability_candidate_count": len(capability_entries),
            "rate_candidate_count": len(rate_entries),
            "review_mold_count": len(review_entries),
            "invalid_rate_row_count": len(invalid_rate_rows),
            "machine_priority_count": sum(
                entry["source_priority"] == "机安" for entry in capability_entries
            ),
            "price_fallback_count": sum(
                entry["source_priority"] == "单价回退"
                for entry in capability_entries
            ),
        },
    }
    result["consolidation_digest"] = _digest(result)
    return result


def _compact_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        key: source.get(key, "")
        for key in (
            "sheet_name",
            "source_row",
            "source_file_name",
            "source_file_hash",
        )
    }


def _compact_bundle_entry(value: Any) -> Any:
    if isinstance(value, list):
        return [_compact_bundle_entry(item) for item in value]
    if not isinstance(value, dict):
        return value
    if "sheet_name" in value and "source_row" in value:
        return _compact_source(value)
    return {key: _compact_bundle_entry(item) for key, item in value.items()}


def _proposal_evidence_rows(
    db: Session,
    *,
    proposal_id: str,
    entity_type: str,
    entries: list[dict[str, Any]],
    source_file_hash: str,
    submitted_by: str,
    timestamp: str,
) -> int:
    seen: set[tuple[str, int, str, str]] = set()
    created = 0

    def visit(value: Any, entity_key: str) -> None:
        nonlocal created
        if isinstance(value, list):
            for item in value:
                visit(item, entity_key)
            return
        if not isinstance(value, dict):
            return
        lineage = value.get("lineage")
        if isinstance(lineage, dict):
            sheet_name = str(value.get("sheet_name", ""))
            source_row = int(value.get("source_row") or 0)
            for field_name, evidence in lineage.items():
                if not isinstance(evidence, dict):
                    continue
                raw_value = str(evidence.get("raw_value", ""))
                displayed_value = str(evidence.get("displayed_value", ""))
                if not raw_value and not displayed_value:
                    continue
                cell_ref = str(evidence.get("cell_ref", ""))
                key = (sheet_name, source_row, str(field_name), cell_ref)
                if key in seen:
                    continue
                seen.add(key)
                db.add(
                    InjectionSchedulingFieldEvidence(
                        id=f"isfieldevidence-{_digest({'proposal': proposal_id, 'key': key})[:32]}",
                        proposal_id=proposal_id,
                        entity_type=entity_type,
                        entity_id=entity_key[:96],
                        field_name=str(field_name),
                        source_file_hash=source_file_hash,
                        sheet_name=sheet_name,
                        source_row=source_row,
                        cell_ref=cell_ref,
                        raw_value=raw_value,
                        displayed_value=displayed_value,
                        confidence="SOURCE_FACT",
                        submitted_by=submitted_by,
                        approved_by="",
                        created_at=timestamp,
                    )
                )
                created += 1
        for item in value.values():
            visit(item, entity_key)

    for entry in entries:
        entity_key = str(
            entry.get("mold_key")
            or entry.get("rate_key")
            or _digest(entry)
        )
        visit(entry, entity_key)
    return created


def stage_consolidated_master_data(
    db: Session,
    *,
    consolidated: dict[str, Any],
    proposed_by: str,
    proposed_by_name: str,
    reason: str,
) -> dict[str, Any]:
    """Persist three idempotent governed proposals from one consolidation result."""

    factory_id = str(consolidated.get("factory_id", "")).strip()
    company_scope_id = db.scalar(
        select(InjectionSchedulingCompanyFactoryMembership.company_scope_id).where(
            InjectionSchedulingCompanyFactoryMembership.factory_id == factory_id,
            InjectionSchedulingCompanyFactoryMembership.status == "ACTIVE",
        )
    )
    if not company_scope_id:
        raise HTTPException(status_code=409, detail="当前厂区没有 ACTIVE 公司归属")
    source_file_hash = str(consolidated.get("source_file_hash", ""))
    source_namespace_id = f"master-data:factory:{factory_id}:legacy-workbook"
    timestamp = _now()
    bundles = (
        (
            MOLD_BUNDLE_ENTITY,
            "COMPANY",
            str(company_scope_id),
            list(consolidated.get("mold_entries", [])),
            {
                "review_entries": consolidated.get("review_entries", []),
                "source_priority_policy": {
                    "machine_class": "机安；仅无机安记录时回退单价",
                    "arm_and_fixture": "机安",
                    "price": "单价",
                },
            },
        ),
        (
            CAPABILITY_BUNDLE_ENTITY,
            "FACTORY",
            factory_id,
            list(consolidated.get("capability_entries", [])),
            {},
        ),
        (
            RATE_BUNDLE_ENTITY,
            "FACTORY",
            factory_id,
            list(consolidated.get("rate_entries", [])),
            {
                "activation_blockers": [
                    "计价口径",
                    "币种",
                    "税制",
                    "owner/厂区/客户/合同适用范围",
                ],
                "invalid_rate_rows": consolidated.get("invalid_rate_rows", []),
            },
        ),
    )
    proposal_ids: dict[str, str] = {}
    created_proposals = 0
    created_evidence = 0
    for entity_type, scope_type, scope_id, entries, extra in bundles:
        request_id = (
            "master-bundle:"
            + _digest(
                {
                    "factory_id": factory_id,
                    "source_file_hash": source_file_hash,
                    "entity_type": entity_type,
                    "consolidation_digest": consolidated.get(
                        "consolidation_digest", ""
                    ),
                }
            )[:48]
        )
        existing = db.scalar(
            select(InjectionSchedulingMasterDataProposal).where(
                InjectionSchedulingMasterDataProposal.scope_type == scope_type,
                InjectionSchedulingMasterDataProposal.scope_id == scope_id,
                InjectionSchedulingMasterDataProposal.request_id == request_id,
            )
        )
        if existing is not None:
            proposal_ids[entity_type] = existing.id
            continue
        proposal_id = f"ismasterproposal-{_digest({'scope': scope_id, 'request': request_id})[:32]}"
        payload = {
            "schema_version": consolidated.get("schema_version", ""),
            "factory_id": factory_id,
            "source_namespace_id": source_namespace_id,
            "source_file_name": consolidated.get("source_file_name", ""),
            "source_file_hash": source_file_hash,
            "consolidation_digest": consolidated.get("consolidation_digest", ""),
            "summary": consolidated.get("summary", {}),
            "entries": _compact_bundle_entry(entries),
            **_compact_bundle_entry(extra),
        }
        proposal = InjectionSchedulingMasterDataProposal(
            id=proposal_id,
            entity_type=entity_type,
            action_type="CREATE",
            target_entity_id="",
            scope_type=scope_type,
            scope_id=scope_id,
            payload_json=_json(payload),
            evidence_digest=_digest(entries),
            status="PROPOSED",
            revision=1,
            request_id=request_id,
            proposed_by=proposed_by,
            proposed_by_name=proposed_by_name,
            approved_by="",
            approved_by_name="",
            reason=reason,
            created_at=timestamp,
            reviewed_at="",
        )
        db.add(proposal)
        created_evidence += _proposal_evidence_rows(
            db,
            proposal_id=proposal_id,
            entity_type=entity_type,
            entries=entries,
            source_file_hash=source_file_hash,
            submitted_by=proposed_by,
            timestamp=timestamp,
        )
        proposal_ids[entity_type] = proposal_id
        created_proposals += 1
    db.commit()
    return {
        "proposal_ids": proposal_ids,
        "created_proposals": created_proposals,
        "created_field_evidence": created_evidence,
        "summary": consolidated.get("summary", {}),
    }


def activate_mold_definition_bundle(
    db: Session,
    *,
    proposal: InjectionSchedulingMasterDataProposal,
    company_scope_id: str,
    factory_id: str,
    timestamp: str,
) -> dict[str, Any]:
    controlled = json.loads(proposal.payload_json)
    entries = list(controlled.get("entries", []))
    source_namespace_id = str(controlled.get("source_namespace_id", "")).strip()
    created_definitions = 0
    updated_definitions = 0
    created_outputs = 0
    updated_outputs = 0
    created_aliases = 0
    for entry in entries:
        mold_no = str(entry.get("canonical_mold_no", "")).strip()
        if not mold_no:
            continue
        definition = db.scalar(
            select(InjectionSchedulingMoldDefinition)
            .where(
                InjectionSchedulingMoldDefinition.company_scope_id
                == company_scope_id,
                InjectionSchedulingMoldDefinition.canonical_mold_no == mold_no,
                InjectionSchedulingMoldDefinition.status == "ACTIVE",
            )
            .with_for_update()
        )
        engineering_json = _json(
            {
                "source_file_hash": controlled.get("source_file_hash", ""),
                "source_priority": entry.get("source_priority", {}),
                **entry.get("engineering", {}),
            }
        )
        if definition is None:
            definition = InjectionSchedulingMoldDefinition(
                id=f"ismolddefinition-{_digest({'scope': company_scope_id, 'mold': mold_no})[:32]}",
                company_scope_id=company_scope_id,
                canonical_mold_no=mold_no,
                display_mold_no=str(entry.get("display_mold_no", mold_no)),
                standard_name=str(entry.get("standard_name", "")),
                recommended_machine_class_raw=str(
                    entry.get("recommended_machine_class_raw", "")
                ),
                mold_a_class=entry.get("mold_a_class"),
                default_arm_type=str(entry.get("default_arm_type", "")),
                default_fixture_type=str(entry.get("default_fixture_type", "")),
                process_tags_json=_json(entry.get("process_tags", [])),
                engineering_json=engineering_json,
                status="ACTIVE",
                data_quality="APPROVED_SOURCE",
                revision=1,
                valid_from=timestamp,
                valid_to="",
                proposal_id=proposal.id,
                created_factory_id=factory_id,
                created_by=proposal.proposed_by,
                approved_by=proposal.approved_by,
                created_at=timestamp,
                approved_at=proposal.reviewed_at,
            )
            db.add(definition)
            db.flush()
            created_definitions += 1
        else:
            definition.display_mold_no = str(
                entry.get("display_mold_no", definition.display_mold_no)
            )
            definition.standard_name = str(
                entry.get("standard_name", definition.standard_name)
            )
            definition.recommended_machine_class_raw = str(
                entry.get(
                    "recommended_machine_class_raw",
                    definition.recommended_machine_class_raw,
                )
            )
            definition.mold_a_class = entry.get("mold_a_class")
            definition.default_arm_type = str(
                entry.get("default_arm_type", definition.default_arm_type)
            )
            definition.default_fixture_type = str(
                entry.get("default_fixture_type", definition.default_fixture_type)
            )
            definition.process_tags_json = _json(entry.get("process_tags", []))
            definition.engineering_json = engineering_json
            definition.proposal_id = proposal.id
            definition.approved_by = proposal.approved_by
            definition.approved_at = proposal.reviewed_at
            definition.revision += 1
            updated_definitions += 1

        for raw_alias in entry.get("raw_aliases", []):
            normalized_alias = normalize_identifier(raw_alias)
            alias = db.scalar(
                select(InjectionSchedulingMoldAlias).where(
                    InjectionSchedulingMoldAlias.company_scope_id == company_scope_id,
                    InjectionSchedulingMoldAlias.source_namespace_id
                    == source_namespace_id,
                    InjectionSchedulingMoldAlias.normalized_alias == normalized_alias,
                    InjectionSchedulingMoldAlias.status == "ACTIVE",
                )
            )
            if alias is not None and alias.mold_definition_id != definition.id:
                raise HTTPException(
                    status_code=409,
                    detail=f"模具别名 {raw_alias} 已指向其他共享定义",
                )
            if alias is None:
                db.add(
                    InjectionSchedulingMoldAlias(
                        id=f"ismoldalias-{_digest({'namespace': source_namespace_id, 'alias': normalized_alias})[:32]}",
                        company_scope_id=company_scope_id,
                        source_namespace_id=source_namespace_id,
                        namespace_type="MASTER_DATA_SOURCE",
                        raw_alias=str(raw_alias),
                        normalized_alias=normalized_alias,
                        mold_definition_id=definition.id,
                        status="ACTIVE",
                        revision=1,
                        valid_from=timestamp,
                        valid_to="",
                        proposal_id=proposal.id,
                        created_at=timestamp,
                    )
                )
                created_aliases += 1

        for output_entry in entry.get("outputs", []):
            output = db.scalar(
                select(InjectionSchedulingMoldOutputSpec)
                .where(
                    InjectionSchedulingMoldOutputSpec.mold_definition_id
                    == definition.id,
                    InjectionSchedulingMoldOutputSpec.customer_identity_id.is_(None),
                    InjectionSchedulingMoldOutputSpec.item_no
                    == str(output_entry.get("item_no", "")),
                    InjectionSchedulingMoldOutputSpec.variant_code
                    == str(output_entry.get("variant_code", "")),
                    InjectionSchedulingMoldOutputSpec.status == "ACTIVE",
                )
                .with_for_update()
            )
            evidence_json = _json(
                {
                    "output_key": output_entry.get("output_key", ""),
                    "proposal_id": proposal.id,
                    "source_rows": output_entry.get("source_rows", []),
                }
            )
            values = {
                "product_name": str(output_entry.get("product_name", "")),
                "cavity_count": output_entry.get("cavity_count"),
                "whole_shot_net_weight_g": output_entry.get(
                    "whole_shot_net_weight_g"
                )
                or None,
                "whole_shot_gross_weight_g": output_entry.get(
                    "whole_shot_gross_weight_g"
                )
                or None,
                "default_material": str(output_entry.get("default_material", "")),
                "default_color": str(output_entry.get("default_color", "")),
                "nominal_daily_capacity": output_entry.get(
                    "nominal_daily_capacity"
                )
                or None,
            }
            if output is None:
                output = InjectionSchedulingMoldOutputSpec(
                    id=f"ismoldoutput-{str(output_entry.get('output_key', _digest(output_entry)))[:32]}",
                    mold_definition_id=definition.id,
                    customer_identity_id=None,
                    item_no=str(output_entry.get("item_no", "")),
                    variant_code=str(output_entry.get("variant_code", "")),
                    units_per_shot=None,
                    nominal_cycle_seconds=None,
                    status="ACTIVE",
                    revision=1,
                    valid_from=timestamp,
                    valid_to="",
                    proposal_id=proposal.id,
                    evidence_json=evidence_json,
                    created_at=timestamp,
                    **values,
                )
                db.add(output)
                created_outputs += 1
            else:
                for field, value in values.items():
                    setattr(output, field, value)
                output.proposal_id = proposal.id
                output.evidence_json = evidence_json
                output.revision += 1
                updated_outputs += 1
    return {
        "created_definitions": created_definitions,
        "updated_definitions": updated_definitions,
        "created_aliases": created_aliases,
        "created_outputs": created_outputs,
        "updated_outputs": updated_outputs,
    }


def activate_factory_capability_bundle(
    db: Session,
    *,
    proposal: InjectionSchedulingMasterDataProposal,
    company_scope_id: str,
    factory_id: str,
    timestamp: str,
) -> dict[str, Any]:
    controlled = json.loads(proposal.payload_json)
    created = 0
    updated = 0
    missing_definitions: list[str] = []
    definitions = {
        item.canonical_mold_no: item
        for item in db.scalars(
            select(InjectionSchedulingMoldDefinition).where(
                InjectionSchedulingMoldDefinition.company_scope_id
                == company_scope_id,
                InjectionSchedulingMoldDefinition.status == "ACTIVE",
            )
        ).all()
    }
    existing_capabilities = {
        (item.applicability_key, item.priority): item
        for item in db.scalars(
            select(InjectionSchedulingFactoryMoldCapability)
            .where(
                InjectionSchedulingFactoryMoldCapability.factory_id == factory_id,
                InjectionSchedulingFactoryMoldCapability.status == "ACTIVE",
            )
            .with_for_update()
        ).all()
    }
    for entry in controlled.get("entries", []):
        mold_no = str(entry.get("canonical_mold_no", "")).strip()
        definition = definitions.get(mold_no)
        if definition is None:
            missing_definitions.append(mold_no)
            continue
        applicability_key = _digest(
            {
                "factory_id": factory_id,
                "mold_definition_id": definition.id,
                "scope": "DEFINITION_DEFAULT",
            }
        )[:64]
        capability = existing_capabilities.get((applicability_key, 100))
        values = {
            "machine_class": entry.get("machine_class"),
            "required_arm_type": str(entry.get("required_arm_type", "")),
            "required_fixture_type": str(entry.get("required_fixture_type", "")),
            "process_limits_json": _json(
                {
                    **entry.get("process_limits", {}),
                    "machine_class_raw": entry.get("machine_class_raw", ""),
                    "source_priority": entry.get("source_priority", ""),
                    "source_file_hash": controlled.get("source_file_hash", ""),
                }
            ),
        }
        if capability is None:
            capability = InjectionSchedulingFactoryMoldCapability(
                id=f"isfactorycapability-{applicability_key[:32]}",
                factory_id=factory_id,
                mold_definition_id=definition.id,
                mold_output_spec_id=None,
                physical_asset_id=None,
                applicability_key=applicability_key,
                nominal_cycle_seconds=None,
                nominal_daily_capacity=None,
                setup_minutes=0,
                priority=100,
                status="ACTIVE",
                revision=1,
                valid_from=timestamp,
                valid_to="",
                proposal_id=proposal.id,
                approved_by=proposal.approved_by,
                approved_at=proposal.reviewed_at,
                created_at=timestamp,
                **values,
            )
            db.add(capability)
            existing_capabilities[(applicability_key, 100)] = capability
            created += 1
        else:
            for field, value in values.items():
                setattr(capability, field, value)
            capability.proposal_id = proposal.id
            capability.approved_by = proposal.approved_by
            capability.approved_at = proposal.reviewed_at
            capability.revision += 1
            updated += 1
    if missing_definitions:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MOLD_DEFINITION_ACTIVATION_REQUIRED",
                "message": "必须先激活共享模具定义，再激活华兴机安能力",
                "missing_count": len(missing_definitions),
                "sample_mold_nos": missing_definitions[:20],
            },
        )
    return {"created_capabilities": created, "updated_capabilities": updated}


def activate_commercial_rate_bundle(
    db: Session,
    *,
    proposal: InjectionSchedulingMasterDataProposal,
    company_scope_id: str,
    factory_id: str,
    timestamp: str,
    pricing_basis: str,
    currency: str,
    tax_mode: str,
) -> dict[str, Any]:
    """Activate unambiguous workbook prices for one factory.

    The controlled Huaxing workbook defines ``单价`` as the per-shot total.  A
    rate is activated only when its source row resolves to exactly one active
    output specification.  Duplicate prices for the same output are retained
    in the proposal for review instead of being silently ordered by sheet row.
    """

    controlled = json.loads(proposal.payload_json)
    entries = list(controlled.get("entries", []))
    output_key_counts = Counter(
        str(entry.get("output_key", "")).strip()
        for entry in entries
        if str(entry.get("output_key", "")).strip()
    )

    outputs_by_key: dict[str, InjectionSchedulingMoldOutputSpec] = {}
    outputs = db.scalars(
        select(InjectionSchedulingMoldOutputSpec)
        .join(
            InjectionSchedulingMoldDefinition,
            InjectionSchedulingMoldDefinition.id
            == InjectionSchedulingMoldOutputSpec.mold_definition_id,
        )
        .where(
            InjectionSchedulingMoldDefinition.company_scope_id == company_scope_id,
            InjectionSchedulingMoldDefinition.status == "ACTIVE",
            InjectionSchedulingMoldOutputSpec.status == "ACTIVE",
        )
    ).all()
    for output in outputs:
        try:
            evidence = json.loads(output.evidence_json or "{}")
        except json.JSONDecodeError:
            continue
        output_key = str(evidence.get("output_key", "")).strip()
        if output_key:
            outputs_by_key[output_key] = output

    existing_by_output: dict[str, InjectionSchedulingCommercialRateRule] = {}
    for rule in db.scalars(
        select(InjectionSchedulingCommercialRateRule)
        .where(
            InjectionSchedulingCommercialRateRule.owner_scope_type == "FACTORY",
            InjectionSchedulingCommercialRateRule.owner_scope_id == factory_id,
            InjectionSchedulingCommercialRateRule.applicable_factory_mode
            == "SPECIFIC",
            InjectionSchedulingCommercialRateRule.applicable_factory_id == factory_id,
            InjectionSchedulingCommercialRateRule.applicable_customer_mode == "ANY",
            InjectionSchedulingCommercialRateRule.contract_mode == "ANY",
            InjectionSchedulingCommercialRateRule.pricing_basis == pricing_basis,
            InjectionSchedulingCommercialRateRule.currency == currency,
            InjectionSchedulingCommercialRateRule.tax_mode == tax_mode,
            InjectionSchedulingCommercialRateRule.status == "ACTIVE",
        )
        .with_for_update()
    ).all():
        output_id = str(rule.mold_output_spec_id or "")
        if output_id in existing_by_output:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DUPLICATE_ACTIVE_RATE_RULE",
                    "message": "同一华兴模具产品已有多条生效单价，必须先治理重复规则",
                    "mold_output_spec_id": output_id,
                },
            )
        existing_by_output[output_id] = rule

    created = 0
    updated = 0
    missing_output_entries: list[dict[str, Any]] = []
    duplicate_entries: list[dict[str, Any]] = []
    for entry in entries:
        output_key = str(entry.get("output_key", "")).strip()
        if not output_key:
            missing_output_entries.append(entry)
            continue
        if output_key_counts[output_key] > 1:
            duplicate_entries.append(entry)
            continue
        output = outputs_by_key.get(output_key)
        if output is None:
            missing_output_entries.append(entry)
            continue
        amount = _decimal(entry.get("amount"))
        if amount is None or amount <= 0:
            missing_output_entries.append(entry)
            continue

        rule = existing_by_output.get(output.id)
        values = {
            "mold_definition_id": output.mold_definition_id,
            "mold_output_spec_id": output.id,
            "amount": amount,
            "proposal_id": proposal.id,
            "proposed_by": proposal.proposed_by,
            "approved_by": proposal.approved_by,
            "approved_at": proposal.reviewed_at,
        }
        if rule is None:
            rule = InjectionSchedulingCommercialRateRule(
                id=f"iscommercialrate-{_digest({'factory': factory_id, 'output': output.id, 'basis': pricing_basis, 'currency': currency})[:32]}",
                owner_scope_type="FACTORY",
                owner_scope_id=factory_id,
                applicable_factory_mode="SPECIFIC",
                applicable_factory_id=factory_id,
                applicable_customer_mode="ANY",
                applicable_customer_id=None,
                contract_mode="ANY",
                contract_id=None,
                pricing_basis=pricing_basis,
                currency=currency,
                tax_mode=tax_mode,
                quantity_min=None,
                quantity_max=None,
                priority=100,
                status="ACTIVE",
                revision=1,
                valid_from=timestamp,
                valid_to="",
                created_at=timestamp,
                **values,
            )
            db.add(rule)
            existing_by_output[output.id] = rule
            created += 1
        else:
            for field, value in values.items():
                setattr(rule, field, value)
            rule.revision += 1
            updated += 1

    duplicate_output_keys = {
        str(entry.get("output_key", "")).strip()
        for entry in duplicate_entries
        if str(entry.get("output_key", "")).strip()
    }
    return {
        "created_rate_rules": created,
        "updated_rate_rules": updated,
        "missing_output_entry_count": len(missing_output_entries),
        "duplicate_output_count": len(duplicate_output_keys),
        "duplicate_rate_entry_count": len(duplicate_entries),
        "review_samples": [
            {
                "canonical_mold_no": entry.get("canonical_mold_no", ""),
                "item_no": entry.get("item_no", ""),
                "product_name": entry.get("product_name", ""),
                "amount": entry.get("amount", ""),
                "source": entry.get("source", {}),
            }
            for entry in (duplicate_entries + missing_output_entries)[:20]
        ],
    }
