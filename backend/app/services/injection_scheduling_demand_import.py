from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.injection_scheduling_shared import (
    InjectionSchedulingCompanyFactoryMembership,
    InjectionSchedulingFactoryMoldCapability,
    InjectionSchedulingMoldAlias,
    InjectionSchedulingMoldAssetMovement,
    InjectionSchedulingMoldDefinition,
    InjectionSchedulingMoldOutputSpec,
    InjectionSchedulingMoldReservation,
    InjectionSchedulingPhysicalMoldAsset,
)
from app.services.injection_scheduling_canonical import _convert
from app.services.injection_scheduling_excel import (
    _clean_text,
    _issue,
    _WorkbookReader,
)
from app.services.injection_scheduling_profiles import (
    CANONICAL_FIELD_CATALOG,
    ImportProfile,
    normalize_header,
    profile_definition_digest,
    profile_header_fingerprint,
    profile_template_signature,
)

DEMAND_SCHEMA_VERSION = "injection-scheduling-demand-v1"
DEMAND_PARSER_VERSION = "injection-scheduling-demand-parser-v1"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def normalize_identifier(value: Any) -> str:
    """Normalize safe presentation variance without changing business identity."""

    return unicodedata.normalize("NFKC", _clean_text(value)).casefold()


def _column_number(column: str) -> int:
    value = 0
    for character in column:
        value = value * 26 + ord(character) - 64
    return value


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _ordered_cells(
    cells: dict[str, dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    return sorted(cells.items(), key=lambda item: _column_number(item[0]))


def _cell_text(reader: _WorkbookReader, cell: dict[str, Any] | None) -> str:
    return reader.identifier(cell) if cell else ""


def _extract_meta_value(
    reader: _WorkbookReader,
    cells: dict[str, dict[str, Any]],
    aliases: tuple[str, ...],
) -> tuple[str, dict[str, Any] | None]:
    normalized_aliases = {normalize_header(item) for item in aliases}
    ordered = _ordered_cells(cells)
    for index, (_, cell) in enumerate(ordered):
        text = _cell_text(reader, cell)
        normalized = normalize_header(text)
        for alias in normalized_aliases:
            if normalized == alias:
                if index + 1 < len(ordered):
                    return _cell_text(reader, ordered[index + 1][1]), ordered[
                        index + 1
                    ][1]
                return "", None
            for separator in ("：", ":"):
                prefix = next(
                    (
                        raw_alias
                        for raw_alias in aliases
                        if normalize_header(raw_alias) == alias
                        and text.startswith(f"{raw_alias}{separator}")
                    ),
                    None,
                )
                if prefix is not None:
                    return text[len(prefix) + 1 :].strip(), cell
    return "", None


def _convert_meta_date(
    reader: _WorkbookReader,
    value: str,
    cell: dict[str, Any] | None,
) -> str:
    """Convert metadata dates from either adjacent or inline label cells."""

    if cell is None:
        return ""
    text = _clean_text(value)
    normalized_text = (
        text.replace("年", "-")
        .replace("月", "-")
        .removesuffix("日")
        .replace("/", "-")
        .replace(".", "-")
    )
    parts = normalized_text.split("-")
    if len(parts) == 3:
        try:
            return date(*(int(part) for part in parts)).isoformat()
        except (TypeError, ValueError):
            pass
    if _cell_text(reader, cell) == value:
        return str(_convert(reader, cell, "date"))
    return ""


def _header_mapping(
    reader: _WorkbookReader,
    cells: dict[str, dict[str, Any]],
    profile: ImportProfile,
    *,
    sheet_name: str,
    header_row: int,
) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    normalized_columns: dict[str, list[str]] = {}
    for column, cell in cells.items():
        header = normalize_header(_cell_text(reader, cell))
        if header:
            normalized_columns.setdefault(header, []).append(column)

    mapping: list[dict[str, Any]] = []
    columns: dict[str, str] = {}
    blocking: list[str] = []
    claimed_columns: dict[str, str] = {}
    for rule in profile.fields:
        aliases = {normalize_header(item) for item in rule.headers}
        candidates = sorted(
            {
                column
                for alias in aliases
                for column in normalized_columns.get(alias, [])
            },
            key=_column_number,
        )
        method = "HEADER_ALIAS"
        status = "MAPPED"
        confidence = "EXACT"
        if len(candidates) == 1:
            column = candidates[0]
        elif len(candidates) > 1:
            column = ""
            status = "AMBIGUOUS"
            confidence = "NONE"
        else:
            fallback_cell = cells.get(rule.column)
            fallback_header = normalize_header(_cell_text(reader, fallback_cell))
            if fallback_cell and not fallback_header:
                column = rule.column
                method = "PROFILE_FALLBACK_COLUMN"
                confidence = "FALLBACK"
            else:
                column = ""
                status = "MISSING"
                confidence = "NONE"
        if column and column in claimed_columns:
            status = "AMBIGUOUS"
            blocking.extend([rule.canonical_field, claimed_columns[column]])
            column = ""
        elif column:
            claimed_columns[column] = rule.canonical_field
            columns[rule.canonical_field] = column
        if rule.required and status != "MAPPED":
            blocking.append(rule.canonical_field)
        cell = cells.get(column or rule.column)
        mapping.append(
            {
                "rule_id": rule.rule_id,
                "rule_revision": profile.revision,
                "sheet_role": "ORDER_SOURCE",
                "sheet_name": sheet_name,
                "header_row": header_row,
                "column": column or rule.column,
                "fallback_column": rule.column,
                "raw_header": _cell_text(reader, cell),
                "normalized_header": normalize_header(_cell_text(reader, cell)),
                "canonical_field": rule.canonical_field,
                "converter": rule.converter,
                "unit": rule.unit,
                "required": rule.required,
                "status": status,
                "mapping_method": method,
                "confidence": confidence,
                "authority": CANONICAL_FIELD_CATALOG[rule.canonical_field].authority,
                "sample_values": [],
            }
        )
    return mapping, columns, sorted(set(blocking))


def _find_document(
    reader: _WorkbookReader,
    profile: ImportProfile,
) -> tuple[str, int, list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    title_aliases = {normalize_header(item) for item in profile.title_aliases}
    recognized: list[
        tuple[int, str, int, list[dict[str, Any]], dict[str, str], dict[str, Any]]
    ] = []
    for sheet_name in reader.sheet_paths:
        title_seen = False
        scan_rows: list[tuple[int, dict[str, dict[str, Any]]]] = []
        for row_number, cells in reader.rows(sheet_name):
            if row_number > 80:
                break
            scan_rows.append((row_number, cells))
            if any(
                normalize_header(_cell_text(reader, cell)) in title_aliases
                for cell in cells.values()
            ):
                title_seen = True
        for row_number, cells in scan_rows:
            mapping, columns, blocking = _header_mapping(
                reader,
                cells,
                profile,
                sheet_name=sheet_name,
                header_row=row_number,
            )
            meta: dict[str, Any] = {}
            for previous_row, previous_cells in scan_rows:
                if not max(1, row_number - 5) <= previous_row < row_number:
                    continue
                for key, aliases in (
                    ("customer_name", ("公司名称", "客户名称")),
                    ("delivery_due_date", ("交货日期", "交货期")),
                    ("source_document_no", ("单号", "订单号")),
                    ("warehouse_text", ("交货地点", "交货地址", "仓库")),
                ):
                    value, cell = _extract_meta_value(reader, previous_cells, aliases)
                    if value and key not in meta:
                        canonical_value = (
                            _convert_meta_date(reader, value, cell)
                            if key == "delivery_due_date" and cell is not None
                            else value
                        )
                        meta[key] = {
                            "value": canonical_value,
                            "source_row": previous_row,
                            "cell_ref": (cell or {}).get("reference", ""),
                            "raw_value": (cell or {}).get("value"),
                        }
            footer_warehouse_found = False
            for following_row, following_cells in scan_rows:
                if following_row <= row_number:
                    continue
                warehouse_value, warehouse_cell = _extract_meta_value(
                    reader, following_cells, ("下单人",)
                )
                if warehouse_value and not footer_warehouse_found:
                    meta["warehouse_text"] = {
                        "value": warehouse_value,
                        "source_row": following_row,
                        "cell_ref": (warehouse_cell or {}).get("reference", ""),
                        "raw_value": (warehouse_cell or {}).get("value"),
                    }
                    footer_warehouse_found = True
                order_date_value, order_date_cell = _extract_meta_value(
                    reader, following_cells, ("下单日期",)
                )
                if order_date_value and "order_date" not in meta:
                    meta["order_date"] = {
                        "value": _convert_meta_date(
                            reader, order_date_value, order_date_cell
                        ),
                        "source_row": following_row,
                        "cell_ref": (order_date_cell or {}).get("reference", ""),
                        "raw_value": (order_date_cell or {}).get("value"),
                    }
                if footer_warehouse_found and "order_date" in meta:
                    break
            anchors = {
                key
                for key in ("customer_name", "delivery_due_date", "source_document_no")
                if key in meta
            }
            core_matches = {
                "source_mold_no",
                "product_name",
                "order_quantity",
                "product_group_no",
                "required_shots",
            } & set(columns)
            if len(columns) < 4 or len(core_matches) < 2:
                continue
            score = (100 if title_seen else 0) + len(columns) + len(anchors) * 10
            if blocking:
                score -= 20
            if title_seen and len(anchors) == 3:
                recognized.append(
                    (score, sheet_name, row_number, mapping, columns, meta)
                )
    if not recognized:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "DEMAND_ORDER_PROFILE_NOT_IDENTIFIED",
                "message": "未找到标题、三项元数据锚点和需求单表头的确定组合",
            },
        )
    recognized.sort(key=lambda item: (item[0], item[1], -item[2]), reverse=True)
    if len(recognized) > 1 and recognized[0][0] == recognized[1][0]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "DEMAND_ORDER_PROFILE_AMBIGUOUS",
                "message": "多个 Sheet 同时满足需求单指纹，必须人工选择来源 Sheet",
            },
        )
    _, sheet_name, header_row, mapping, columns, meta = recognized[0]
    return sheet_name, header_row, mapping, columns, meta


