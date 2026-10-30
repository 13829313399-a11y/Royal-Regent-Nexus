from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import carton_materials as schema
from app.services import carton_materials as service
from app.services import carton_material_references as references
from app.services.auth import AuthContext, get_current_user
from app.services.customer_order_jobs import run_order_job, order_job_request

def retired_writes(request: Request):
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        raise HTTPException(410, '订单指令资料流程已停用，请使用箱唛资料库；原资料仍可查阅')


router = APIRouter(prefix='/api/carton-materials', tags=['carton-materials'], dependencies=[Depends(order_job_request), Depends(retired_writes)])


@router.get('')
def listing(factory_id: str, audience: schema.Audience, q: str = Query('', max_length=255), todo: bool = False,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.list_folders(db, user, factory_id, audience, q, todo)


@router.get('/capabilities')
def capabilities(factory_id: str, audience: schema.Audience,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.capabilities(db,user,factory_id,audience)


@router.get('/contracts')
def contracts(factory_id: str, audience: schema.Audience,q: str = Query('',max_length=255),
    limit: int = Query(50,ge=1,le=100),offset: int = Query(0,ge=0),
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.contract_listing(db,user,factory_id,audience,q,limit,offset)


@router.post('/references')
def associate(body: schema.ReferenceCreate,request: Request,factory_id: str,audience: schema.Audience,
    db: Session = Depends(get_db),user: AuthContext = Depends(get_current_user)):
    try: return references.associate(db,user,factory_id,audience,body,lambda:get_current_user(request,db))
    except BaseException:
        db.rollback(); raise


@router.post('/batch-approvals')
def batch_approval(body: schema.BatchApproval,request: Request,factory_id: str,audience: schema.Audience,
    db: Session = Depends(get_db),user: AuthContext = Depends(get_current_user)):
    from app.services.carton_materials_batch import approve
    return approve(db,user,factory_id,audience,body,lambda:get_current_user(request,db))


@router.get('/references')
def reverse_references(source_context_id: str,factory_id: str,audience: schema.Audience,
    version_id: str = '',limit: int = Query(50,ge=1,le=100),offset: int = Query(0,ge=0),
    db: Session = Depends(get_db),user: AuthContext = Depends(get_current_user)):
    return references.reverse(db,user,factory_id,audience,source_context_id,version_id,limit,offset)


@router.get('/contracts/{identifier}')
def contract_detail(identifier: str,factory_id: str,audience: schema.Audience,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.contract_detail(db,user,factory_id,audience,identifier)


@router.post('/contracts/{identifier}/mappings')
def mapping(identifier: str,body: schema.Mapping,request: Request,factory_id: str,audience: schema.Audience,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    try: return service.map_legacy(db,user,factory_id,audience,identifier,body,lambda:get_current_user(request,db))
    except BaseException:
        db.rollback(); raise


@router.get('/options')
def options(factory_id: str, audience: schema.Audience, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    service.authorize(db, user, factory_id, audience)
    return dict(suppliers=service.suppliers(db, factory_id) if audience != 'supplier' else [],
                capabilities=service.capabilities(db,user,factory_id,audience))


@router.get('/candidates')
def candidates(factory_id: str, audience: schema.Audience, q: str = Query('', max_length=255),
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.candidates(db, user, factory_id, audience, q)


@router.post('/statuses')
def statuses(body: schema.Statuses, factory_id: str, audience: schema.Audience,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.statuses(db,user,factory_id,audience,body.targets)


@router.post('')
@router.post('/contracts')
def create(body: schema.Create, request: Request, factory_id: str, audience: schema.Audience,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    try: return service.create(db, user, factory_id, audience, body, lambda: get_current_user(request, db))
    except BaseException:
        db.rollback(); raise


@router.get('/{identifier}')
def detail(identifier: str, factory_id: str, audience: schema.Audience,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.detail(db, user, factory_id, audience, identifier)


@router.post('/{identifier}/actions')
def action(identifier: str, body: schema.Command, request: Request, factory_id: str, audience: schema.Audience,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    try: return service.change(db, user, factory_id, audience, identifier, body, lambda: get_current_user(request, db))
    except BaseException:
        db.rollback(); raise


@router.post('/{identifier}/versions')
async def version(identifier: str, request: Request, factory_id: str, audience: schema.Audience,
    metadata: str = Form(...), file: UploadFile | None = File(None),
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    try: body = schema.Version.model_validate_json(metadata)
    except ValidationError as error: raise HTTPException(422, '资料版本参数不正确') from error
    initial = service.resolve_entry(db,user,factory_id,audience,identifier,authority_id=body.authority_id,write=True)
    if not initial['state']: raise HTTPException(422,'请先选择具体订单资料后上传')
    prepared = None
    if file:
        content = await file.read(20 * 1024 * 1024 + 1)
        if not content or len(content) > 20 * 1024 * 1024: raise HTTPException(422, '文件不能为空，单个不超过20MB')
        prepared = await run_order_job(service.prepare_file, file.filename or '', content, db=db)
    try: return service.change(db, user, factory_id, audience, identifier, body, lambda: get_current_user(request, db), prepared)
    except BaseException:
        db.rollback(); raise


@router.post('/{identifier}/versions-and-references')
async def upload_and_associate(identifier: str,request: Request,factory_id: str,audience: schema.Audience,
    metadata: str = Form(...),file: UploadFile | None = File(None),
    db: Session = Depends(get_db),user: AuthContext = Depends(get_current_user)):
    try: body=schema.SharedUpload.model_validate_json(metadata)
    except ValidationError as error: raise HTTPException(422,'上传并关联参数不正确，请显式选择目标订单') from error
    initial=service.resolve_entry(db,user,factory_id,audience,identifier,authority_id=body.authority_id,write=True)
    if not initial['state']: raise HTTPException(422,'请选择具体来源资料')
    references.require_schema(db)
    customer=references.customer_for(db,factory_id,initial['state'])
    references.target_entries(db,factory_id,audience,user,body.targets,initial['state']['id'],customer.id)
    prepared=None
    if file:
        content=await file.read(20*1024*1024+1)
        if not content or len(content)>20*1024*1024: raise HTTPException(422,'文件不能为空，单个不超过20MB')
        prepared=await run_order_job(service.prepare_file,file.filename or '',content,db=db)
    try: return references.associate(db,user,factory_id,audience,body,lambda:get_current_user(request,db),upload_identifier=identifier,prepared=prepared)
    except BaseException:
        db.rollback(); raise


@router.post('/{identifier}/references/{reference_id}/deactivate')
def remove_reference(identifier: str,reference_id: str,body: schema.ReferenceRemove,request: Request,
    factory_id: str,audience: schema.Audience,db: Session = Depends(get_db),user: AuthContext = Depends(get_current_user)):
    try: return references.remove(db,user,factory_id,audience,identifier,reference_id,body,lambda:get_current_user(request,db))
    except BaseException:
        db.rollback(); raise


@router.get('/{identifier}/versions/{version_id}/document')
def document(identifier: str, version_id: str, factory_id: str, audience: schema.Audience,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    asset = service.document(db, user, factory_id, audience, identifier, version_id)
    return Response(asset.content, media_type=asset.content_type, headers={
        'Content-Disposition': "attachment; filename*=UTF-8''" + quote(asset.file_name),
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
