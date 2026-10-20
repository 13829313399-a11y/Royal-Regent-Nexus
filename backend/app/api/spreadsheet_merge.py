"""Authenticated request-time spreadsheet utilities; no job or business persistence."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response

from app.core.config import settings
from app.schemas.spreadsheet_merge import MergeRequest
from app.services.auth import AuthContext, can, get_current_user
from app.services.carton_procurement import CARTON_DEPARTMENTS, require_carton_factory
from app.services import spreadsheet_merge as service
from app.services import spreadsheet_merge_templates as catalog


def enabled():
    if not settings.document_tools_enabled:
        service.fail('文档工具暂未启用', 503)


router = APIRouter(prefix='/api/tools/spreadsheet-merge', tags=['spreadsheet-merge'], dependencies=[Depends(enabled)])
User = Annotated[AuthContext, Depends(get_current_user)]


def warehouse_templates_allowed(user: AuthContext, factory_id: str) -> bool:
    # Canonical policy enforces current bindings, factory ceilings and explicit
    # denies in every rollout mode. A role label or flat permission union is not
    # an authorization decision for the selected factory.
    return any(
        all(can(user, f'carton_procurement:{permission}', factory_id, department)
            for permission in ('read', 'inventory_write'))
        for department in CARTON_DEPARTMENTS
    )


def require_template_access(user: AuthContext, factory_id: str | None):
    if not factory_id:
        service.fail('请选择模板所属厂区', 422)
    factory_id = require_carton_factory(factory_id)
    if not warehouse_templates_allowed(user, factory_id):
        service.fail('无当前厂区的仓库模板权限', 403)


def authorize_merge_template(payload: MergeRequest, user: AuthContext):
    if payload.template_id or payload.profile != 'generic':
        require_template_access(user, payload.factory_id)


@router.post('/inspect')
def inspect(user: User, response: Response, file: UploadFile = File(...), preset: Literal['generic', 'carton-packaging-source'] = Form('generic')):
    # Read a bounded payload even when Content-Length is absent or inaccurate.
    try:
        response.headers['Cache-Control'] = 'no-store'
        content = file.file.read(service.MAX_BYTES + 1)
        name = (file.filename or 'spreadsheet.xlsx').replace('\\', '/').rsplit('/', 1)[-1][:255]
        return service.inspect(content, name, preset)
    finally:
        file.file.close()


@router.post('/preview')
def preview(payload: MergeRequest, user: User, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    authorize_merge_template(payload, user)
    return service.merge(payload)


@router.post('/export')
def export(payload: MergeRequest, user: User):
    authorize_merge_template(payload, user)
    content, filename, media_type = service.export(payload)
    return Response(content, media_type=media_type, headers={'Content-Disposition': f'attachment; filename="{filename}"', 'Cache-Control': 'no-store'})


@router.get('/templates')
def templates(factory_id: str, user: User, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    factory_id = require_carton_factory(factory_id)
    return catalog.list_templates() if warehouse_templates_allowed(user, factory_id) else []


@router.get('/templates/{template_id}')
def template(template_id: str, factory_id: str, user: User):
    require_template_access(user, factory_id)
    return Response(catalog.download_template(template_id), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="{template_id}-template.xlsx"', 'Cache-Control': 'no-store'})
