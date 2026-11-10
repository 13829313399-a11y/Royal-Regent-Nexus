"""Original pure workbook tools, with immutable local export evidence."""
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter,Depends,File,Form,HTTPException,UploadFile
from app import order_contract as contract
from app.services.customer_order_jobs import run_order_job,order_job_request
from app.services.customer_order_360_workbook import organize_workbook
from app.services.customer_order_casdon import _casdon_preview,_casdon_export,fingerprint as source_fingerprint,VERSION


def schedule_tools_router(history,fixed_factory,output_response):
    router=APIRouter(prefix='/api/customer-order-ledger/schedule',dependencies=[Depends(order_job_request)])
    async def upload(factory_id,expected,file):
        if factory_id!=fixed_factory:raise HTTPException(403,'本试用包不能切换厂区。')
        if factory_id!=expected:raise HTTPException(400,'当前厂区不支持此排期整理工具。')
        contract._validate_upload(file,kind='客户排期',supported=('.xlsx',))
        content=await file.read(contract.MAX_SCHEDULE_BYTES+1)
        if not content or len(content)>contract.MAX_SCHEDULE_BYTES:raise HTTPException(400,'客户排期为空或超过 35MB 限制。')
        return Path((file.filename or '排期.xlsx').replace('\\','/')).name,content

    @router.post('/organize-360')
    async def organize(factory_id:str,schedule_file:UploadFile=File(...)):
        name,content=await upload(factory_id,'huakang-a',schedule_file)
        output,output_name,report,source_hash=await run_order_job(organize_workbook,name,content)
        as_of=report['as_of_date']
        fingerprint=sha256(f'360-inspection-placement-v1|{source_hash}|{as_of}'.encode()).hexdigest()
        controls={'source_schedule_name':name,'source_schedule_sha256':source_hash,'preview_fingerprint':fingerprint,
            'received_date':as_of,'reason':'按已有验货日期整理 Excel；不改变台账实际走货数量。','report':report,'operation':'organize-360'}
        evidence=history.save('360',output_name,output,0,controls)
        warnings=report.get('warnings',[])
        response_report={'as_of_date':as_of,'sheets':report.get('sheets',{}),'warning_count':len(warnings),'warnings':[str(w)[:100] for w in warnings[:3]]}
        response=output_response(evidence)
        response.headers['X-Export-Audit-Id']=evidence['id']
        response.headers['X-Schedule-Organize-Report']=quote(json.dumps(response_report,ensure_ascii=False,separators=(',',':')),safe='')
        return response

    @router.post('/casdon/preview')
    async def casdon_preview(factory_id:str,schedule_file:UploadFile=File(...)):
        name,content=await upload(factory_id,'huadeng',schedule_file)
        return await run_order_job(_casdon_preview,name,content)

    @router.post('/casdon/export')
    async def casdon_export(factory_id:str,schedule_file:UploadFile=File(...),fingerprint:str=Form(...,max_length=64),
        action:str=Form(...,max_length=16),selections:str=Form('[]',max_length=5000),reason:str=Form('',max_length=500),confirmed:bool=Form(False)):
        name,content=await upload(factory_id,'huadeng',schedule_file)
        if action not in {'prepare','ship','restore'}:raise HTTPException(400,'不支持的整理操作。')
        if action!='prepare' and (not confirmed or len(reason.strip())<4):raise HTTPException(400,'请确认所选订单并填写至少4字的整理原因。')
        if fingerprint!=source_fingerprint(content):raise HTTPException(409,'源文件已变化，请重新预览。')
        try:ids=json.loads(selections)
        except (ValueError,TypeError) as exc:raise HTTPException(400,'所选订单格式不正确。') from exc
        output,output_name,report,source_hash=await run_order_job(_casdon_export,name,content,fingerprint,action,ids)
        controls={'source_schedule_name':name,'source_schedule_sha256':source_hash,'preview_fingerprint':fingerprint,
            'preview_schema_version':VERSION,'received_date':date.today().isoformat(),'operation':'casdon-'+action,
            'reason':reason.strip(),'selections':ids,'report':report,'scope':'仅整理Excel，不更改台账走货数量'}
        evidence=history.save('casdon',output_name,output,0,controls)
        warnings=report.get('warnings',[])
        summary={'moved':len(report['moves']),'warning_count':len(warnings),'warnings':warnings[:3]}
        response=output_response(evidence)
        response.headers['X-Export-Audit-Id']=evidence['id']
        response.headers['X-Casdon-Report']=quote(json.dumps(summary,ensure_ascii=False),safe='')
        return response
    return router
