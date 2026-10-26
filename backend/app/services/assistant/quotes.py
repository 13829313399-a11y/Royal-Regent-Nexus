"""Model-safe quotation snapshots over the authorized native read-only readers."""
import base64
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from app import db as database
from app.core.time import business_now, parse_business_timestamp
from app.models.internal_quote import InternalQuote, InternalQuoteSection
from app.services import internal_quote as native, internal_quote_queries as reader
from app.services.business_authz import has_permission_for_departments
from .auth_snapshot import fingerprint, matches
from .errors import AssistantError
from .evidence import stable_id
from .help_registry import supplier_only
from .orders import FACTORIES
from .tool_result import validate_result

NAME = 'get_internal_quote_overview'
HEADER_FIELDS = ('id', 'factory_id', 'quote_no', 'product_name', 'customer', 'qty', 'version_label', 'status',
    'module_version', 'formula_version', 'header_revision', 'reference_snapshot_id', 'final_release_status',
    'final_release_revision', 'created_at', 'updated_at', 'workshop_code')
ROW_FIELDS = {*HEADER_FIELDS, 'resource_ref', 'workflow', 'readiness', 'sections', 'financial', 'comparison',
    'version_archived', 'document_archived', 'truncated_fields'}
DEFINITIONS = {
    'quote.documents.v1': '原分页台账筛选命中的逻辑报价文档数；子产品或方案版本可使原文档命中。不是物理版本数，不相加各方案成本。',
    'quote.selected.v1': '按明确厂区重新授权读取的原报价版本数；比较返回基准和目标两个版本。',
    'quote.status.v1': '保留原status及final_release_status。v4为直接输出，不把无需审核或已输出改称审批通过；v2/v3沿原流程。',
    'quote.price.v1': '原summary.authoritative_factory_quote_hkd；未完整核价时未知。HKD保持原报价产品成本口径，接口未明确件/套，不乘qty猜整批金额。',
    'quote.cost.v1': '原summary.factory_price_hkd是原工厂成本汇总，区别于含倍率的authoritative_factory_quote_hkd；缺失/未完成核价不以部分成本或0冒充完整值。',
    'quote.tax.v1': '原rr2_cost_summary.totals为采购成本减税口径；不是发票增值税额、未税售价或含税总额。无对应确认字段时保持未知。',
    'quote.compare.v1': '只比较原系统允许的关联版本。两侧完整核价且币种、原产品/车间/数量基准、公式、定价模式和冻结汇率一致时才提供原成本差及Decimal报价差；否则保留两侧事实、停止相减。',
    'quote.clock.v1': 'as_of为本次数据库快照时间；updated_at为原记录更新时间。读取不会更新报价、参考快照、审批或输出。',
    'quote.financial_access.v1': '金额与成本/利润只在既有internal_quote:summary_read范围开放；read权限不能代替summary_read。',
}


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def number(value):
    if value is None or isinstance(value, bool): return None
    try:
        amount = Decimal(str(value))
        return format(amount, 'f') if amount.is_finite() else None
    except (InvalidOperation, ValueError): return None


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    factory_id: str = Field(min_length=1, max_length=32)
    view: Literal['list', 'detail', 'compare'] = 'list'
    resource_id: str | None = Field(default=None, min_length=1, max_length=64)
    base_resource_id: str | None = Field(default=None, min_length=1, max_length=64)
    status: str = Field(default='', max_length=32)
    keyword: str = Field(default='', max_length=128)
    customer: str = Field(default='', max_length=128)
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode='after')
    def validate_scope(self):
        for value in (self.resource_id, self.base_resource_id):
            if value and value != value.strip(): raise ValueError('ambiguous id')
        if self.resource_id and self.view == 'list': self.view = 'detail'
        if self.view != 'list' and (not self.resource_id or self.status or self.keyword or self.customer or self.cursor):
            raise ValueError('selected versions cannot silently retain list filters')
        if (self.view == 'compare') != bool(self.base_resource_id): raise ValueError('comparison needs two versions')
        if self.base_resource_id and self.base_resource_id == self.resource_id: raise ValueError('same version')
        return self


