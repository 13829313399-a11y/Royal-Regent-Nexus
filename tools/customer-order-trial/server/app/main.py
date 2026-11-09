"""Factory-bound, loopback-only trial for the unchanged customer order engines."""
from copy import deepcopy
from datetime import date
from pathlib import Path
from urllib.parse import quote
import json

from fastapi import Depends,FastAPI,File,Form,HTTPException,Query,Request,Response,UploadFile
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from app.catalog import CUSTOMERS,FACTORIES,profiles
from app.history import History
from app import order_contract as contract
from app.services import customer_order_jobs as jobs

OPERATIONS=frozenset({'_create_special_batch_preview','_export_special_batch_schedule',
 '_create_mapped_customer_preview','_export_mapped_customer_schedule','parse_workbook','_casdon_preview','_casdon_export','organize_workbook'})
MAX_REQUEST_BYTES=120*1024**2


class LocalBoundary:
    def __init__(self,app,authority):
        self.app=app;self.authority=authority;self.origin='http://'+authority
    async def __call__(self,scope,receive,send):
        if scope['type']!='http': return await self.app(scope,receive,send)
        headers=scope.get('headers',[])
        hosts=[v.decode('latin-1') for k,v in headers if k.lower()==b'host']
        origins=[v.decode('latin-1') for k,v in headers if k.lower()==b'origin']
        if hosts!=[self.authority] or (origins and origins!=[self.origin]) or scope['method']=='OPTIONS':
            return await JSONResponse({'detail':'请从本机试用版启动后打开的页面操作。'},status_code=403)(scope,receive,send)
        if scope['path'].startswith('/api/') and scope['method'] not in {'GET','HEAD'}:
            markers=[v for k,v in headers if k.lower()==b'x-order-trial']
            if markers!=[b'1']:
                return await JSONResponse({'detail':'请从本厂区订单试用页面提交。'},status_code=403)(scope,receive,send)
        lengths=[v for k,v in headers if k.lower()==b'content-length']
        try: size=int(lengths[0]) if len(lengths)==1 else 0
        except ValueError: size=-1
        if len(lengths)>1 or size<0 or size>MAX_REQUEST_BYTES:
            return await JSONResponse({'detail':'本次上传内容超过 120MB。'},status_code=413)(scope,receive,send)
        consumed=0
        async def bounded_receive():
            nonlocal consumed
            message=await receive()
            if message['type']=='http.request':
                consumed+=len(message.get('body',b''))
                if consumed>MAX_REQUEST_BYTES: raise HTTPException(413,'本次上传内容超过 120MB。')
            return message
        async def private_send(message):
            if message['type']=='http.response.start':
                message=dict(message);response_headers=list(message.get('headers',[]))
                response_headers.extend([(b'x-content-type-options',b'nosniff'),(b'referrer-policy',b'no-referrer')])
                if scope['path'].startswith('/api/'):response_headers.append((b'cache-control',b'no-store'))
                message['headers']=response_headers
            await send(message)
        await self.app(scope,bounded_receive,private_send)


