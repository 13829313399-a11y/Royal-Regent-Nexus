"""Local persistent ledger using the original ERP state machine, without remote integration."""
from datetime import date
from typing import Literal
from urllib.parse import quote
from pydantic import TypeAdapter,ValidationError
from fastapi import APIRouter,Depends,File,Form,HTTPException,Query,Response,UploadFile
from sqlalchemy import select,func,update
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm import Session
from app.db import local_sessions
from app.models.customer_order_ledger import OrderLedgerLine as Line,OrderLedgerSource as Source,OrderLedgerDispatch as Dispatch,OrderLedgerShipment as Shipment
from app.schemas.customer_order_ledger import AmendIn,DispatchIn,ReasonIn,RestoreIn,ShipmentIn,HistorySelection,HistoryOpeningIn
from app.services import customer_order_ledger as ledger,customer_order_queries as queries,customer_order_history as migration,customer_order_schedule as schedule
from app.services.auth import now_text
from app.services.customer_order_jobs import order_job_request,run_order_job

from app.catalog import profiles

ACTOR='本机试用操作员 (local-trial)'


def ledger_router(history,fixed_factory,scoped,prepare_confirmed):
    sessions=local_sessions(history.path,new_database=history.new_database)
    router=APIRouter(prefix='/api/customer-order-ledger')
    router.add_event_handler('shutdown',sessions.kw['bind'].dispose)
    def database():
        with sessions() as session: yield session
    def factory(value):
        if value!=fixed_factory:raise HTTPException(403,'当前数据仅属于本试用包固定厂区。')
    def transaction(db,operation):
        try:
            result=operation();db.commit();return result
        except (IntegrityError,OperationalError) as exc:
            db.rollback();raise HTTPException(409,'本机订单正在更新或存在重复记录，请刷新核对后重试。') from exc
        except Exception:
            db.rollback();raise
    def mutate(db,factory_id,line_id,body,action):
        factory(factory_id);line=ledger.get_line(db,fixed_factory,line_id)
        def perform():
            action(db,line,body,ACTOR);return ledger.line_out(db,line)
        return transaction(db,perform)

    @router.get('/capabilities')
    def capabilities(factory_id:str,recipient:Literal['pmc','warehouse','injection']='pmc'):
        factory(factory_id)
        return {**{key:True for key in ('read','write','dispatch','shipment_confirm','inbox_read','inbox_receive')},
            'cutting_dispatch_enabled':False,'carton_change':False,'local_only':True}

    @router.get('/lines')
    def lines(factory_id:str,customer_code:str='',view:Literal['all','unshipped','shipped','cancelled']='all',
              q:str=Query('',max_length=255),page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=200),db:Session=Depends(database)):
        factory(factory_id)
        if customer_code:scoped(customer_code,factory_id)
        query=queries.statement(fixed_factory,customer_code=customer_code,view=view,q=q)
        total,items=queries.page(db,query,page_number=page,page_size=page_size)
        customers=db.execute(select(Line.customer_code,Line.customer_name).where(Line.factory_id==fixed_factory).distinct()).all()
        return {'items':[ledger.line_out(db,item) for item in items],'total':total,'page':page,'page_size':page_size,
                'customers':[{'code':code,'name':name} for code,name in customers]}

    @router.get('/lines/{line_id}')
    def detail(line_id:str,factory_id:str,db:Session=Depends(database)):
        factory(factory_id);return ledger.detail(db,ledger.get_line(db,fixed_factory,line_id))

    @router.get('/sources/{source_id}')
    def source(source_id:str,factory_id:str,db:Session=Depends(database)):
        factory(factory_id)
        row=db.scalar(select(Source).where(Source.id==source_id,Source.factory_id==fixed_factory))
        if row is None:raise HTTPException(404,'本机原始文件记录不存在。')
        return Response(row.content,media_type='application/octet-stream',headers={
            'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row.file_name)})

    @router.post('/imports/{customer_code}',dependencies=[Depends(order_job_request)])
    async def import_orders(customer_code:str,factory_id:str=Form(...),received_date:date=Form(...),
        confirmed:bool=Form(...),skipped_issue_keys:str=Form('[]'),manual_overrides:str=Form('[]'),
        preview_fingerprint:str=Form(...),confirmation_reason:str=Form(''),source_kind:Literal['formal','supplementary']=Form('formal'),
        reconcile_line_id:str=Form(''),expected_revision:int|None=Form(None),reconciliation_reason:str=Form(''),
        po_files:list[UploadFile]=File(...),schedule_file:UploadFile=File(...),db:Session=Depends(database)):
        factory(factory_id);scoped(customer_code,factory_id)
        if reconcile_line_id and not 4<=len(reconciliation_reason.strip())<=500:
            raise HTTPException(400,'关联原因需要 4 至 500 个字。')
        # A single original writer rebuilds authoritative rows, then controls are checked before any database writes.
        args,resolved,output,name,controls=await prepare_confirmed(customer_code,factory_id,received_date,
            po_files,schedule_file,confirmed,skipped_issue_keys,manual_overrides,preview_fingerprint,confirmation_reason)
        resolved['customer_name']=scoped(customer_code,factory_id)['name']
        def perform():
            target=ledger.get_line(db,fixed_factory,reconcile_line_id) if reconcile_line_id else None
            result=ledger.import_preview(db,preview=resolved,
                files=[(name,content,source_kind) for name,content in args['po_files']]+[(args['schedule_file_name'],args['schedule_content'],'schedule')],
                source_kind=source_kind,actor=ACTOR,reason=reconciliation_reason.strip() if target else controls['reason'],
                controls=controls,reconcile_line=target,expected_revision=expected_revision)
            evidence=history.save_on(db.connection().connection.driver_connection,customer_code,name,output,len(resolved.get('rows',[])),controls)
            return {**result,'local_only':True,'export_id':evidence['id'],'output_sha256':evidence['output_sha256']}
        return transaction(db,perform)

    @router.post('/lines/{line_id}/amend')
    def amend(line_id:str,factory_id:str,body:AmendIn,db:Session=Depends(database)):
        return mutate(db,factory_id,line_id,body,ledger.amend)

    @router.post('/lines/{line_id}/cancel')
    def cancel(line_id:str,factory_id:str,body:ReasonIn,db:Session=Depends(database)):
        return mutate(db,factory_id,line_id,body,ledger.cancel)

    @router.post('/lines/{line_id}/restore')
    def restore(line_id:str,factory_id:str,body:RestoreIn,db:Session=Depends(database)):
        return mutate(db,factory_id,line_id,body,ledger.restore)

    @router.post('/lines/{line_id}/dispatch')
    def dispatch(line_id:str,factory_id:str,body:DispatchIn,db:Session=Depends(database)):
        if set(body.recipients)-{'pmc','warehouse','injection'}:raise HTTPException(422,'本试用版仅提供 PMC、仓库和注塑的本机收件记录。')
        return mutate(db,factory_id,line_id,body,ledger.dispatch)

    @router.post('/lines/{line_id}/shipments')
    def ship(line_id:str,factory_id:str,body:ShipmentIn,db:Session=Depends(database)):
        return mutate(db,factory_id,line_id,body,ledger.ship)

    @router.post('/shipments/{shipment_id}/reverse')
    def reverse(shipment_id:str,factory_id:str,body:ReasonIn,db:Session=Depends(database)):
        factory(factory_id)
        shipment=db.scalar(select(Shipment).where(Shipment.id==shipment_id,Shipment.factory_id==fixed_factory))
        if shipment is None:raise HTTPException(404,'本机走货记录不存在。')
        def action(db,line,body,actor):ledger.reverse_shipment(db,line,shipment,body,actor)
        return mutate(db,factory_id,shipment.line_id,body,action)

    @router.get('/inbox')
    def inbox(factory_id:str,recipient:Literal['pmc','warehouse','injection'],page:int=Query(1,ge=1),
        page_size:int=Query(50,ge=1,le=200),db:Session=Depends(database)):
        factory(factory_id)
        query=select(Dispatch).where(Dispatch.factory_id==fixed_factory,Dispatch.recipient==recipient)
        total=db.scalar(select(func.count()).select_from(query.subquery()))
        items=db.scalars(query.order_by(Dispatch.created_at.desc(),Dispatch.id).offset((page-1)*page_size).limit(page_size)).all()
        latest=dict(db.execute(select(Line.id,Line.version).where(Line.factory_id==fixed_factory,Line.id.in_([item.line_id for item in items]))).all())
        return {'items':[ledger.dispatch_out(item)|{'latest_version':latest[item.line_id],'carton_processed':None} for item in items],
                'total':total,'page':page,'page_size':page_size,'local_only':True}

    @router.post('/inbox/{dispatch_id}/receive')
    def receive(dispatch_id:str,factory_id:str,recipient:Literal['pmc','warehouse','injection'],db:Session=Depends(database)):
        factory(factory_id)
        item=db.scalar(select(Dispatch).where(Dispatch.id==dispatch_id,Dispatch.factory_id==fixed_factory,Dispatch.recipient==recipient))
        if item is None:raise HTTPException(404,'当前本机部门收件箱没有此记录。')
        def perform():
            db.execute(update(Dispatch).where(Dispatch.id==item.id,Dispatch.received_at=='').values(
                received_at=now_text(),received_by=ACTOR),execution_options={'synchronize_session':False})
            db.refresh(item)
            return ledger.dispatch_out(item)|{'latest_version':ledger.get_line(db,fixed_factory,item.line_id).version}
        return transaction(db,perform)

    @router.get('/history/customers')
    def history_customers(factory_id:str):
        factory(factory_id)
        return {'items':[{'code':item['code'],'name':item['name']} for item in profiles(fixed_factory)]}

    async def history_parse(db,factory_id,customer_code,upload):
        factory(factory_id);profile=scoped(customer_code,factory_id)
        content=await upload.read(migration.MAX_BYTES+1)
        workbook=await run_order_job(migration.parse_workbook,content,db=db)
        parsed=migration.preview(db,content,upload.filename or '',fixed_factory,customer_code,profile['name'],workbook=workbook)
        return content,parsed

    @router.post('/history/preview',dependencies=[Depends(order_job_request)])
    async def history_preview(factory_id:str=Form(...),customer_code:str=Form(...),schedule_file:UploadFile=File(...),db:Session=Depends(database)):
        _,parsed=await history_parse(db,factory_id,customer_code,schedule_file)
        return parsed

    @router.post('/history/confirm',dependencies=[Depends(order_job_request)])
    async def history_confirm(factory_id:str=Form(...),customer_code:str=Form(...),schedule_file:UploadFile=File(...),
        fingerprint:str=Form(...),cutoff_date:date=Form(...),reason:str=Form(...),selections:str=Form(...),
        confirmed:bool=Form(...),db:Session=Depends(database)):
        factory(factory_id);scoped(customer_code,factory_id)
        if not confirmed or not 4<=len(reason.strip())<=500:
            raise HTTPException(400,'请确认所选订单的数量、状态及期初口径，并填写 4 至 500 字核对说明')
        if len(selections)>150000:raise HTTPException(400,'单批最多选择 500 条订单')
        try:selected=TypeAdapter(list[HistorySelection]).validate_json(selections)
        except ValidationError as exc:raise HTTPException(400,'所选订单或期初走货数量格式不正确') from exc
        if not 1<=len(selected)<=500:raise HTTPException(400,'请选择 1 至 500 条订单')
        content,parsed=await history_parse(db,factory_id,customer_code,schedule_file)
        return transaction(db,lambda:migration.confirm(db,parsed=parsed,content=content,selections=selected,
            fingerprint=fingerprint,cutoff_date=cutoff_date,reason=reason.strip(),actor=ACTOR))

    @router.post('/lines/{line_id}/history-opening')
    def correct_opening(line_id:str,factory_id:str,body:HistoryOpeningIn,db:Session=Depends(database)):
        return mutate(db,factory_id,line_id,body,migration.correct_opening)

    @router.get('/schedule/customers')
    def schedule_customers(factory_id:str):
        factory(factory_id)
        return {'factory_id':fixed_factory,'items':[{'code':item['code'],'name':item['name']} for item in profiles(fixed_factory)]}

    @router.get('/schedule')
    def customer_schedule(factory_id:str,customer_code:str=Query(...,min_length=1,max_length=64),
        q:str=Query('',max_length=255),date_from:date|None=None,date_to:date|None=None,
        unshipped_page:int=Query(1,ge=1),shipped_page:int=Query(1,ge=1),inspection_pending_page:int=Query(1,ge=1),
        completed_page:int=Query(1,ge=1),cancelled_page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=200),db:Session=Depends(database)):
        factory(factory_id);profile=scoped(customer_code,factory_id)
        if date_from and date_to and date_from>date_to:raise HTTPException(400,'交期开始日期不能晚于结束日期')
        return schedule.read_schedule(db,factory=fixed_factory,customer=customer_code,customer_name=profile['name'],
            q=q,date_from=date_from,date_to=date_to,pages={'unshipped':unshipped_page,'shipped':shipped_page,
            'cancelled':cancelled_page,'inspection_pending':inspection_pending_page,'completed':completed_page},page_size=page_size)

    return router
