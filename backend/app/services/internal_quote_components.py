"""Product-scoped JustPlay identities shared by imports and image attachments."""
import json
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select

from app.models.internal_quote import InternalQuoteSection

COMPONENT_IMAGE_PREFIX = "component-image:"


def quote_components(db, quote) -> list[dict]:
    if quote.factory_id != "huakang-b" or "".join(c for c in quote.customer.lower() if c.isalnum()) != "justplay":
        return []
    section = db.scalar(select(InternalQuoteSection).where(
        InternalQuoteSection.quote_id == quote.id, InternalQuoteSection.department == "sales",
    ))
    payload = json.loads(section.payload_json or "{}") if section else {}
    return payload.get("pricing_components", []) if payload.get("pricing_mode") == "component" else []


def component_image_department(component_id: str) -> str:
    department = COMPONENT_IMAGE_PREFIX + component_id
    if not component_id or len(department) > 64:
        raise HTTPException(400, "分项标识无效")
    return department


def import_assignment_rows(import_type: str, fragment: dict) -> list[dict]:
    field = {"mold": "molds", "painting": "rows"}.get(import_type)
    if not field:
        return []
    return [
        {"key": f"{field}:{index}", "label": str(row.get("item") or row.get("name") or row.get("chinese_name") or row.get("part_name") or row.get("mold_no") or f"明细 {index + 1}"),
         "source_row": row.get("source_row", ""), "mold_no": row.get("mold_no", "")}
        for index, row in enumerate(fragment.get(field, [])) if isinstance(row, dict)
    ]


def apply_import_assignments(import_type: str, fragment: dict, assignments: dict[str, str], components: list[dict]) -> dict:
    rows = import_assignment_rows(import_type, fragment)
    expected = {row["key"] for row in rows}
    valid_ids = {str(c["id"]) for c in components}
    if set(assignments) != expected:
        raise HTTPException(400, "请给每条映射明细选择应用分项或不采用")
    if any(value != "__skip__" and value not in valid_ids for value in assignments.values()):
        raise HTTPException(400, "映射分项不属于当前产品，请重新选择")
    result = deepcopy(fragment)
    field = "molds" if import_type == "mold" else "rows"
    selected = []
    for index, row in enumerate(result.get(field, [])):
        component_id = assignments[f"{field}:{index}"]
        if component_id != "__skip__":
            row["pricing_component_id"] = component_id
            selected.append(row)
    if not selected:
        raise HTTPException(400, "至少选择一条需要采用的映射明细")
    result[field] = selected
    return result
