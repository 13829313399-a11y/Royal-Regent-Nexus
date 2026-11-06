from fastapi import APIRouter, Depends, File, Form, UploadFile, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db import get_db
from app.services.auth import get_current_user
from app.services import engineering_bom as service
from app.services import engineering_bom_comparison as comparison
from app.services import engineering_bom_checks as checks
from app.services import engineering_material_usage as material_usage
from app.services.engineering_bom_import import preview, LIMIT
from app.schemas.engineering_bom import Command, Material, SaveBom

router = APIRouter(prefix='/api/engineering-bom', tags=['engineering-bom'])


def check(db, user, factory, action='read'):
    service.authorize(user, factory, action)
    service.require(settings.engineering_bom_enabled, '工程 BOM 基础功能尚未启用', 503)
    service.ensure(db)


@router.get('/access')
def access(factory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    service.authorize(user, factory_id)
    return dict(enabled=settings.engineering_bom_enabled, schema_ready=service.ready(db),
                permissions=[a for a in service.ACTIONS if service.allowed(user, a)])


@router.get('/workspace')
def workspace(factory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id)
    docs = db.scalars(select(service.EngineeringBom).where(service.EngineeringBom.factory_id == service.FACTORY))
    return dict(materials=service.materials(db), boms=[service.view(db, r) | {'effective_version': r.effective_version} for r in docs])


@router.get('/history/{identity}')
def history(identity: str, factory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id)
    return dict(items=service.versions(db, identity))


@router.post('/materials')
def save_material(body: Material, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'material_write')
    return service.save_material(db, user, body)


@router.get('/boms/{identity}/comparison')
def compare_versions(identity: str, factory_id: str, from_version: int = Query(..., ge=1), to_version: int = Query(..., ge=1),
                     db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id)
    return comparison.read(db, identity, from_version, to_version)


@router.get('/boms/{identity}/approval-check')
def approval_check(identity: str, factory_id: str, expected_version: int = Query(..., ge=1),
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id)
    return checks.read(db, identity, expected_version)


@router.post('/materials/{identity}/{action}')
def material_state(identity: str, action: str, body: Command, db: Session = Depends(get_db), user=Depends(get_current_user)):
    service.require(action in ('approve', 'deactivate'), '未知操作', 422)
    check(db, user, body.factory_id, 'material_approve' if action == 'approve' else 'material_write')
    return service.material_state(db, user, body, identity, action == 'approve')


@router.get('/materials/{identity}/bom-usage')
def material_bom_usage(identity: str, factory_id: str, expected_version: int = Query(..., ge=1),
                       db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id)
    return material_usage.read(db, identity, expected_version)


@router.post('/boms')
def create(body: SaveBom, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'bom_write')
    return service.save_bom(db, user, body)


@router.post('/boms/{identity}')
def save(identity: str, body: SaveBom, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'bom_write')
    return service.save_bom(db, user, body, identity)


@router.post('/boms/{identity}/approve')
def approve(identity: str, body: Command, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'bom_approve')
    return service.approve_bom(db, user, body, identity)


@router.post('/preview')
def calculate(body: SaveBom, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id)
    return dict(items=service.expansion(body.data.model_dump(mode='json')))


@router.post('/import-preview')
async def import_preview(factory_id: str = Form(...), file: UploadFile = File(...),
                         db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id, 'import')
    return preview(db, await file.read(LIMIT + 1), file.filename or '')