def create_app(data_dir,static_dir=None,factory_id='huaxing',host='127.0.0.1',port=8765):
    if factory_id not in CUSTOMERS: raise ValueError('本试用版未开放该厂区订单映射。')
    if host!='127.0.0.1' or not isinstance(port,int) or not 1<=port<=65535:raise ValueError('试用版仅支持 127.0.0.1 本地端口。')
    history=History(data_dir,factory_id)
    jobs.OPERATIONS=OPERATIONS
    jobs.LOCK_PATH=Path(data_dir).resolve()/'.file-worker.lock'
    app=FastAPI(title=FACTORIES[factory_id]+'订单排期本地试用',docs_url=None,redoc_url=None,openapi_url=None)
    app.state.history=history;app.state.factory_id=factory_id
    app.add_middleware(LocalBoundary,authority=f'{host}:{port}')
    registered=profiles(factory_id)

    @app.get('/api/health')
    def health():return {'status':'ok','service':'customer-order-trial','factory_id':factory_id,'schema':1}

    @app.get('/api/config')
    def config():return {'factory_id':factory_id,'factory_name':FACTORIES[factory_id],
        'customers':registered,'duplicate_confirmation_enabled':True,
        'capabilities':{'history_import':True,'ledger_schedule':True,'workbook_tools':True},
        'scope':'本机订单台账、排期导出、部门收件及走货记录；不连接线上系统，发送仅写入本机部门收件箱。',
        'limits':{'po_files':contract.MAX_BATCH_PO_FILES,'po_bytes':contract.MAX_PO_BYTES,
                  'batch_po_bytes':contract.MAX_BATCH_PO_BYTES,'schedule_bytes':contract.MAX_SCHEDULE_BYTES}}

    def scoped(customer,submitted):
        if submitted!=factory_id:raise HTTPException(403,'本试用包只处理 '+FACTORIES[factory_id]+'，不能切换厂区。')
        profile=next((row for row in registered if row['code']==customer),None)
        if profile is None:raise HTTPException(400,'当前厂区未开放此客户映射。')
        return profile

    async def sources(customer,submitted,received,uploads,schedule):
        profile=scoped(customer,submitted)
        usable=[file for file in uploads if not contract._is_macos_metadata_upload(file.filename or '')]
        if not 1<=len(usable)<=contract.MAX_BATCH_PO_FILES:raise HTTPException(400,'请选择 1 至 30 份有效 PO 文件。')
        files=[];total=0
        for file in usable:
            contract._validate_upload(file,kind='PO',supported=tuple(profile['po_extensions']))
            content=await file.read(contract.MAX_PO_BYTES+1)
            if not content or len(content)>contract.MAX_PO_BYTES:raise HTTPException(400,'PO 文件为空或超过 12MB 限制。')
            total+=len(content)
            if total>contract.MAX_BATCH_PO_BYTES:raise HTTPException(400,'本批 PO 文件合计超过 80MB 限制。')
            files.append((Path((file.filename or '').replace('\\','/')).name,content))
        contract._validate_upload(schedule,kind='客户排期',supported=('.xlsx',))
        content=await schedule.read(contract.MAX_SCHEDULE_BYTES+1)
        if not content or len(content)>contract.MAX_SCHEDULE_BYTES:raise HTTPException(400,'客户排期为空或超过 35MB 限制。')
        return dict(customer_code=customer,factory_id=factory_id,received_date=received.isoformat(),po_files=files,
                    schedule_file_name=Path((schedule.filename or '').replace('\\','/')).name,schedule_content=content)

    def finalize(preview,received):
        contract._apply_customer_order_confirmation_policy(preview,duplicate_confirmation_authorized=True)
        preview['preview_fingerprint']=contract._preview_fingerprint(preview,received)
        return preview

    @app.post('/api/orders/preview',dependencies=[Depends(jobs.order_job_request)])
    async def preview(customer_code:str=Form(...),factory_id:str=Form(...),received_date:date=Form(...),
        po_files:list[UploadFile]=File(...),schedule_file:UploadFile=File(...)):
        args=await sources(customer_code,factory_id,received_date,po_files,schedule_file)
        operation=contract._create_special_batch_preview if customer_code in {'buzzbee','dickie','caixing'} else contract._create_mapped_customer_preview
        result=await jobs.run_order_job(operation,**args)
        return finalize(result,args['received_date'])

    def output_response(row):
        return Response(row['content'],media_type=contract.XLSX_CONTENT_TYPE,headers={
            'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['file_name']),
            'X-Export-Id':row['id'],'X-Output-SHA256':row['output_sha256'],
            'X-Workbook-Password-Required':str(json.loads(row['controls']).get('password_required',False)).lower()})

    async def prepare_confirmed(customer_code,factory_id,received_date,po_files,schedule_file,confirmed,
        skipped_issue_keys,manual_overrides,preview_fingerprint,confirmation_reason):
        scoped(customer_code,factory_id)
        if not confirmed:raise HTTPException(400,'请先核对预览并明确确认生成。')
        if len(skipped_issue_keys)>2_000_000 or len(manual_overrides)>4_000_000:raise HTTPException(400,'人工核对内容过大。')
        keys=contract._parse_skipped_issue_keys(skipped_issue_keys)
        overrides=contract._parse_manual_overrides(manual_overrides)
        resolution=keys|{item['issue_key'] for item in overrides}
        contract._ensure_test_duplicate_confirmation_allowed(resolution)
        reason=contract._validated_confirmation_reason(resolution,confirmation_reason)
        args=await sources(customer_code,factory_id,received_date,po_files,schedule_file)
        operation=contract._export_special_batch_schedule if customer_code in {'buzzbee','dickie','caixing'} else contract._export_mapped_customer_schedule
        output,name,resolved=await jobs.run_order_job(operation,**args,skipped_issue_keys=resolution,manual_overrides=overrides)
        validated=finalize(deepcopy(resolved),args['received_date'])
        contract._ensure_preview_fingerprint(validated,args['received_date'],preview_fingerprint)
        actual_keys=contract._actual_confirmed_issue_keys(validated,resolution)
        contract._actual_manual_overrides(validated,overrides)
        controls={'preview_fingerprint':preview_fingerprint,'received_date':args['received_date'],
            'confirmed_issue_keys':sorted(actual_keys),'manual_overrides':overrides,'reason':reason,
            'source_po_names':validated.get('po_file_names',[]),'source_po_sha256s':validated.get('source_po_sha256s',[]),
            'source_schedule_name':args['schedule_file_name'],'source_schedule_sha256':validated.get('source_schedule_sha256',''),
            'password_required':bool(resolved.get('_schedule_encrypted'))}
        return args,resolved,output,name,controls

    @app.post('/api/orders/export',dependencies=[Depends(jobs.order_job_request)])
    async def export(customer_code:str=Form(...),factory_id:str=Form(...),received_date:date=Form(...),
        po_files:list[UploadFile]=File(...),schedule_file:UploadFile=File(...),confirmed:bool=Form(...),
        skipped_issue_keys:str=Form('[]'),manual_overrides:str=Form('[]'),preview_fingerprint:str=Form(...),
        confirmation_reason:str=Form('')):
        args,resolved,output,name,controls=await prepare_confirmed(customer_code,factory_id,received_date,
            po_files,schedule_file,confirmed,skipped_issue_keys,manual_overrides,preview_fingerprint,confirmation_reason)
        row=history.save(customer_code,name,output,len(resolved.get('rows',[])),controls)
        return output_response(row)

    @app.get('/api/orders/exports')
    def exports(page:int=Query(1,ge=1,le=10000)):return history.list(page)

    @app.get('/api/orders/exports/{ident}/download')
    def download(ident:str):
        row=history.get(ident)
        if row is None:raise HTTPException(404,'导出记录不存在。')
        return output_response(row)

    from app.local_ledger import ledger_router
    app.include_router(ledger_router(history,factory_id,scoped,prepare_confirmed))
    from app.schedule_tools import schedule_tools_router
    app.include_router(schedule_tools_router(history,factory_id,output_response))

    if static_dir is not None:
        directory=Path(static_dir).resolve()
        if not (directory/'index.html').is_file():raise RuntimeError('缺少试用页面，请完整解压后启动。')
        app.mount('/',StaticFiles(directory=directory,html=True),name='web')
    return app