def authorize(user, factory):
    if user is None or supplier_only(user): raise AssistantError('business_forbidden', '当前身份不可读取内部报价。', 403)
    if factory not in FACTORIES: raise AssistantError('factory_unavailable', '请选择明确的报价厂区。', 422)
    try: reader.authorize(user, factory)
    except HTTPException: raise AssistantError('business_forbidden', '无本厂内部报价读取权限。', 403) from None


def can_financial(user, factory):
    return has_permission_for_departments(user, 'internal_quote:summary_read', factory, native.ALL_QUOTE_DEPARTMENTS)


def financial(db, user, quote):
    unavailable = dict(state='forbidden', currency=None, unit='原报价成本口径（源接口未明确件/套）',
        quote_hkd=None, base_cost_hkd=None, cost_hkd=None, gross_hkd=None, profit_hkd=None,
        tax_deduction_hkd=None, after_deduction_cost_hkd=None, invoice_net=None, invoice_tax=None, invoice_gross=None)
    if not can_financial(user, quote.factory_id): return unavailable
    frozen = quote.module_version == 'v4' and quote.final_release_status == 'issued'
    if frozen:
        manifest = native._json_object(quote.final_submission_manifest_json)
        saved_summary = manifest.get('rr2_cost_summary')
        saved_costs = manifest.get('cost_context')
        # The native legacy view can reconstruct an absent issued summary.
        # Reconstruction is not immutable historical evidence for the model.
        if (not isinstance(saved_summary, dict) or not isinstance(saved_costs, dict)
            or number(saved_costs.get('factory_price_hkd')) is None):
            return {**unavailable, 'state':'issued_snapshot_unavailable'}
    try: summary = reader.summary(db, user, quote.factory_id, quote.id)
    except HTTPException as exc:
        if exc.status_code != 409: raise
        return {**unavailable, 'state':'reference_unavailable'}
    costs = summary.get('rr2_cost_summary') or {}
    complete = summary['pricing_complete'] and (frozen or summary['calculation_phase'] != 'blocked')
    currency = costs.get('currency') if costs.get('currency') in {'HKD', 'USD', 'CNY'} else None
    quote_amount = number(summary.get('authoritative_factory_quote_hkd'))
    complete = bool(complete and currency == 'HKD' and quote_amount is not None)
    table = {row.get('key'):number(row.get('value')) for row in costs.get('t3', []) if isinstance(row, dict)}
    shipping = costs.get('shipping_pricing') or {}
    totals = costs.get('totals') or {}
    reference = native._find_reference_set(db, quote)
    snapshot = native._json_object(reference.snapshot_json) if reference else {}
    fx = snapshot.get('fx') or {}
    return {**unavailable, 'state':'issued_snapshot' if complete and frozen else 'draft_calculated' if complete else 'incomplete',
        'currency':currency, 'quote_hkd':quote_amount if complete else None,
        'base_cost_hkd':number(summary.get('factory_price_hkd')) if complete else None,
        'cost_hkd':table.get('total_cost') if complete else None,
        'gross_hkd':table.get('gross') if complete else None, 'profit_hkd':table.get('profit') if complete else None,
        'tax_deduction_hkd':number(totals.get('total_deduction_hkd')) if complete else None,
        'after_deduction_cost_hkd':number(totals.get('after_deduction_cost_hkd')) if complete else None,
        'formula_version':summary['formula_version'], 'current_formula_version':summary['current_formula_version'],
        'reference_snapshot_id':summary['reference_snapshot_id'], 'reference_sha256':summary['reference_snapshot_sha256'],
        'frozen_reference_fx':{key:number(fx.get(key)) for key in ('rmb_hkd','hkd_usd')},
        'pricing_mode':shipping.get('pricing_mode') if shipping.get('pricing_mode') in {'standard','component'} else None,
        'complete':complete, 'frozen':frozen,
        'incomplete_sections':[{key:str(row.get(key,''))[:160] for key in ('section_code','section_name','reason')}
            for row in summary.get('incomplete_sections',[])[:9]],
        'section_amounts':[{ 'department':row['section_code'], 'revision':row['revision'],
            'status':row['section_status'], 'calculation_status':row['calculation_status'], 'dependency_status':row['dependency_status'],
            # Issued totals come from the frozen manifest; current section rows
            # are not evidence for the historic section amounts. Partial or
            # stale calculations likewise must not masquerade as a valid cost.
            'draft_amount':row['is_draft_amount'], 'hkd':number(row['total_hkd']) if complete and not frozen and row['calculation_status']=='valid' and row['dependency_status']=='current' else None}
            for row in summary['sections']],
    }