def _find_document_from_saved_profile(
    reader: _WorkbookReader,
    profile: ImportProfile,
) -> tuple[str, int, list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    recognition = profile.recognition_config
    source_sheet = recognition.get("source_sheet") or {}
    role = profile.primary_source_role
    sheet_name = next((name for name in role.names if name in reader.sheet_paths), "")
    if not sheet_name:
        raise HTTPException(
            status_code=422, detail="已保存模板引用的需求单 Sheet 不存在"
        )
    header_row = int(role.header_row or max(source_sheet.get("header_rows") or [1]))
    field_header_rows = {int(item.header_row or header_row) for item in profile.fields}
    header_cells: dict[str, dict[str, Any]] = {}
    anchor_specs = list(recognition.get("metadata_anchors") or [])
    anchor_refs = {
        str(ref)
        for item in anchor_specs
        for ref in (item.get("label_cell"), item.get("value_cell"))
        if ref
    }
    anchor_cells: dict[str, dict[str, Any]] = {}
    last_needed_row = max(
        [
            *field_header_rows,
            *[int("".join(filter(str.isdigit, ref))) for ref in anchor_refs],
        ]
    )
    for row_number, cells in reader.rows(sheet_name):
        if row_number in field_header_rows:
            for cell in cells.values():
                header_cells[str(cell.get("reference", ""))] = cell
        for cell in cells.values():
            reference = str(cell.get("reference", ""))
            if reference in anchor_refs:
                anchor_cells[reference] = cell
        if row_number > last_needed_row:
            break
    mapping: list[dict[str, Any]] = []
    columns: dict[str, str] = {}
    for rule in profile.fields:
        rule_header_row = int(rule.header_row or header_row)
        cell = header_cells.get(f"{rule.column}{rule_header_row}")
        raw_header = _cell_text(reader, cell)
        matched = normalize_header(raw_header) in {
            normalize_header(item) for item in rule.headers
        }
        if matched:
            columns[rule.canonical_field] = rule.column
        mapping.append(
            {
                "rule_id": rule.rule_id,
                "rule_revision": profile.revision,
                "sheet_role": "ORDER_SOURCE",
                "sheet_name": sheet_name,
                "header_row": rule_header_row,
                "column": rule.column,
                "fallback_column": rule.column,
                "raw_header": raw_header,
                "normalized_header": normalize_header(raw_header),
                "canonical_field": rule.canonical_field,
                "converter": rule.converter,
                "unit": rule.unit,
                "required": rule.required,
                "status": "MAPPED" if matched else "MISSING",
                "mapping_method": "SAVED_STRUCTURAL_HEADER",
                "confidence": "EXACT" if matched else "NONE",
                "authority": CANONICAL_FIELD_CATALOG[rule.canonical_field].authority,
                "sample_values": [],
            }
        )
    meta: dict[str, Any] = {}
    for item in anchor_specs:
        label_ref = str(item.get("label_cell", ""))
        value_ref = str(item.get("value_cell", ""))
        label_cell = anchor_cells.get(label_ref)
        value_cell = anchor_cells.get(value_ref)
        converter = str(item.get("transformer", "text"))
        if label_cell is None or value_cell is None:
            continue
        value = _convert(reader, value_cell, converter)
        if value in (None, ""):
            continue
        meta[str(item.get("canonical_field", ""))] = {
            "value": value,
            "source_row": int("".join(filter(str.isdigit, value_ref))),
            "cell_ref": value_ref,
            "label_cell_ref": label_ref,
            "raw_value": value_cell.get("raw_value"),
            "mapping_method": "SAVED_STRUCTURAL_METADATA_ANCHOR",
        }
    return sheet_name, header_row, mapping, columns, meta


def master_revision_digest(db: Session, company_scope_id: str) -> str:
    definitions = list(
        db.scalars(
            select(InjectionSchedulingMoldDefinition)
            .where(
                InjectionSchedulingMoldDefinition.company_scope_id == company_scope_id
            )
            .order_by(InjectionSchedulingMoldDefinition.id)
        ).all()
    )
    definition_ids = [item.id for item in definitions]
    assets = (
        list(
            db.scalars(
                select(InjectionSchedulingPhysicalMoldAsset)
                .where(
                    InjectionSchedulingPhysicalMoldAsset.mold_definition_id.in_(
                        definition_ids
                    )
                )
                .order_by(InjectionSchedulingPhysicalMoldAsset.id)
            ).all()
        )
        if definition_ids
        else []
    )
    asset_ids = [item.id for item in assets]
    payload: dict[str, list[tuple[Any, ...]]] = {
        "mold_definitions": [
            (item.id, item.revision, item.status, item.valid_from, item.valid_to)
            for item in definitions
        ],
        "assets": [
            (
                item.id,
                item.revision,
                item.status,
                item.current_factory_id,
                item.current_location,
                item.available_from,
            )
            for item in assets
        ],
    }
    scoped_models = (
        (
            "mold_aliases",
            InjectionSchedulingMoldAlias,
            InjectionSchedulingMoldAlias.company_scope_id == company_scope_id,
        ),
    )
    for name, model, scope_filter in scoped_models:
        payload[name] = [
            (str(item.id), int(item.revision), str(item.status))
            for item in db.scalars(
                select(model).where(scope_filter).order_by(model.id)
            ).all()
        ]
    for name, model in (
        ("output_specs", InjectionSchedulingMoldOutputSpec),
        ("capabilities", InjectionSchedulingFactoryMoldCapability),
    ):
        payload[name] = (
            [
                (str(item.id), int(item.revision), str(item.status))
                for item in db.scalars(
                    select(model)
                    .where(model.mold_definition_id.in_(definition_ids))
                    .order_by(model.id)
                ).all()
            ]
            if definition_ids
            else []
        )
    payload["movements"] = (
        [
            (
                item.id,
                item.status,
                item.effective_at,
                item.from_factory_id,
                item.to_factory_id,
            )
            for item in db.scalars(
                select(InjectionSchedulingMoldAssetMovement)
                .where(
                    InjectionSchedulingMoldAssetMovement.physical_asset_id.in_(
                        asset_ids
                    )
                )
                .order_by(InjectionSchedulingMoldAssetMovement.id)
            ).all()
        ]
        if asset_ids
        else []
    )
    payload["reservations"] = (
        [
            (
                item.id,
                item.revision,
                item.status,
                item.window_start,
                item.window_end,
                item.expires_at,
            )
            for item in db.scalars(
                select(InjectionSchedulingMoldReservation)
                .where(
                    InjectionSchedulingMoldReservation.physical_asset_id.in_(asset_ids)
                )
                .order_by(InjectionSchedulingMoldReservation.id)
            ).all()
        ]
        if asset_ids
        else []
    )
    return _digest(payload)


def _company_scope_id(db: Session, factory_id: str) -> str:
    membership = db.scalar(
        select(InjectionSchedulingCompanyFactoryMembership).where(
            InjectionSchedulingCompanyFactoryMembership.factory_id == factory_id,
            InjectionSchedulingCompanyFactoryMembership.status == "ACTIVE",
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "COMPANY_SCOPE_NOT_CONFIGURED",
                "message": "当前厂区尚未加入共享模具公司范围",
            },
        )
    return membership.company_scope_id


def _resolve_row(
    db: Session,
    *,
    factory_id: str,
    company_scope_id: str,
    source_namespace_id: str,
    canonical: dict[str, Any],
    master_digest: str,
) -> dict[str, Any]:
    mold_aliases = list(
        db.scalars(
            select(InjectionSchedulingMoldAlias).where(
                InjectionSchedulingMoldAlias.company_scope_id == company_scope_id,
                InjectionSchedulingMoldAlias.source_namespace_id == source_namespace_id,
                InjectionSchedulingMoldAlias.normalized_alias
                == normalize_identifier(canonical.get("source_mold_no", "")),
                InjectionSchedulingMoldAlias.status == "ACTIVE",
            )
        ).all()
    )
    normalized_mold_no = normalize_identifier(canonical.get("source_mold_no", ""))
    direct_definitions = [
        item
        for item in db.scalars(
            select(InjectionSchedulingMoldDefinition).where(
                InjectionSchedulingMoldDefinition.company_scope_id == company_scope_id,
                InjectionSchedulingMoldDefinition.status == "ACTIVE",
            )
        ).all()
        if normalize_identifier(item.canonical_mold_no) == normalized_mold_no
    ]
    mold_ids = sorted(
        {
            *[item.mold_definition_id for item in mold_aliases],
            *[item.id for item in direct_definitions],
        }
    )
    mold_definition_id = mold_ids[0] if len(mold_ids) == 1 else None
    output_specs: list[InjectionSchedulingMoldOutputSpec] = []
    if mold_definition_id:
        item_keys = {
            normalize_identifier(canonical.get("item_no", "")),
            normalize_identifier(canonical.get("product_group_no", "")),
        } - {""}
        output_specs = list(
            db.scalars(
                select(InjectionSchedulingMoldOutputSpec).where(
                    InjectionSchedulingMoldOutputSpec.mold_definition_id
                    == mold_definition_id,
                    InjectionSchedulingMoldOutputSpec.status == "ACTIVE",
                )
            ).all()
        )
        if item_keys:
            output_specs = [
                item
                for item in output_specs
                if normalize_identifier(item.item_no) in item_keys
            ]
    mold_output_spec_id = output_specs[0].id if len(output_specs) == 1 else None
    assets: list[InjectionSchedulingPhysicalMoldAsset] = []
    capabilities: list[InjectionSchedulingFactoryMoldCapability] = []
    if mold_definition_id:
        assets = list(
            db.scalars(
                select(InjectionSchedulingPhysicalMoldAsset).where(
                    InjectionSchedulingPhysicalMoldAsset.mold_definition_id
                    == mold_definition_id,
                    InjectionSchedulingPhysicalMoldAsset.current_factory_id
                    == factory_id,
                    InjectionSchedulingPhysicalMoldAsset.status == "AVAILABLE",
                )
            ).all()
        )
        capabilities = list(
            db.scalars(
                select(InjectionSchedulingFactoryMoldCapability).where(
                    InjectionSchedulingFactoryMoldCapability.factory_id == factory_id,
                    InjectionSchedulingFactoryMoldCapability.mold_definition_id
                    == mold_definition_id,
                    InjectionSchedulingFactoryMoldCapability.status == "ACTIVE",
                    or_(
                        InjectionSchedulingFactoryMoldCapability.mold_output_spec_id
                        == mold_output_spec_id,
                        InjectionSchedulingFactoryMoldCapability.mold_output_spec_id.is_(
                            None
                        ),
                    ),
                )
            ).all()
        )

    status = "READY"
    reasons: list[str] = []
    if len(mold_ids) > 1 or len(output_specs) > 1:
        reasons.append("mold_match_ambiguous_pending_enrichment")
    elif not mold_definition_id:
        reasons.append("shared_mold_pending_enrichment")
    elif not mold_output_spec_id:
        reasons.append("mold_output_pending_enrichment")
    capability_keys = [(item.applicability_key, item.priority) for item in capabilities]
    capability_conflict = len(capability_keys) != len(set(capability_keys))
    eligible_assets = [
        asset
        for asset in assets
        if any(
            capability.physical_asset_id in {None, asset.id}
            for capability in capabilities
        )
    ]
    readiness = (
        "CAPABILITY_CONFLICT"
        if capability_conflict
        else "FACTORY_READY"
        if eligible_assets
        else "NOT_FACTORY_READY"
    )
    mold_enrichment_status = (
        "AMBIGUOUS"
        if len(mold_ids) > 1 or len(output_specs) > 1
        else "MATCHED"
        if mold_definition_id and mold_output_spec_id
        else "PENDING"
    )
    resolved_values = {
        "customer_identity_id": None,
        "mold_definition_id": mold_definition_id,
        "mold_output_spec_id": mold_output_spec_id,
        "physical_mold_asset_id": eligible_assets[0].id
        if len(eligible_assets) == 1
        else None,
        "factory_capability_id": capabilities[0].id if len(capabilities) == 1 else None,
        "commercial_rate_rule_id": None,
        "frozen_amount": None,
        "frozen_currency": "",
        "frozen_pricing_basis": "",
        "factory_readiness_status": readiness,
        "mold_enrichment_status": mold_enrichment_status,
    }
    provenance = {
        key: {
            "source": "ACTIVE_MASTER_RULE",
            "entity_id": value,
            "master_revision_digest": master_digest,
        }
        for key, value in resolved_values.items()
        if value not in {None, ""}
    }
    candidates = {
        "customer_identity_ids": [],
        "mold_definition_ids": mold_ids,
        "mold_output_spec_ids": [item.id for item in output_specs],
        "physical_mold_asset_ids": [item.id for item in assets],
        "factory_capability_ids": [item.id for item in capabilities],
        "commercial_rate_rule_ids": [],
    }
    resolution_digest = _digest(
        {
            "canonical": canonical,
            "resolved_values": resolved_values,
            "master_revision_digest": master_digest,
            "status": status,
        }
    )
    return {
        "resolution_status": status,
        "resolution_reasons": reasons,
        "resolved_values": resolved_values,
        "provenance": provenance,
        "candidates": candidates,
        "master_revision_digest": master_digest,
        "resolution_digest": resolution_digest,
    }


def parse_demand_order_workbook(
    db: Session,
    content: bytes,
    source_file_name: str,
    *,
    factory_id: str,
    profile: ImportProfile,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_file_hash = hashlib.sha256(content).hexdigest()
    company_scope_id = _company_scope_id(db, factory_id)
    source_namespace_id = f"{profile.source_namespace_id}:{factory_id}"
    reader = _WorkbookReader(content)
    issues: list[dict[str, Any]] = []
    try:
        if profile.recognition_config.get("method") == "MANUAL_CORRECTION":
            sheet_name, header_row, mapping, columns, meta = (
                _find_document_from_saved_profile(reader, profile)
            )
        else:
            sheet_name, header_row, mapping, columns, meta = _find_document(
                reader, profile
            )
        blocking_mapping = [
            item for item in mapping if item["required"] and item["status"] != "MAPPED"
        ]
        if blocking_mapping:
            for item in blocking_mapping:
                issues.append(
                    _issue(
                        code="REQUIRED_MAPPING_MISSING",
                        message=f"必填字段 {item['canonical_field']} 未形成唯一表头映射",
                        sheet_name=sheet_name,
                        source_row=header_row,
                        field_name=item["canonical_field"],
                        cell_ref=f"{item['column']}{header_row}",
                        blocking=True,
                    )
                )

        meta_values = {key: value["value"] for key, value in meta.items()}
        if not meta_values.get("source_document_no"):
            meta_values["source_document_no"] = source_file_name.rsplit(".", 1)[0]
            meta["source_document_no"] = {
                "value": meta_values["source_document_no"],
                "source_row": 0,
                "cell_ref": "",
                "raw_value": None,
                "mapping_method": "FILE_NAME_STEM_FALLBACK",
            }
        rules = {item.canonical_field: item for item in profile.fields}
        mapping_by_field = {item["canonical_field"]: item for item in mapping}
        rows: list[dict[str, Any]] = []
        master_digest = master_revision_digest(db, company_scope_id)
        termination_tokens = {
            normalize_header(item) for item in profile.termination_aliases
        }
        started = False
        empty_identity_streak = 0
        saved_source_sheet = profile.recognition_config.get("source_sheet") or {}
        saved_termination = (profile.recognition_config.get("row_layout") or {}).get(
            "termination"
        ) or {}
        for row_number, cells in reader.rows(sheet_name):
            data_start_row = int(
                saved_source_sheet.get("data_start_row") or header_row + 1
            )
            data_end_row = 1_000_000
            if row_number < data_start_row:
                continue
            if row_number > data_end_row:
                break
            row_tokens = {
                normalize_header(_cell_text(reader, cell)) for cell in cells.values()
            } - {""}
            if saved_termination:
                footer_tokens = {
                    normalize_header(item)
                    for item in saved_termination.get("footer_labels", [])
                }
                if (
                    started
                    and saved_termination.get("mode") == "FIRST_FOOTER_LABEL"
                    and row_tokens & footer_tokens
                ):
                    break
            elif started and (
                "备注" in row_tokens
                or "下单日期" in row_tokens
                or "操作员" in row_tokens
                or bool(
                    row_tokens & termination_tokens
                    and not columns.get("source_mold_no") in cells
                )
            ):
                break
            canonical: dict[str, Any] = {
                "customer_name": meta_values.get("customer_name", ""),
                "source_document_no": meta_values.get("source_document_no", ""),
                "delivery_due_date": meta_values.get("delivery_due_date", ""),
                "warehouse_text": meta_values.get("warehouse_text", ""),
                "order_date": meta_values.get("order_date", ""),
            }
            lineage: dict[str, Any] = {}
            for field_name, column in columns.items():
                rule = rules[field_name]
                cell = cells.get(column)
                converted = _convert(reader, cell, rule.converter)
                if converted not in (None, "") or field_name not in canonical:
                    canonical[field_name] = converted
                lineage[field_name] = {
                    "source_file_hash": source_file_hash,
                    "source_sheet": sheet_name,
                    "source_row": row_number,
                    "source_column": column,
                    "cell_ref": (cell or {}).get("reference", f"{column}{row_number}"),
                    "raw_value": (cell or {}).get("raw_value"),
                    "displayed_value": _cell_text(reader, cell),
                    "profile_id": profile.profile_id,
                    "profile_revision": profile.revision,
                    "parser_version": DEMAND_PARSER_VERSION,
                    "mapping_method": mapping_by_field[field_name]["mapping_method"],
                }
            canonical["item_no"] = canonical.get("product_group_no", "")
            mold_no = str(canonical.get("source_mold_no") or "")
            quantity = Decimal(str(canonical.get("order_quantity") or 0))
            has_product = bool(
                canonical.get("product_group_no") or canonical.get("product_name")
            )
            if not mold_no and quantity == 0 and not has_product:
                if saved_termination.get("mode") == "EMPTY_IDENTITY_STREAK":
                    empty_identity_streak += 1
                    if started and empty_identity_streak >= int(
                        saved_termination.get("empty_identity_streak") or 5
                    ):
                        break
                continue
            empty_identity_streak = 0
            if not mold_no or quantity <= 0 or not has_product:
                issues.append(
                    _issue(
                        code="DEMAND_ROW_INVALID",
                        message="需求行必须有模具编号、正数数量，以及款号或工模名称",
                        sheet_name=sheet_name,
                        source_row=row_number,
                        blocking=False,
                    )
                )
                rows.append(
                    {
                        "source": {"sheet_name": sheet_name, "source_row": row_number},
                        "canonical": canonical,
                        "source_lineage": lineage,
                        "stable_line_key": "",
                        "identity_quality": "INVALID",
                        "resolution_status": "INVALID",
                        "resolution_reasons": ["invalid_order_facts"],
                        "resolved_values": {},
                        "provenance": {},
                        "candidates": {},
                        "master_revision_digest": master_digest,
                        "resolution_digest": _digest(
                            {"canonical": canonical, "status": "INVALID"}
                        ),
                    }
                )
                continue
            started = True
            identity_parts = [
                source_namespace_id,
                str(canonical.get("source_document_no", "")),
                str(canonical.get("item_no", "")),
                mold_no,
                str(canonical.get("product_name", "")),
                str(canonical.get("delivery_due_date", "")),
            ]
            stable_line_key = _digest(
                [normalize_identifier(item) for item in identity_parts]
            )
            resolution = _resolve_row(
                db,
                factory_id=factory_id,
                company_scope_id=company_scope_id,
                source_namespace_id=source_namespace_id,
                canonical=canonical,
                master_digest=master_digest,
            )
            rows.append(
                {
                    "source": {"sheet_name": sheet_name, "source_row": row_number},
                    "canonical": canonical,
                    "source_lineage": lineage,
                    "source_order_line_id": "",
                    "source_revision": source_file_hash,
                    "stable_line_key": stable_line_key,
                    "identity_quality": "FALLBACK_BUSINESS_KEY",
                    **resolution,
                }
            )
    finally:
        reader.close()

    duplicate_keys = {
        key
        for key, count in Counter(
            item["stable_line_key"] for item in rows if item["stable_line_key"]
        ).items()
        if count > 1
    }
    for item in rows:
        if item["stable_line_key"] in duplicate_keys:
            item["resolution_status"] = "IDENTITY_REVIEW_REQUIRED"
            item["resolution_reasons"] = ["fallback_business_key_duplicate"]
            item["resolution_digest"] = _digest(
                {
                    "previous": item["resolution_digest"],
                    "status": "IDENTITY_REVIEW_REQUIRED",
                }
            )

    ready_count = sum(item["resolution_status"] == "READY" for item in rows)
    mapping_fingerprint = _digest(
        [
            (item["canonical_field"], item["column"], item["normalized_header"])
            for item in mapping
        ]
    )
    aggregate_resolution_digest = _digest(
        [(item["stable_line_key"], item["resolution_digest"]) for item in rows]
    )
    blocking_count = sum(bool(item.get("blocking")) for item in issues)
    batch_state = (
        "MAPPING_REQUIRED"
        if blocking_count
        else "PREVIEW_READY"
        if ready_count
        else "RESOLUTION_REVIEW_REQUIRED"
    )
    normalized: dict[str, Any] = {
        "schema_version": DEMAND_SCHEMA_VERSION,
        "parser_version": DEMAND_PARSER_VERSION,
        "document_kind": "DEMAND_ORDER",
        "source_file_name": source_file_name,
        "source_file_hash": source_file_hash,
        "source_size_bytes": len(content),
        "source_namespace_id": source_namespace_id,
        "company_scope_id": company_scope_id,
        "profile": {
            "profile_id": profile.profile_id,
            "profile_code": profile.profile_code,
            "profile_family": profile.profile_family,
            "revision": profile.revision,
            "definition_digest": profile_definition_digest(profile),
            "recognition_method": (
                str(
                    profile.recognition_config.get("method")
                    or "ACTIVE_STRUCTURAL_PROFILE"
                )
                if profile.recognition_config.get("structural_layout_signature")
                else "TITLE_ANCHORS_DYNAMIC_HEADER"
            ),
            "recognition_config": profile.recognition_config,
        },
        "template_signature": str(
            profile.recognition_config.get("structural_layout_signature")
            or profile_template_signature(profile)
        ),
        "header_fingerprint": profile_header_fingerprint(profile),
        "sheet_roles": [
            {
                "role": "ORDER_SOURCE",
                "sheet_name": sheet_name,
                "header_row": header_row,
                "status": "MATCHED",
                "required": True,
            }
        ],
        "mapping": mapping,
        "mapping_fingerprint": mapping_fingerprint,
        "mapping_draft": {},
        "document_meta": meta_values,
        "document_meta_lineage": meta,
        "demand_rows": rows,
        "scheduled_baseline_tasks": [],
        "backlog_orders": [],
        "invalid_rows": [
            item for item in rows if item["resolution_status"] == "INVALID"
        ],
        "master_differences": [],
        "calculation_comparisons": [],
        "reconciliation_actions": [],
        "plan_context": {
            "target_draft_plan_id": "",
            "target_draft_plan_revision": 0,
            "reference_published_plan_id": "",
            "reference_published_plan_revision": 0,
            "reference_published_event_sequence": 0,
            "order_task_revision_digest": "",
            "rule_revision": 0,
            "master_revision_digest": master_digest,
        },
        "action_fingerprint": "",
        "resolution_digest": aggregate_resolution_digest,
        "batch_state": batch_state,
        "summary": {
            "document_kind": "DEMAND_ORDER",
            "row_count": len(rows),
            "ready_count": ready_count,
            "review_required_count": len(rows) - ready_count,
            "invalid_count": sum(
                item["resolution_status"] == "INVALID" for item in rows
            ),
            "issue_count": len(issues),
            "blocking_issue_count": blocking_count,
            "can_confirm": ready_count > 0 and blocking_count == 0,
            "partial_confirmation_supported": True,
        },
    }
    normalized["normalized_sha256"] = _digest(normalized)
    return normalized, issues
