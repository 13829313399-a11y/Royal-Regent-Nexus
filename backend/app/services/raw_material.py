import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.molding_sample import MoldingSampleMaterialPrice
from app.models.raw_material import RawMaterial
from app.schemas.raw_material import RawMaterialCreateRequest, RawMaterialOut, RawMaterialUpdateRequest
from app.services.auth import AuthContext, add_auth_audit


RAW_MATERIAL_BASELINE_PATH = Path(__file__).resolve().parents[1] / "data" / "raw_material_baseline.json"
RAW_MATERIAL_BASELINE_FACTORY_IDS = ("huakang-a", "huakang-b", "huadeng", "huaxing")


def load_raw_material_baseline() -> list[dict[str, object]]:
    try:
        rows = json.loads(RAW_MATERIAL_BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("原料基准资料读取失败") from error

    if not isinstance(rows, list):
        raise RuntimeError("原料基准资料格式无效")

    return [row for row in rows if isinstance(row, dict)]


def baseline_material_name(row: dict[str, object]) -> str:
    return str(row.get("materialName") or row.get("commodityName") or "").strip()


def baseline_blend_description(row: dict[str, object]) -> str:
    parts: list[str] = []
    for index in range(1, 4):
        material_name = str(row.get(f"blendMaterialName{index:02d}") or "").strip()
        if not material_name:
            continue
        ratio = row.get(f"blendRatio{index:02d}")
        if isinstance(ratio, (int, float)):
            percentage = ratio if ratio > 1 else ratio * 100
            parts.append(f"{material_name} {percentage:g}%")
        else:
            parts.append(material_name)
    return f"混料：{' / '.join(parts)}" if parts else ""


def seed_raw_material_defaults(db: Session) -> int:
    """Seed the prior browser-only baseline into each supported factory idempotently."""
    baseline_rows = load_raw_material_baseline()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created_count = 0

    for factory_id in RAW_MATERIAL_BASELINE_FACTORY_IDS:
        existing_codes = set(db.scalars(
            select(RawMaterial.material_code).where(RawMaterial.factory_id == factory_id)
        ).all())
        for row in baseline_rows:
            material_code = str(row.get("materialCode") or "").strip()
            if not material_code or material_code in existing_codes:
                continue

            material_name = baseline_material_name(row)
            blend_description = baseline_blend_description(row)
            category = str(row.get("plasticCategory") or "").strip()
            spec = str(row.get("commodityName") or blend_description or row.get("remarks") or "").strip()
            notes = str(row.get("remarks") or blend_description or "").strip()
            db.add(
                RawMaterial(
                    id=f"RM-BASELINE-{factory_id}-{material_code}",
                    factory_id=factory_id,
                    material_code=material_code,
                    material_name=material_name,
                    category=category,
                    spec=spec,
                    unit=str(row.get("unit") or "KG/包").strip() or "KG/包",
                    supplier=str(row.get("origin") or "").strip(),
                    safety_stock_kg=None,
                    status="启用" if material_name else "停用",
                    notes=notes,
                    created_by="system-baseline",
                    created_at=now,
                    updated_at=now,
                )
            )
            existing_codes.add(material_code)
            created_count += 1

    if created_count:
        db.commit()
    return created_count


def to_raw_material_out(material: RawMaterial, unit_price_hkd_per_lb: float | None = None) -> RawMaterialOut:
    return RawMaterialOut.model_validate(material).model_copy(
        update={"unit_price_hkd_per_lb": unit_price_hkd_per_lb},
    )


def list_raw_materials(db: Session, factory_id: str) -> list[RawMaterialOut]:
    statement = (
        select(RawMaterial, MoldingSampleMaterialPrice.unit_price)
        .outerjoin(
            MoldingSampleMaterialPrice,
            MoldingSampleMaterialPrice.material == RawMaterial.material_name,
        )
        .where(RawMaterial.factory_id == factory_id)
        .order_by(RawMaterial.material_code, RawMaterial.created_at)
    )
    return [
        to_raw_material_out(material, unit_price)
        for material, unit_price in db.execute(statement).all()
    ]


def upsert_material_price(
    db: Session,
    material_name: str,
    unit_price_hkd_per_lb: float | None,
) -> float | None:
    if unit_price_hkd_per_lb is None:
        existing = db.scalar(
            select(MoldingSampleMaterialPrice).where(
                MoldingSampleMaterialPrice.material == material_name,
            ),
        )
        return existing.unit_price if existing else None

    price = db.scalar(
        select(MoldingSampleMaterialPrice).where(
            MoldingSampleMaterialPrice.material == material_name,
        ),
    )
    if price is None:
        price = MoldingSampleMaterialPrice(
            material=material_name,
            unit_price=unit_price_hkd_per_lb,
            notes="工程部通过原料主数据维护",
        )
        db.add(price)
    else:
        price.unit_price = unit_price_hkd_per_lb
    return unit_price_hkd_per_lb


def create_raw_material(
    db: Session,
    payload: RawMaterialCreateRequest,
    current_user: AuthContext,
) -> RawMaterialOut:
    existing = db.scalar(
        select(RawMaterial.id).where(
            RawMaterial.factory_id == payload.factory_id,
            RawMaterial.material_code == payload.material_code,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="当前厂区已存在相同物料编号")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    material = RawMaterial(
        id=f"RM-{uuid4().hex[:12].upper()}",
        factory_id=payload.factory_id,
        material_code=payload.material_code,
        material_name=payload.material_name,
        category=payload.category,
        spec=payload.spec,
        unit=payload.unit,
        supplier=payload.supplier,
        safety_stock_kg=payload.safety_stock_kg,
        status=payload.status,
        notes=payload.notes,
        created_by=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(material)
    unit_price_hkd_per_lb = upsert_material_price(
        db,
        material.material_name,
        payload.unit_price_hkd_per_lb,
    )
    add_auth_audit(
        db,
        "raw_material_created",
        username=current_user.username,
        user_id=current_user.id,
        detail=(
            f"厂区={material.factory_id};物料编号={material.material_code};原料={material.material_name};"
            f"单价(HKD/磅)={unit_price_hkd_per_lb if unit_price_hkd_per_lb is not None else '未维护'}"
        ),
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="当前厂区已存在相同物料编号") from None
    db.refresh(material)
    return to_raw_material_out(material, unit_price_hkd_per_lb)


def update_raw_material(
    db: Session,
    material_id: str,
    payload: RawMaterialUpdateRequest,
    current_user: AuthContext,
) -> RawMaterialOut:
    material = db.get(RawMaterial, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="原料不存在或已被删除")

    previous_name = material.material_name
    material.material_name = payload.material_name
    material.category = payload.category
    material.spec = payload.spec
    material.unit = payload.unit
    material.supplier = payload.supplier
    material.safety_stock_kg = payload.safety_stock_kg
    material.status = payload.status
    material.notes = payload.notes
    material.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    unit_price_hkd_per_lb = upsert_material_price(
        db,
        material.material_name,
        payload.unit_price_hkd_per_lb,
    )
    add_auth_audit(
        db,
        "raw_material_updated",
        username=current_user.username,
        user_id=current_user.id,
        detail=(
            f"厂区={material.factory_id};物料编号={material.material_code};"
            f"原料={previous_name}→{material.material_name};"
            f"单价(HKD/磅)={unit_price_hkd_per_lb if unit_price_hkd_per_lb is not None else '未维护'}"
        ),
    )
    db.commit()
    db.refresh(material)
    return to_raw_material_out(material, unit_price_hkd_per_lb)
