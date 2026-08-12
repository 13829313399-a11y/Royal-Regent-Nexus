from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.molding_sample import MoldingSampleInventoryBatch
from app.models.raw_material import RawMaterial
from app.services.raw_material import RAW_MATERIAL_GLOBAL_FACTORY_ID


@dataclass(frozen=True, slots=True)
class RawMaterialAIMasterRow:
    material_id: str
    material_code: str
    material_name: str
    category: str
    spec: str
    unit: str
    safety_stock_kg: float | None
    status: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class RawMaterialAIMasterPage:
    factory_id: str
    as_of: str
    total: int
    limit: int
    offset: int
    truncated: bool
    items: tuple[RawMaterialAIMasterRow, ...]


@dataclass(frozen=True, slots=True)
class RawMaterialAIInventoryRow:
    batch_id: str
    material_name: str
    batch_no: str
    location: str
    initial_weight_kg: float
    available_weight_kg: float
    updated_at: str


@dataclass(frozen=True, slots=True)
class RawMaterialAIInventoryPage:
    factory_id: str
    as_of: str
    total: int
    limit: int
    offset: int
    truncated: bool
    items: tuple[RawMaterialAIInventoryRow, ...]


def list_raw_material_ai_master_summaries(
    db: Session,
    context_factory_id: str,
    *,
    status: str = "",
    keyword: str = "",
    limit: int = 10,
    offset: int = 0,
) -> RawMaterialAIMasterPage:
    scope = select(
        RawMaterial.id.label("material_id"),
        RawMaterial.material_code.label("material_code"),
        RawMaterial.material_name.label("material_name"),
        RawMaterial.category.label("category"),
        RawMaterial.spec.label("spec"),
        RawMaterial.unit.label("unit"),
        RawMaterial.safety_stock_kg.label("safety_stock_kg"),
        RawMaterial.status.label("status"),
        RawMaterial.updated_at.label("updated_at"),
    ).where(RawMaterial.factory_id == RAW_MATERIAL_GLOBAL_FACTORY_ID)
    if status:
        scope = scope.where(RawMaterial.status == status)
    normalized_keyword = keyword.strip()
    if normalized_keyword:
        scope = scope.where(
            or_(
                RawMaterial.material_code.contains(
                    normalized_keyword,
                    autoescape=True,
                ),
                RawMaterial.material_name.contains(
                    normalized_keyword,
                    autoescape=True,
                ),
                RawMaterial.category.contains(
                    normalized_keyword,
                    autoescape=True,
                ),
                RawMaterial.spec.contains(normalized_keyword, autoescape=True),
            )
        )
    scoped = scope.cte("ai_raw_material_master_scope")
    total = (
        select(func.count().label("total"))
        .select_from(scoped)
        .cte("ai_raw_material_master_total")
    )
    page = (
        select(scoped)
        .order_by(scoped.c.material_code, scoped.c.material_id)
        .limit(limit)
        .offset(offset)
        .cte("ai_raw_material_master_page")
    )
    results = db.execute(
        select(
            total.c.total,
            page.c.material_id,
            page.c.material_code,
            page.c.material_name,
            page.c.category,
            page.c.spec,
            page.c.unit,
            page.c.safety_stock_kg,
            page.c.status,
            page.c.updated_at,
        ).select_from(total.outerjoin(page, true()))
    ).mappings().all()
    total_count = int(results[0]["total"] or 0) if results else 0
    items = tuple(
        RawMaterialAIMasterRow(
            material_id=str(row["material_id"]),
            material_code=str(row["material_code"] or ""),
            material_name=str(row["material_name"] or ""),
            category=str(row["category"] or ""),
            spec=str(row["spec"] or ""),
            unit=str(row["unit"] or ""),
            safety_stock_kg=(
                float(row["safety_stock_kg"])
                if row["safety_stock_kg"] is not None
                else None
            ),
            status=str(row["status"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )
        for row in results
        if row["material_id"] is not None
    )
    return RawMaterialAIMasterPage(
        factory_id=context_factory_id,
        as_of=business_now().isoformat(timespec="seconds"),
        total=total_count,
        limit=limit,
        offset=offset,
        truncated=offset + len(items) < total_count,
        items=items,
    )


def list_raw_material_ai_inventory_summaries(
    db: Session,
    factory_id: str,
    *,
    material: str = "",
    only_available: bool = False,
    limit: int = 10,
    offset: int = 0,
) -> RawMaterialAIInventoryPage:
    scope = select(
        MoldingSampleInventoryBatch.id.label("batch_id"),
        MoldingSampleInventoryBatch.material.label("material_name"),
        MoldingSampleInventoryBatch.batch_no.label("batch_no"),
        MoldingSampleInventoryBatch.location.label("location"),
        MoldingSampleInventoryBatch.initial_weight_kg.label("initial_weight_kg"),
        MoldingSampleInventoryBatch.available_weight_kg.label("available_weight_kg"),
        MoldingSampleInventoryBatch.updated_at.label("updated_at"),
    ).where(MoldingSampleInventoryBatch.factory_id == factory_id)
    normalized_material = material.strip()
    if normalized_material:
        scope = scope.where(
            MoldingSampleInventoryBatch.material.contains(
                normalized_material,
                autoescape=True,
            )
        )
    if only_available:
        scope = scope.where(MoldingSampleInventoryBatch.available_weight_kg > 0)
    scoped = scope.cte("ai_raw_material_inventory_scope")
    total = (
        select(func.count().label("total"))
        .select_from(scoped)
        .cte("ai_raw_material_inventory_total")
    )
    page = (
        select(scoped)
        .order_by(
            scoped.c.material_name,
            scoped.c.batch_no,
            scoped.c.batch_id,
        )
        .limit(limit)
        .offset(offset)
        .cte("ai_raw_material_inventory_page")
    )
    results = db.execute(
        select(
            total.c.total,
            page.c.batch_id,
            page.c.material_name,
            page.c.batch_no,
            page.c.location,
            page.c.initial_weight_kg,
            page.c.available_weight_kg,
            page.c.updated_at,
        ).select_from(total.outerjoin(page, true()))
    ).mappings().all()
    total_count = int(results[0]["total"] or 0) if results else 0
    items = tuple(
        RawMaterialAIInventoryRow(
            batch_id=str(row["batch_id"]),
            material_name=str(row["material_name"] or ""),
            batch_no=str(row["batch_no"] or ""),
            location=str(row["location"] or ""),
            initial_weight_kg=float(row["initial_weight_kg"] or 0),
            available_weight_kg=float(row["available_weight_kg"] or 0),
            updated_at=str(row["updated_at"] or ""),
        )
        for row in results
        if row["batch_id"] is not None
    )
    return RawMaterialAIInventoryPage(
        factory_id=factory_id,
        as_of=business_now().isoformat(timespec="seconds"),
        total=total_count,
        limit=limit,
        offset=offset,
        truncated=offset + len(items) < total_count,
        items=items,
    )
