from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.schemas.ai.workbook import (
    AI_INJECTION_DEMAND_REQUIRED_FIELDS,
    AI_INJECTION_PLAN_REQUIRED_FIELDS,
    AIInjectionPlanLayoutRecognitionV1,
    AIInjectionWorkbookMappingV1,
)
from app.services.ai.workbook_recognition_packet import source_sheet_mode
from app.services.injection_scheduling_canonical import parse_canonical_workbook
from app.services.injection_scheduling_demand_import import parse_demand_order_workbook
from app.services.injection_scheduling_excel import _WorkbookReader
from app.services.injection_scheduling_profiles import (
    FieldRule,
    ImportProfile,
    SheetRoleRule,
    profile_config,
    profile_from_config,
)

AI_LAYOUT_PARSER_VERSION = "injection-scheduling-ai-layout-parser-v1"
AI_MAPPING_PARSER_VERSION = "injection-scheduling-ai-workbook-mapping-parser-v1"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _cell_row(cell_ref: str) -> int:
    match = re.fullmatch(r"[A-Z]{1,4}([1-9][0-9]{0,6})", cell_ref)
    if match is None:
        raise ValueError("无效的表头单元格")
    return int(match.group(1))


def _header_values(
    reader: _WorkbookReader,
    *,
    sheet_name: str,
    layout: AIInjectionPlanLayoutRecognitionV1,
) -> dict[str, str]:
    needed_rows = {_cell_row(item.header_cell) for item in layout.field_mappings}
    needed_refs = {item.header_cell for item in layout.field_mappings}
    result: dict[str, str] = {}
    for row_number, cells in reader.rows(sheet_name):
        if row_number not in needed_rows:
            continue
        for cell in cells.values():
            reference = str(cell.get("reference", ""))
            if reference in needed_refs:
                result[reference] = reader.identifier(cell)
        if len(result) == len(needed_refs):
            break
    return result


def _ephemeral_profile(
    reader: _WorkbookReader,
    layout: AIInjectionPlanLayoutRecognitionV1,
    factory_id: str,
) -> ImportProfile:
    sheet_name = layout.plan_sheet.sheet_name
    headers = _header_values(reader, sheet_name=sheet_name, layout=layout)
    fields = tuple(
        FieldRule(
            rule_id=f"ai-layout:{layout.layout_digest}:{item.canonical_field}",
            canonical_field=item.canonical_field,
            column=item.source_column,
            headers=(headers[item.header_cell],),
            converter=item.transformer,
            required=item.canonical_field in AI_INJECTION_PLAN_REQUIRED_FIELDS,
            selector_strategy="AI_HEADER_CELL",
            header_row=_cell_row(item.header_cell),
        )
        for item in layout.field_mappings
    )
    shift_start = layout.shift_grid.start_column if layout.shift_grid.enabled else "XFD"
    shift_end = layout.shift_grid.end_column if layout.shift_grid.enabled else "XFD"
    return ImportProfile(
        profile_id=f"ai-layout-{layout.layout_digest[:32]}",
        profile_code="ai_layout_v1",
        profile_family="ai_layout",
        revision=1,
        name="AI 验证布局",
        factories=(factory_id,),
        status="VALIDATED_EPHEMERAL",
        sheet_roles=(
            SheetRoleRule(
                role="CURRENT_PLAN",
                names=(sheet_name,),
                required=True,
                header_row=max(layout.plan_sheet.header_rows),
            ),
        ),
        fields=fields,
        machine_adapter="system_master_only",
        mold_adapter="system_master_only",
        dynamic_shift_start=shift_start,
        dynamic_shift_end=shift_end,
        quantity_scope="ORDER_CUMULATIVE",
        renderer_code="system_standard_v1",
    )