def row_out(db, user, quote, *, with_financial):
    item = {key:getattr(quote,key) for key in HEADER_FIELDS}
    item['truncated_fields'] = [key for key,value in item.items() if isinstance(value,str) and len(value)>300]
    item = {key:value[:300] if isinstance(value,str) else value for key,value in item.items()}
    for key in ('created_at','updated_at'):
        parsed = parse_business_timestamp(item[key]); item[key] = parsed.isoformat() if parsed else None
    detail = native.quote_to_out(db, quote)
    readiness = detail.readiness.model_dump(mode='json') if detail.readiness else {}
    item.update(resource_ref='internal-quote:quote:'+quote.id,
        workflow='direct_output' if quote.module_version=='v4' else 'whole_review' if quote.module_version=='v3' else 'section_review' if quote.module_version=='v2' else 'unknown',
        version_archived=detail.version_archived, document_archived=bool(detail.document_archive),
        readiness={key:readiness.get(key) for key in ('ready_sections','required_sections','state')},
        sections=[{key:getattr(section,key) for key in ('department','status','revision','is_required','calculation_status','dependency_status')}
                  for section in detail.sections],
        financial=financial(db,user,quote) if with_financial else None)
    return item


def comparison(db, user, base, target, rows):
    native_comparison = reader.comparison(db,user,target.factory_id,target.id,base.id)
    left,right=rows[0]['financial'],rows[1]['financial']
    reasons=[]
    if not left.get('complete') or not right.get('complete'): reasons.append('至少一个版本未完整核价或金额不可用')
    for key,label in [('product_name','产品'),('qty','数量基准'),('workshop_code','车间'),('formula_version','公式')]:
        if getattr(base,key)!=getattr(target,key): reasons.append(label+'不同')
    for key,label in [('currency','币种'),('pricing_mode','定价模式'),('frozen_reference_fx','冻结汇率')]:
        if left.get(key) is None or right.get(key) is None or left.get(key)!=right.get(key): reasons.append(label+'不同或缺失')
    if any(v is None for side in (left,right) for v in side.get('frozen_reference_fx',{}).values()): reasons.append('冻结汇率缺失')
    allowed={'quote_no','version_label','product_name','customer','qty','formula_version','reference_snapshot_id','final_release_status','final_release_revision'}
    changes=[dict(field=c.path,before=str(c.before)[:300] if c.before is not None else None,
                  after=str(c.after)[:300] if c.after is not None else None) for c in native_comparison.header_changes if c.path in allowed]
    return dict(base_id=base.id,target_id=target.id,comparable=not reasons,reasons=reasons,header_changes=changes,
        base_cost_delta_hkd=number(native_comparison.total_delta_hkd) if not reasons else None,
        quote_delta_hkd=format(Decimal(right['quote_hkd'])-Decimal(left['quote_hkd']),'f') if not reasons else None,
        sections=[dict(department=s.section_code,before_revision=s.before_revision,after_revision=s.after_revision,
            before_status=s.before_status,after_status=s.after_status,input_changed=bool(s.payload_changes)) for s in native_comparison.sections])


