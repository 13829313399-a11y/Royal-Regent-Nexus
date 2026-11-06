from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db import get_db
from app.services.auth import get_current_user
from app.services import material_plan as service
from app.schemas.material_plan import TrialRequest
from app.schemas.material_plan import DatesRequest
from app.schemas.engineering_bom import Command
from app.services import material_plan_workflow as workflow

router = APIRouter(prefix='/api/material-planning', tags=['material-planning'])


def enabled():
    return settings.material_plan_enabled and settings.engineering_bom_enabled


def check(db, user, factory, action='read'):
    service.authorize(user, factory, action)
    service.bom.require(enabled(), '需求试算尚未启用', 503)
    service.bom.require(service.ready(db), '需求试算数据结构尚未部署，请管理员备份并执行迁移', 503)


@router.get('/access')
def access(factory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    service.authorize(user, factory_id)
    return dict(enabled=enabled(), schema_ready=service.ready(db), can_write=service.allowed(user, 'draft_write'),
        can_submit=service.allowed(user, 'submit'), can_self_review=service.allowed(user, 'self_review'),
        can_read_orders=service.orders.allowed(user), order_schema_ready=service.orders.ready(db))


@router.get('/orders')
def orders(factory_id: str, q: str = Query('', max_length=255), db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id)
    return service.orders.search(db, user, q)


@router.get('/workspace')
def workspace(factory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id)
    return service.workspace(db, user)


@router.get('/drafts/{identity}/history')
def history(identity: str, factory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id)
    return dict(items=service.history(db, user, identity))


@router.post('/preview')
def preview(body: TrialRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id)
    return service.preview(db, user, body)


@router.post('/drafts')
def create(body: TrialRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'draft_write')
    return service.save(db, user, body)


@router.post('/drafts/{identity}')
def update(identity: str, body: TrialRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'draft_write')
    return service.save(db, user, body, identity)


@router.get('/procurement/access')
def procurement_access(factory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    service.authorize(user, factory_id, 'dates_read')
    return dict(enabled=enabled(), schema_ready=service.ready(db), can_write=service.allowed(user, 'dates_write'))


@router.get('/procurement/workspace')
def procurement_workspace(factory_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, factory_id, 'dates_read')
    return workflow.queue(db)


@router.post('/drafts/{identity}/dates')
def dates(identity: str, body: DatesRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'dates_write')
    return workflow.apply(db, user, identity, 'dates', body)


@router.post('/drafts/{identity}/submit')
def submit(identity: str, body: Command, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'submit')
    return workflow.apply(db, user, identity, 'submit', body)


@router.post('/drafts/{identity}/self-review')
def self_review(identity: str, body: Command, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'self_review')
    return workflow.apply(db, user, identity, 'self-review', body)


@router.post('/drafts/{identity}/reopen')
def reopen(identity: str, body: Command, db: Session = Depends(get_db), user=Depends(get_current_user)):
    check(db, user, body.factory_id, 'submit')
    return workflow.apply(db, user, identity, 'reopen', body)
