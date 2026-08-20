from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.injection_scheduling_demand_import import master_revision_digest
from app.services.injection_scheduling_excel import (
    _clean_text,
    _issue,
    _WorkbookReader,
)
from app.services.injection_scheduling_profiles import (
    ImportProfile,
    normalize_header,
    profile_definition_digest,
    profile_header_fingerprint,
    profile_template_signature,
)

MASTER_SCHEMA_VERSION = "injection-scheduling-master-data-v1"
MASTER_PARSER_VERSION = "injection-scheduling-master-data-parser-v1"

SHEET_ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "MOLD_DEFINITION_SOURCE": ("机安", "模具资料", "模具主数据"),
    "PRICE_RULE_SOURCE": ("单价", "价格", "价格规则"),
}

MOLD_HEADERS: dict[str, tuple[str, ...]] = {
    "source_mold_no": ("工模", "工模编号", "模具编号", "模号"),
    "standard_name": ("工模名称", "模具名称", "产品名称", "名称"),
    "item_no": ("货号", "产品编号", "产品编码", "配件编号"),
    "output_name": ("配件名称", "输出名称", "产品名称"),
    "recommended_machine_class_raw": ("安数", "机安", "机型", "推荐机型"),
    "cavity_count": ("模具安数", "出数", "腔数", "一啤出数"),
    "nominal_daily_capacity": ("模具日产量", "日产量", "日啤数"),
    "whole_shot_gross_weight_g": ("整啤毛重", "毛重"),
    "whole_shot_net_weight_g": ("整啤净重", "净重"),
    "required_arm_type": ("单双臂", "机械手"),
    "required_fixture_type": ("气剪", "夹具", "吸盘"),
    "material_name": ("用料名称", "用料", "材料名称"),
    "color_name": ("颜色",),
    "engineering_weight_g": ("工程重量(G)", "工程重量（G）", "工程重量"),
    "length_mm": ("length", "模具长度", "长"),
    "width_mm": ("width", "模具宽度", "宽"),
    "height_mm": ("height", "模具高度", "高"),
    "weight_kg": ("weight kg", "模具重量", "重量KG"),
    "automation_mode": ("是否可上自动拉",),
    "engineering_advice": ("建议",),
    "location_text": ("位置", "存放位置", "所在厂区"),
    "asset_no": ("资产编号", "模具资产号", "副号"),
    "remark": ("备注", "说明"),
}

PRICE_HEADERS: dict[str, tuple[str, ...]] = {
    "source_mold_no": ("工模", "工模编号", "模具编号", "模号"),
    "item_no": ("货号", "塑胶货号", "产品编号", "产品编码"),
    "product_name": ("产品名称", "配件名称", "物料名称", "名称"),
    "customer_text": ("客户", "客户名称", "公司名称"),
    "rate_value_raw": ("单价", "单价/啤", "每啤单价", "工价", "价格"),
    "pricing_unit": ("计价单位", "单价单位", "价格单位"),
    "currency": ("币种", "货币"),
    "tax_mode": ("税制", "含税", "税率"),
    "quantity_from": ("起始数量", "数量下限"),
    "quantity_to": ("结束数量", "数量上限"),
    "valid_from": ("生效日期", "开始日期", "有效期起"),
    "valid_to": ("失效日期", "结束日期", "有效期止"),
    "remark": ("备注", "说明"),
    "fallback_machine_class_raw": ("啤机机型", "机型", "安数"),
    "nominal_daily_capacity": ("模具日产量", "日产量", "日啤数"),
    "whole_shot_net_weight_g": ("整啤净重", "净重"),
    "whole_shot_gross_weight_g": ("整啤毛重", "毛重"),
    "cavity_count": ("整啤模腔数", "模腔数", "腔数", "一啤出数"),
    "material_name": ("用料名称", "材料名称"),
    "color_name": ("颜色",),
}