def _recognized_machine_codes(
    reader: _WorkbookReader,
    layout: AIInjectionPlanLayoutRecognitionV1,
) -> set[str]:
    if layout.row_layout.layout_type != "GROUPED_BY_MACHINE":
        return set()
    rule = layout.row_layout.machine_header_rule
    columns = layout.row_layout.machine_header_columns
    machine_mapping = next(
        item for item in layout.field_mappings if item.canonical_field == "machine_code"
    )
    identity_columns = {
        item.source_column
        for item in layout.field_mappings
        if item.canonical_field in layout.row_layout.task_identity_fields
    }
    result: set[str] = set()
    for row_number, cells in reader.rows(layout.plan_sheet.sheet_name):
        if row_number < layout.plan_sheet.data_start_row:
            continue
        if row_number > layout.plan_sheet.data_end_row:
            break
        if rule == "SAME_VALUE_IN_TWO_COLUMNS":
            values = [reader.identifier(cells.get(column)) for column in columns]
            if len(values) == 2 and values[0] and values[0] == values[1]:
                result.add(values[1])
        elif rule == "MACHINE_CODE_WITHOUT_BUSINESS_IDENTITY":
            machine = reader.identifier(cells.get(machine_mapping.source_column))
            has_identity = any(
                reader.identifier(cells.get(column)) for column in identity_columns
            )
            if machine and not has_identity:
                result.add(machine)
    return result


