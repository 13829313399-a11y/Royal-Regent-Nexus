from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db import get_db
from app.models.cutting_ops import CuttingMaster, CuttingRevision
from app.services.auth import AuthContext, get_current_user
from app.services import cutting_ops as c, cutting_schemas as s
from app.services.permission_codes import CUTTING_OPS_PERMISSION_CODES


class CuttingRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request: Request):
            # Reject repeated scope parameters rather than picking the last one.
            if len(request.query_params.getlist('factory_id')) > 1:
                return JSONResponse({'detail': '厂区参数不能重复'}, status_code=422)
            try:
                return await original(request)
            except ValidationError as error:
                return JSONResponse({'detail': [{'loc': list(e['loc']), 'msg': e['msg']} for e in error.errors()]}, status_code=422)
        return handler


router = APIRouter(prefix='/api/cutting-operations', tags=['cutting-operations'], route_class=CuttingRoute)
Db = Annotated[Session, Depends(get_db)]
User = Annotated[AuthContext, Depends(get_current_user)]


def ready(db):
    c.require(settings.cutting_ops_enabled, '裁床基础资料尚未启用', 503)
    c.require(c.schema_ready(db.connection()), '裁床基础资料需先完成显式数据库迁移', 503)


@router.get('/access')
def access(db: Db, user: User, factory_id: str = ''):
    c.authorize(user, factory_id)
    enabled = settings.cutting_ops_enabled
    migrated = c.schema_ready(db.connection()) if enabled else False
    return dict(enabled=enabled, schema_ready=migrated, permissions=[code.split(':')[1] for code in
                CUTTING_OPS_PERMISSION_CODES if c.allowed(user, code.split(':')[1])])


@router.get('/masters')
def masters(db: Db, user: User, factory_id: str = '', kind: s.Kind = 'material',
            page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), q: str = Query('', max_length=80)):
    c.authorize(user, factory_id)
    ready(db)
    query = select(CuttingMaster).where(CuttingMaster.factory_id == factory_id, CuttingMaster.kind == kind)
    if q.strip():
        query = query.where(CuttingMaster.code.contains(q.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(CuttingMaster.code).offset((page-1)*page_size).limit(page_size))
    return dict(data=[c.view(db, item) for item in rows], total=total, page=page, page_size=page_size)


@router.get('/masters/{entity_id}/versions')
def versions(entity_id: str, db: Db, user: User, factory_id: str = '', page: int = Query(1, ge=1)):
    c.authorize(user, factory_id)
    ready(db)
    item = c.master(db, entity_id)
    numbers = db.scalars(select(CuttingRevision.version).where(CuttingRevision.master_id == item.id)
                         .order_by(CuttingRevision.version.desc()).offset((page-1)*50).limit(50))
    return dict(data=[c.view(db, item, version) for version in numbers], total=item.version, page=page, page_size=50)


@router.post('/masters')
def create(body: s.Save, db: Db, user: User):
    c.authorize(user, body.factory_id, 'bom_write' if body.kind == 'bom' else 'master_write')
    ready(db)
    return c.command(db, user, body, 'create', lambda: c.save(db, user, body))


@router.put('/masters/{entity_id}')
def update(entity_id: str, body: s.Save, db: Db, user: User):
    c.authorize(user, body.factory_id, 'bom_write' if body.kind == 'bom' else 'master_write')
    ready(db)
    return c.command(db, user, body, 'update:' + entity_id, lambda: c.save(db, user, body, entity_id))


@router.post('/masters/{entity_id}/state')
def change_state(entity_id: str, body: s.StateChange, db: Db, user: User):
    c.authorize(user, body.factory_id, 'bom_publish' if body.status == 'published' else 'master_write')
    ready(db)
    return c.command(db, user, body, 'state:' + entity_id, lambda: c.state(db, user, body, entity_id))
