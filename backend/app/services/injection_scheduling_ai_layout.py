from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.schemas.ai.workbook import (
    AI_INJECTION_PLAN_REQUIRED_FIELDS,
    AIInjectionPlanLayoutRecognitionV1,
)
from app.services.injection_scheduling_canonical import parse_canonical_workbook
from app.services.injection_scheduling_excel import _WorkbookReader
from app.services.injection_scheduling_profiles import (
    FieldRule,
    ImportProfile,
    SheetRoleRule,
)

AI_LAYOUT_PARSER_VERSION = "injection-scheduling-ai-layout-parser-v1"


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
        item
        for item in layout.field_mappings
        if item.canonical_field == "machine_code"
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
    cloud_ai_consent: bool = False,
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
        "cloud_ai_consent": cloud_ai_consent,
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
    normalized["normalized_sha256"] = hashlib.sha256(_json(normalized).encode()).hexdigest()
    return normalized, issues