def parse_ai_layout_workbook(
    content: bytes,
    source_file_name: str,
    *,
    factory_id: str,
    layout: AIInjectionPlanLayoutRecognitionV1,
    packet_digest: str,
    business_date: str,
    requested_mode: str,
    cache_hit: bool = False,
    system_machine_codes: set[str] | None = None,
    system_mold_nos: set[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_hash = hashlib.sha256(content).hexdigest()
    if source_hash != layout.source_sha256:
        raise ValueError("AI 布局与当前文件 SHA 不一致")
    reader = _WorkbookReader(content)
    try:
        if layout.plan_sheet.sheet_name not in reader.sheet_paths:
            raise ValueError("AI 布局引用的 Sheet 不存在")
        profile = _ephemeral_profile(reader, layout, factory_id)
        recognized_machine_codes = _recognized_machine_codes(reader, layout)
        normalized, issues = parse_canonical_workbook(
            reader,
            source_file_name=source_file_name,
            source_file_hash=source_hash,
            source_size_bytes=len(content),
            factory_id=factory_id,
            system_machine_codes=system_machine_codes,
            system_mold_nos=system_mold_nos,
            profiles=(profile,),
            layout_override={
                "data_start_row": layout.plan_sheet.data_start_row,
                "data_end_row": layout.plan_sheet.data_end_row,
                "row_layout": layout.row_layout.model_dump(mode="json"),
            },
            additional_known_machine_codes=recognized_machine_codes,
        )
    finally:
        reader.close()

    recognition = {
        "mode": "AI_LAYOUT",
        "requested_mode": requested_mode,
        "model": layout.generated_by_model,
        "prompt_version": layout.prompt_version,
        "layout_schema_version": layout.schema_version,
        "layout_digest": layout.layout_digest,
        "packet_digest": packet_digest,
        "source_sha256": layout.source_sha256,
        "business_date": business_date,
        "sheet_name": layout.plan_sheet.sheet_name,
        "overall_confidence": layout.overall_confidence,
        "cache_hit": cache_hit,
        "layout": layout.model_dump(mode="json"),
    }
    normalized["parser_version"] = AI_LAYOUT_PARSER_VERSION
    normalized["recognition"] = recognition
    normalized["profile"] = {
        **(normalized.get("profile") or {}),
        "profile_id": None,
        "profile_code": "ai_layout_v1",
        "profile_family": "ai_layout",
        "status": "VALIDATED_EPHEMERAL",
        "recognition_method": "AI_LAYOUT_VALIDATED",
        "definition_digest": layout.layout_digest,
        "renderer_code": "system_standard_v1",
    }
    normalized["summary"].update(
        {
            "recognition_mode": "AI_LAYOUT",
            "recognition_model": layout.generated_by_model,
            "recognition_sheet": layout.plan_sheet.sheet_name,
            "recognition_confidence": layout.overall_confidence,
            "recognized_machine_count": len(recognized_machine_codes),
            "low_confidence_field_count": sum(
                item.confidence < 0.8 for item in layout.field_mappings
            ),
        }
    )
    normalized["mapping_fingerprint"] = hashlib.sha256(
        _json(normalized.get("mapping", [])).encode()
    ).hexdigest()
    normalized["template_signature"] = layout.layout_digest
    normalized.pop("normalized_sha256", None)
    normalized["normalized_sha256"] = hashlib.sha256(
        _json(normalized).encode()
    ).hexdigest()
    return normalized, issues


def _legacy_plan_layout(
    mapping: AIInjectionWorkbookMappingV1,
    *,
    business_date: str,
) -> AIInjectionPlanLayoutRecognitionV1:
    payload = {
        "schema_version": "injection-plan-layout-recognition-v1",
        "document_kind": "PLANNED_SCHEDULE",
        "source_sha256": mapping.source_sha256,
        "plan_sheet": mapping.source_sheet.model_dump(mode="json"),
        "row_layout": {
            key: value
            for key, value in mapping.row_layout.model_dump(mode="json").items()
            if key != "termination"
        },
        "field_mappings": [
            item.model_dump(mode="json") for item in mapping.field_mappings
        ],
        "shift_grid": {
            "enabled": mapping.shift_grid.enabled,
            "start_column": mapping.shift_grid.start_column,
            "end_column": mapping.shift_grid.end_column,
            "day_header_row": mapping.shift_grid.date_header_row,
            "shift_header_row": mapping.shift_grid.shift_header_row,
            "calendar_month": business_date[:7] if mapping.shift_grid.enabled else "",
            "day_shift_aliases": mapping.shift_grid.day_shift_aliases,
            "quantity_semantics": (
                "COMPLETED_OUTPUT"
                if mapping.shift_grid.enabled
                else "COMPLETED_OR_PLANNED_OUTPUT"
            ),
        },
        "warnings": mapping.warnings,
        "overall_confidence": mapping.overall_confidence,
    }
    digest = hashlib.sha256(_json(payload).encode()).hexdigest()
    return AIInjectionPlanLayoutRecognitionV1(
        **payload,
        generated_by_model=mapping.generated_by_model,
        layout_digest=digest,
    )


def profile_config_from_ai_mapping(
    mapping: AIInjectionWorkbookMappingV1,
    *,
    factory_id: str,
    structural_signature: str,
    header_values: dict[str, str],
    recognition_method: str = "AI_SKILL",
) -> dict[str, Any]:
    is_demand = mapping.document_kind == "DEMAND_ORDER"
    family = f"workbench_ai_{mapping.document_kind.lower()}_{structural_signature[:12]}"
    sheet_names = (
        tuple(f"{month}月" for month in range(1, 13))
        if source_sheet_mode(mapping.source_sheet.sheet_name) == "MONTH_SHEET"
        else (mapping.source_sheet.sheet_name,)
    )
    required_fields = (
        AI_INJECTION_DEMAND_REQUIRED_FIELDS
        if is_demand
        else AI_INJECTION_PLAN_REQUIRED_FIELDS
    )
    fields = tuple(
        FieldRule(
            rule_id=f"{family}:{item.canonical_field}:r1",
            canonical_field=item.canonical_field,
            column=item.source_column,
            headers=(header_values.get(item.header_cell) or item.canonical_field,),
            converter=item.transformer,
            required=item.canonical_field in required_fields,
            selector_strategy="AI_HEADER_CELL",
            header_row=_cell_row(item.header_cell),
        )
        for item in mapping.field_mappings
    )
    recognition = {
        "method": recognition_method,
        "skill_id": mapping.skill_id,
        "skill_version": mapping.skill_version,
        "prompt_version": mapping.prompt_version,
        "structural_layout_signature": structural_signature,
        "source_sheet_mode": source_sheet_mode(mapping.source_sheet.sheet_name),
        "source_sheet": mapping.source_sheet.model_dump(mode="json"),
        "row_layout": mapping.row_layout.model_dump(mode="json"),
        "metadata_anchors": [
            item.model_dump(mode="json") for item in mapping.metadata_anchors
        ],
        "shift_grid": mapping.shift_grid.model_dump(mode="json"),
    }
    profile = ImportProfile(
        profile_id=f"ai-profile-{structural_signature[:24]}",
        profile_code=f"{family}_v1",
        profile_family=family,
        revision=1,
        name=(
            f"{factory_id} · 智能识别下单表"
            if is_demand
            else f"{factory_id} · 智能识别计划表"
        ),
        factories=(factory_id,),
        status="PROFILE_DRAFT",
        sheet_roles=(
            SheetRoleRule(
                role="ORDER_SOURCE" if is_demand else "CURRENT_PLAN",
                names=sheet_names,
                required=True,
                header_row=max(mapping.source_sheet.header_rows),
            ),
        ),
        fields=fields,
        machine_adapter="system_master_only",
        mold_adapter="system_master_only",
        dynamic_shift_start=(
            mapping.shift_grid.start_column if mapping.shift_grid.enabled else "A"
        ),
        dynamic_shift_end=(
            mapping.shift_grid.end_column if mapping.shift_grid.enabled else "A"
        ),
        quantity_scope="ORDER_CUMULATIVE",
        renderer_code=("demand_order_review_v1" if is_demand else "system_standard_v1"),
        document_kind=mapping.document_kind,
        source_namespace_id="demand-order:company" if is_demand else "",
        recognition_config=recognition,
    )
    return profile_config(profile)


def parse_ai_workbook_mapping(
    db,
    content: bytes,
    source_file_name: str,
    *,
    factory_id: str,
    mapping: AIInjectionWorkbookMappingV1,
    packet_digest: str,
    structural_signature: str,
    business_date: str,
    requested_mode: str,
    system_machine_codes: set[str] | None = None,
    system_mold_nos: set[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_hash = hashlib.sha256(content).hexdigest()
    if source_hash != mapping.source_sha256:
        raise ValueError("AI 映射与当前文件 SHA 不一致")
    reader = _WorkbookReader(content)
    try:
        needed_refs = {item.header_cell for item in mapping.field_mappings}
        needed_rows = set(mapping.source_sheet.header_rows)
        header_values: dict[str, str] = {}
        all_header_values: dict[str, str] = {}
        for row_number, cells in reader.rows(mapping.source_sheet.sheet_name):
            if row_number not in needed_rows:
                continue
            for cell in cells.values():
                reference = str(cell.get("reference", ""))
                value = reader.identifier(cell)
                if value:
                    all_header_values[reference] = value
                if reference in needed_refs:
                    header_values[reference] = value
            if row_number >= max(needed_rows):
                break
    finally:
        reader.close()
    config = profile_config_from_ai_mapping(
        mapping,
        factory_id=factory_id,
        structural_signature=structural_signature,
        header_values=header_values,
    )
    profile = profile_from_config(config)
    if mapping.document_kind == "DEMAND_ORDER":
        normalized, issues = parse_demand_order_workbook(
            db,
            content,
            source_file_name,
            factory_id=factory_id,
            profile=profile,
            layout_override=mapping,
        )
    else:
        normalized, issues = parse_ai_layout_workbook(
            content,
            source_file_name,
            factory_id=factory_id,
            layout=_legacy_plan_layout(mapping, business_date=business_date),
            packet_digest=packet_digest,
            business_date=business_date,
            requested_mode=requested_mode,
            system_machine_codes=system_machine_codes,
            system_mold_nos=system_mold_nos,
        )
    confidence_by_field = {
        item.canonical_field: (item.confidence, item.reason)
        for item in mapping.field_mappings
    }
    for item in normalized.get("mapping", []):
        confidence, reason = confidence_by_field.get(
            str(item.get("canonical_field", "")), (0.0, "")
        )
        item["confidence_score"] = confidence
        item["confidence_reason"] = reason
        item["mapping_source"] = "AI_SKILL"
    mapped_header_refs = {item.header_cell for item in mapping.field_mappings}
    for cell_ref, raw_header in all_header_values.items():
        if cell_ref in mapped_header_refs:
            continue
        match = re.fullmatch(r"([A-Z]{1,4})([1-9][0-9]{0,6})", cell_ref)
        if match is None:
            continue
        normalized.setdefault("mapping", []).append(
            {
                "rule_id": "",
                "rule_revision": 0,
                "sheet_role": "ORDER_SOURCE"
                if mapping.document_kind == "DEMAND_ORDER"
                else "CURRENT_PLAN",
                "sheet_name": mapping.source_sheet.sheet_name,
                "header_row": int(match.group(2)),
                "column": match.group(1),
                "source_column": match.group(1),
                "raw_header": raw_header,
                "normalized_header": re.sub(r"\s+", "", raw_header).lower(),
                "canonical_field": "",
                "converter": "text",
                "unit": "",
                "required": False,
                "status": "AVAILABLE_SOURCE",
                "mapping_method": "UNASSIGNED_HEADER",
                "confidence": "NONE",
                "confidence_score": 0.0,
                "confidence_reason": "可供人工修正选择的真实来源表头",
                "mapping_source": "SOURCE_HEADER",
                "authority": "SOURCE_ONLY",
                "sample_values": [],
            }
        )
    recognition = {
        "mode": "AI_SKILL",
        "requested_mode": requested_mode,
        "source": "AI_SKILL",
        "model": mapping.generated_by_model,
        "skill_id": mapping.skill_id,
        "skill_version": mapping.skill_version,
        "prompt_version": mapping.prompt_version,
        "mapping_digest": mapping.mapping_digest,
        "packet_digest": packet_digest,
        "structural_layout_signature": structural_signature,
        "source_sha256": mapping.source_sha256,
        "business_date": business_date,
        "sheet_name": mapping.source_sheet.sheet_name,
        "overall_confidence": mapping.overall_confidence,
        "template_hit": False,
        "mapping": mapping.model_dump(mode="json"),
        "profile_config": config,
    }
    normalized["recognition"] = recognition
    normalized["parser_version"] = AI_MAPPING_PARSER_VERSION
    normalized["template_signature"] = structural_signature
    normalized["profile"] = {
        **(normalized.get("profile") or {}),
        "profile_id": None,
        "profile_code": config["profile_code"],
        "profile_family": config["profile_family"],
        "revision": None,
        "status": "VALIDATED_EPHEMERAL",
        "recognition_method": "AI_SKILL_VALIDATED",
        "definition_digest": mapping.mapping_digest,
        "renderer_code": config["renderer_code"],
    }
    normalized.get("summary", {}).update(
        {
            "recognition_mode": "AI_SKILL",
            "recognition_source": "AI_SKILL",
            "recognition_model": mapping.generated_by_model,
            "recognition_sheet": mapping.source_sheet.sheet_name,
            "recognition_confidence": mapping.overall_confidence,
            "low_confidence_field_count": sum(
                item.confidence < 0.85 for item in mapping.field_mappings
            ),
            "metadata_anchor_count": len(mapping.metadata_anchors),
        }
    )
    normalized.pop("normalized_sha256", None)
    normalized["normalized_sha256"] = hashlib.sha256(
        _json(normalized).encode()
    ).hexdigest()
    return normalized, issues
