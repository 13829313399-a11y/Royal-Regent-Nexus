from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db import get_db
from app.schemas.engineering_bom import Command
from app.schemas.material_purchase import SavePurchase, ChangePurchase, ReplacementPurchase
from app.services.auth import get_current_user
from app.services import material_purchase as service
from app.services import material_purchase_checks as checks

router = APIRouter(prefix='/api/material-purchasing', tags=['material-purchasing'])


def enabled():
    return settings.material_purchase_enabled and settings.material_plan_enabled and settings.engineering_bom_enabled


def check(db, user, factory, action='read'):
    service.authorize(user, factory, action)
    service.trial.bom.require(enabled(), '采购准备流程尚未启用', 503)
    service.trial.bom.require(service.ready(db), '采购准备结构尚未部署，请管理员备份并执行迁移', 503)


@router.get('/access')
def access(factory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    service.authorize(user, factory_id)
    return dict(enabled=enabled(), schema_ready=service.ready(db), can_write=service.allowed(user, 'write'),
        can_approve=service.allowed(user, 'approve'), can_release=False)


@router.get('/workspace')
def workspace(factory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id)
    return service.workspace(db)


@router.get('/documents/{identity}/history')
def history(identity: str, factory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id)
    return dict(items=service.history(db, identity))


@router.get('/documents/{identity}/checks')
def preparation_checks(identity: str, factory_id: str, expected_version: int = Query(..., ge=1),
                       db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id)
    return checks.read(db, identity, expected_version)


@router.post('/documents')
def create(body: SavePurchase, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'write')
    return service.command(db, user, body, 'save')


@router.post('/documents/{identity}')
def save(identity: str, body: SavePurchase, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'write')
    return service.command(db, user, body, 'save', identity)


@router.post('/documents/{identity}/change')
def change(identity: str, body: ChangePurchase, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'write')
    return service.command(db, user, body, 'change', identity)


@router.post('/documents/{identity}/replacement')
def replacement(identity: str, body: ReplacementPurchase, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'write')
    return service.command(db, user, body, 'replacement', identity)


@router.post('/documents/{identity}/actions/{action}')
def action(identity: str, action: Literal['submit', 'approve', 'reject', 'approve-change', 'reject-change', 'release'],
           body: Command, db: Session = Depends(get_db), user=Depends(get_current_user)):
    permission = 'release' if action == 'release' else 'write' if action == 'submit' else 'approve'
    check(db, user, body.factory_id, permission)
    return service.command(db, user, body, action, identity)