FOOTER_ALIASES = {
    normalize_header(value)
    for value in ("备注", "制表", "操作员", "合计", "汇总", "结束")
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _company_scope_id(db: Session, factory_id: str) -> str:
    from sqlalchemy import select

    from app.models.injection_scheduling_shared import (
        InjectionSchedulingCompanyFactoryMembership,
    )

    scope_id = db.scalar(
        select(InjectionSchedulingCompanyFactoryMembership.company_scope_id).where(
            InjectionSchedulingCompanyFactoryMembership.factory_id == factory_id,
            InjectionSchedulingCompanyFactoryMembership.status == "ACTIVE",
        )
    )
    if not scope_id:
        raise HTTPException(status_code=409, detail="当前厂区没有 ACTIVE 公司归属")
    return str(scope_id)


def _sheet_role(sheet_name: str) -> str:
    normalized = normalize_header(sheet_name)
    for role, aliases in SHEET_ROLE_ALIASES.items():
        if normalized in {normalize_header(item) for item in aliases}:
            return role
    return ""


def _header_catalog(role: str) -> dict[str, tuple[str, ...]]:
    return MOLD_HEADERS if role == "MOLD_DEFINITION_SOURCE" else PRICE_HEADERS


def _header_mapping(
    reader: _WorkbookReader,
    rows: list[tuple[int, dict[str, dict[str, Any]]]],
    role: str,
) -> tuple[int, dict[str, str], list[dict[str, Any]], list[str]]:
    catalog = _header_catalog(role)
    alias_to_fields: dict[str, set[str]] = {}
    for field, aliases in catalog.items():
        for alias in aliases:
            alias_to_fields.setdefault(normalize_header(alias), set()).add(field)

    best: tuple[int, int, dict[str, str], list[dict[str, Any]], list[str]] | None = None
    for row_number, cells in rows[:40]:
        mapping: dict[str, str] = {}
        evidence: list[dict[str, Any]] = []
        ambiguous: list[str] = []
        for column, cell in cells.items():
            displayed = reader.identifier(cell)
            candidates = alias_to_fields.get(normalize_header(displayed), set())
            if len(candidates) == 1:
                field = next(iter(candidates))
                if field in mapping:
                    ambiguous.append(field)
                    continue
                mapping[field] = column
                evidence.append(
                    {
                        "canonical_field": field,
                        "source_header": displayed,
                        "source_column": column,
                        "cell_ref": cell.get("reference", ""),
                        "strategy": "HEADER_ALIAS",
                    }
                )
            elif len(candidates) > 1:
                ambiguous.extend(sorted(candidates))
        score = len(mapping) * 10 - len(set(ambiguous)) * 20
        candidate = (score, row_number, mapping, evidence, sorted(set(ambiguous)))
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        return 0, {}, [], []
    _, row_number, mapping, evidence, ambiguous = best
    return row_number, mapping, evidence, ambiguous


def _raw_cell(reader: _WorkbookReader, cell: dict[str, Any] | None) -> dict[str, Any]:
    if not cell:
        return {"raw_value": "", "displayed_value": "", "cell_ref": ""}
    return {
        "raw_value": _clean_text(cell.get("raw_value")),
        "displayed_value": reader.identifier(cell),
        "cell_ref": cell.get("reference", ""),
        "formula": _clean_text(cell.get("formula")),
    }


def _row_payload(
    reader: _WorkbookReader,
    *,
    cells: dict[str, dict[str, Any]],
    mapping: dict[str, str],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    values: dict[str, str] = {}
    lineage: dict[str, dict[str, Any]] = {}
    for field, column in mapping.items():
        source = _raw_cell(reader, cells.get(column))
        values[field] = source["displayed_value"]
        lineage[field] = source
    return values, lineage


def _row_status(role: str, values: dict[str, str]) -> tuple[str, list[str]]:
    if role == "MOLD_DEFINITION_SOURCE":
        blockers = [
            label
            for field, label in (
                ("source_mold_no", "模具编号"),
                ("standard_name", "模具/产品名称"),
            )
            if not values.get(field, "").strip()
        ]
        return ("PROPOSABLE" if not blockers else "REVIEW_REQUIRED"), blockers
    blockers = [
        label
        for field, label in (
            ("rate_value_raw", "单价"),
            ("source_mold_no", "模具编号"),
        )
        if not values.get(field, "").strip()
    ]
    decisions = [
        label
        for field, label in (
            ("pricing_unit", "计价单位"),
            ("currency", "币种"),
        )
        if not values.get(field, "").strip()
    ]
    if blockers:
        return "REVIEW_REQUIRED", blockers
    # Price facts can be proposed with unresolved business decisions, but activation
    # remains blocked until an approved policy supplies every required dimension.
    return "PROPOSABLE", [f"激活前确认：{item}" for item in decisions]


def parse_master_data_workbook(
    db: Session,
    content: bytes,
    source_file_name: str,
    *,
    factory_id: str,
    profile: ImportProfile,
    auto_detection: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reader = _WorkbookReader(content)
    try:
        if auto_detection and any(
            normalize_header(name) in {"计划表", "排期表", "啤货表", "下单表"}
            for name in reader.sheet_paths
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "MASTER_DATA_PROFILE_NOT_IDENTIFIED",
                    "message": "包含计划/下单 Sheet 的工作簿不会自动猜测为主数据文件",
                },
            )
        recognized = [
            (sheet_name, _sheet_role(sheet_name))
            for sheet_name in reader.sheet_paths
            if _sheet_role(sheet_name)
        ]
        if not recognized:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "MASTER_DATA_PROFILE_NOT_IDENTIFIED",
                    "message": "未识别到机安、模具资料或单价 Sheet",
                },
            )

        issues: list[dict[str, Any]] = []
        rows_out: list[dict[str, Any]] = []
        mapping_out: list[dict[str, Any]] = []
        sheet_roles: list[dict[str, Any]] = []
        company_scope_id = _company_scope_id(db, factory_id)
        for sheet_name, role in recognized:
            rows = list(reader.rows(sheet_name))
            header_row, mapping, evidence, ambiguous = _header_mapping(
                reader, rows, role
            )
            sheet_roles.append(
                {
                    "sheet_name": sheet_name,
                    "role": role,
                    "header_row": header_row,
                    "recognized": bool(header_row and mapping),
                }
            )
            mapping_out.extend(
                {**item, "sheet_name": sheet_name, "header_row": header_row}
                for item in evidence
            )
            required_field = (
                "source_mold_no"
                if role == "MOLD_DEFINITION_SOURCE"
                else "rate_value_raw"
            )
            if not header_row or required_field not in mapping or ambiguous:
                issues.append(
                    _issue(
                        code="MASTER_DATA_MAPPING_REQUIRED",
                        message=f"{sheet_name} 表头无法唯一映射，请提交 Profile 草案",
                        sheet_name=sheet_name,
                        source_row=header_row or None,
                        field_name=required_field,
                        blocking=True,
                    )
                )
                continue
            blank_rows = 0
            for source_row, cells in rows:
                if source_row <= header_row:
                    continue
                values, lineage = _row_payload(reader, cells=cells, mapping=mapping)
                displayed = [
                    value.strip() for value in values.values() if value.strip()
                ]
                if not displayed:
                    blank_rows += 1
                    if blank_rows >= 5:
                        break
                    continue
                blank_rows = 0
                first_value = next(iter(displayed), "")
                if normalize_header(first_value) in FOOTER_ALIASES:
                    break
                status, blockers = _row_status(role, values)
                entity_type = (
                    "MOLD_DEFINITION_BUNDLE"
                    if role == "MOLD_DEFINITION_SOURCE"
                    else "COMMERCIAL_RATE_RULE"
                )
                row = {
                    "row_id": "",
                    "entity_type": entity_type,
                    "proposal_action": "CREATE_OR_REVISE",
                    "resolution_status": status,
                    "activation_blockers": blockers,
                    "canonical": values,
                    "source": {
                        "sheet_name": sheet_name,
                        "source_row": source_row,
                        "source_file_name": source_file_name,
                        "source_file_hash": hashlib.sha256(content).hexdigest(),
                    },
                    "source_lineage": lineage,
                }
                row["row_digest"] = _digest(row)
                rows_out.append(row)
                if status != "PROPOSABLE":
                    issues.append(
                        _issue(
                            code="MASTER_DATA_ROW_REVIEW_REQUIRED",
                            message=f"{sheet_name} 第 {source_row} 行缺少：{', '.join(blockers)}",
                            sheet_name=sheet_name,
                            source_row=source_row,
                            blocking=False,
                        )
                    )

        blocking = sum(1 for item in issues if item.get("blocking"))
        proposable = sum(
            1 for item in rows_out if item["resolution_status"] == "PROPOSABLE"
        )
        master_digest = master_revision_digest(db, company_scope_id)
        normalized: dict[str, Any] = {
            "schema_version": MASTER_SCHEMA_VERSION,
            "parser_version": MASTER_PARSER_VERSION,
            "document_kind": "MASTER_DATA",
            "source_namespace_id": profile.source_namespace_id,
            "source_file_name": source_file_name,
            "source_file_hash": hashlib.sha256(content).hexdigest(),
            "source_size_bytes": len(content),
            "profile": {
                "profile_id": profile.profile_id,
                "profile_code": profile.profile_code,
                "profile_family": profile.profile_family,
                "revision": profile.revision,
                "definition_digest": profile_definition_digest(profile),
                "template_signature": profile_template_signature(profile),
                "header_fingerprint": profile_header_fingerprint(profile),
            },
            "sheet_roles": sheet_roles,
            "mapping": mapping_out,
            "mapping_fingerprint": _digest(mapping_out),
            "master_data_rows": rows_out,
            "master_revision_digest": master_digest,
            "batch_state": "PREVIEW_READY"
            if proposable and not blocking
            else "MAPPING_REQUIRED",
            "summary": {
                "master_row_count": len(rows_out),
                "proposable_count": proposable,
                "review_required_count": len(rows_out) - proposable,
                "issue_count": len(issues),
                "blocking_issue_count": blocking,
            },
        }
        normalized["resolution_digest"] = _digest(
            {
                "master_revision_digest": master_digest,
                "mapping_fingerprint": normalized["mapping_fingerprint"],
                "rows": [item["row_digest"] for item in rows_out],
            }
        )
        normalized["normalized_sha256"] = _digest(normalized)
        return normalized, issues
    finally:
        reader.close()
