from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.raw_material import RawMaterial
from app.schemas.raw_material import (
    RawMaterialCreateRequest,
    RawMaterialFactoryId,
    RawMaterialOut,
    RawMaterialUpdateRequest,
)
from app.services.auth import AuthContext, get_current_user
from app.services.business_authz import ENGINEERING_DEPARTMENTS, WAREHOUSE_DEPARTMENTS, ensure_permission_for_departments
from app.services.molding_sample import ensure_molding_local_write, ensure_molding_read
from app.services.raw_material import (
    RAW_MATERIAL_GLOBAL_FACTORY_ID,
    create_raw_material,
    list_raw_materials,
    update_raw_material,
)


router = APIRouter(prefix="/api/raw-materials")


def ensure_raw_material_access(db: Session, current_user: AuthContext, factory_id: str) -> None:
    ensure_molding_local_write(db, current_user, factory_id)
    ensure_permission_for_departments(
        db,
        current_user,
        "molding_sample:raw_material_write",
        factory_id,
        (*ENGINEERING_DEPARTMENTS, *WAREHOUSE_DEPARTMENTS),
    )


def ensure_raw_material_read_access(db: Session, current_user: AuthContext, factory_id: str) -> None:
    ensure_molding_read(db, current_user, factory_id)


@router.get("", response_model=list[RawMaterialOut])
def get_raw_materials(
    factory_id: RawMaterialFactoryId,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_raw_material_read_access(db, current_user, factory_id)
    return list_raw_materials(db)


@router.post("", response_model=RawMaterialOut, status_code=status.HTTP_201_CREATED)
def post_raw_material(
    payload: RawMaterialCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_raw_material_access(db, current_user, payload.factory_id)
    return create_raw_material(db, payload, current_user)


@router.patch("/{material_id}", response_model=RawMaterialOut)
def patch_raw_material(
    material_id: str,
    payload: RawMaterialUpdateRequest,
    factory_id: RawMaterialFactoryId,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_raw_material_access(db, current_user, factory_id)
    material = db.get(RawMaterial, material_id)
    if material is None or material.factory_id != RAW_MATERIAL_GLOBAL_FACTORY_ID:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="原料不存在或已被删除")
    return update_raw_material(db, material_id, payload, current_user, factory_id)