def visible(db,user,source):
    factory=source['scope']['factory_id'];authorize(user,factory)
    if not matches(db,user,source.get('authorization_fingerprint')): return False
    if source.get('financial_access') and not can_financial(user,factory): return False
    for resource in source.get('resources',[]):
        if resource.get('module_id')!='internal-quote' or resource.get('resource_type')!='quote': return False
        if not db.scalar(select(InternalQuote.id).where(InternalQuote.id==resource['resource_id'],InternalQuote.factory_id==factory)): return False
    return True


def query(user,arguments,run_id,*,tool_call_id=None,step_id=None):
    try: args=Arguments.model_validate(arguments)
    except (ValidationError,ValueError,TypeError): raise AssistantError('tool_invalid','报价查询参数无效，请核对厂区、版本和筛选。',422) from None
    authorize(user,args.factory_id)
    requested=business_now()
    with database.SessionLocal() as db:
        if db.get_bind().dialect.name=='sqlite':db.connection().exec_driver_sql('BEGIN')
        elif db.get_bind().dialect.name=='postgresql':db.connection(execution_options={'isolation_level':'REPEATABLE READ'})
        auth=fingerprint(db,user)
        filters={key:getattr(args,key) for key in ('view','status','keyword','customer')}
        try:
            if args.view=='list': records=reader.documents(db,user,args.factory_id,status=args.status,keyword=args.keyword,customer=args.customer)
            else:
                records=([reader.record(db,user,args.factory_id,args.base_resource_id)] if args.base_resource_id else [])
                records.append(reader.record(db,user,args.factory_id,args.resource_id))
            if args.view=='compare' and not can_financial(user,args.factory_id): raise HTTPException(403)
            signature=[{key:getattr(row,key) for key in HEADER_FIELDS} for row in records]
            section_state=list(db.execute(select(InternalQuoteSection.quote_id,InternalQuoteSection.department,
                InternalQuoteSection.revision,InternalQuoteSection.status,InternalQuoteSection.calculation_hash,
                InternalQuoteSection.calculation_status,InternalQuoteSection.dependency_status)
                .where(InternalQuoteSection.quote_id.in_([r.id for r in records])).order_by(InternalQuoteSection.quote_id,InternalQuoteSection.department)).all()) if records else []
            key=stable_id(auth,args.factory_id,compact(filters),compact(signature),compact([list(r) for r in section_state]))
            offset=0;anchor=requested
            if args.cursor:
                try:
                    c=json.loads(base64.urlsafe_b64decode(args.cursor.encode('ascii')));anchor=datetime.fromisoformat(c['at']);offset=c['offset']
                    if (anchor.tzinfo is None or type(offset) is not int or not 0<offset<len(records)
                        or c['key']!=stable_id(key,anchor.isoformat(),offset) or not 0<=(requested-anchor).total_seconds()<=300):raise ValueError()
                except (ValueError,TypeError,KeyError,AttributeError,OverflowError):raise AssistantError('cursor_invalid','报价、权限或筛选已变化，请从第一页重新查询。',422) from None
            shown=records[offset:offset+args.limit] if args.view=='list' else records
            rows=[row_out(db,user,row,with_financial=args.view!='list') for row in shown]
            if args.view=='compare':rows[-1]['comparison']=comparison(db,user,records[0],records[1],rows)
        except HTTPException as exc:
            if exc.status_code not in (400,403,404,409):raise
            raise AssistantError('business_forbidden' if exc.status_code==403 else 'source_unavailable',
                '无此版本的金额比较权限。' if exc.status_code==403 else '报价版本不存在、不在本厂范围或不能按原系统规则比较。',exc.status_code) from None
        refs=[row['resource_ref'] for row in rows]
        resources=[dict(module_id='internal-quote',resource_type='quote',resource_id=row.id) for row in records]
        source_id=stable_id(run_id,NAME,key,offset,requested.isoformat())
        unknowns=[dict(field='invoice_net/invoice_tax/invoice_gross',reason=DEFINITIONS['quote.tax.v1']),
            dict(field='quantity_unit',reason='源报价接口没有明确件/套计价单位；不按产品数量推算整批金额。')]
        if args.view=='list':unknowns.append(dict(field='financial',reason='列表只读取文档状态；查询金额须选择原报价版本并独立复核汇总权限。'))
        if any(row['financial'] and not row['financial'].get('complete') for row in rows):unknowns.append(dict(field='financial',reason='部分版本无金额权限、缺参考快照或未完成核价；缺失金额保留未知。'))
        if any(row['truncated_fields'] for row in rows):unknowns.append(dict(field='rows',reason='长文本仅返回前300字，完整内容请查看原报价。'))
        source=dict(kind='business',source_id=source_id,run_id=run_id,title='内部报价原版本',tool_name=NAME,
            resources=resources,scope=dict(factory_id=args.factory_id,scope_label='本厂逻辑报价文档' if args.view=='list' else '本厂选中报价版本',authorization='current_user',filters=filters),
            as_of=requested.isoformat(),retrieved_at=business_now().isoformat(),data_mode='snapshot',unknown_fields=[u['reason'] for u in unknowns],
            authorization_fingerprint=auth,financial_access=args.view!='list' and can_financial(user,args.factory_id))
        metric_key='document_count' if args.view=='list' else 'version_count'
        metrics={metric_key:dict(value=len(records),unit='逻辑报价文档' if args.view=='list' else '原报价版本',
            definition_id='quote.documents.v1' if args.view=='list' else 'quote.selected.v1',status='known')}
        actions=[dict(type='open_record', label='打开原报价：'+row.quote_no[:40]+' / '+row.version_label[:20],
            route_name='internal-quote-collaboration', params=dict(quoteId=row.id), query=dict(factory=args.factory_id),
            resource=dict(module_id='internal-quote',resource_type='quote',resource_id=row.id)) for row in shown]
        truncated=offset+len(shown)<len(records)
        cursor=base64.urlsafe_b64encode(compact(dict(at=anchor.isoformat(),offset=offset+len(shown),key=stable_id(key,anchor.isoformat(),offset+len(shown)))).encode()).decode() if truncated else None
        result=dict(record_type='tool_result',contract_version=3,tool_name=NAME,tool_version='quotes-v3.1',
            tool_call_id=tool_call_id or stable_id(run_id,key,offset),run_id=run_id,step_id=step_id or NAME,status='empty' if not records else 'partial',
            scope=dict(factory_ids=[args.factory_id],module_id='internal-quote',filters=filters,resource_refs=refs if args.view!='list' else [],
                coverage='filtered_scope' if args.view=='list' else 'selected_resources',label=source['scope']['scope_label']),
            requested_at=requested.isoformat(),as_of=requested.isoformat(),observed_at=None,retrieved_at=source['retrieved_at'],
            timezone='Asia/Shanghai',business_date=requested.date().isoformat(),data_mode='snapshot',
            freshness=dict(state='fresh',max_age_seconds=30,cache_hit=False,cache_created_at=None,policy_id='quote-current-v1'),
            metrics=metrics,rows=rows,total_count=len(records),returned_count=len(rows),truncated=truncated,next_cursor=cursor,
            definitions=DEFINITIONS,unknown_fields=unknowns,source_refs=[source_id],
            allowed_actions=[dict(action_id=stable_id(source_id,ref),kind='navigate',label=action['label'],resource_ref=ref)
                for ref,action in zip(refs,actions)],diagnostic_code=None)
        return validate_result(result,registered_sources=[source_id],registered_resources=refs,row_fields=ROW_FIELDS),source,actions
