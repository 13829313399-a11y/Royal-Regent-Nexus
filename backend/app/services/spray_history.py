"""Historical facts and source associations are separate from live stock."""
from collections import defaultdict
from hashlib import sha256
import json
import re
from decimal import Decimal as D
from sqlalchemy import select, update
from fastapi import HTTPException
from openpyxl.utils.datetime import from_excel
from app.models import spray_production as m
from app.services import spray_production as s

KINDS = {"order":"接单", "receipt":"来料", "report":"生产日报", "shipment":"送货", "settlement":"月结对照", "payroll":"工资", "purchase":"采购", "material":"油漆收发耗用", "returnable":"容器往来", "expense":"收支费用", "production_summary":"生产汇总对照", "price":"工价报价"}
NUMBERS={"quantity","price","amount","regular_hours","overtime_hours","wage","difference","received","consumed"}
IDENTITY=("kind","business_date","document_no","customer","product_no","part_name","operation","source_line","unit","currency")


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def cell_value(row, spec, field, context=None):
    if spec == "$row":return str(row.row_number), {"source_row":row.row_number}
    if spec == "$sheet":return row.sheet, {"source_sheet":row.sheet}
    if isinstance(spec, dict) and "value" in spec:
        return spec["value"], {"confirmed_value":spec["value"],"reason":spec.get("reason","")}
    fill_down=isinstance(spec,dict) and spec.get("fill_down",False)
    address=str(spec.get("column","") if isinstance(spec,dict) else spec).upper()
    if re.fullmatch(r"[A-Z]+",address): address+=str(row.row_number)
    cell=(context or row.cells).get(address,{})
    if fill_down and cell.get("raw_value") in (None,""):
        col=re.sub(r"\d+$","",address)
        for index in range(row.row_number-1,0,-1):
            candidate=(context or {}).get(col+str(index),{})
            if candidate.get("raw_value") not in (None,""):
                cell=candidate;address=col+str(index);break
    value=cell.get("normalized_value",cell.get("raw_value"))
    if field in ("document_no","product_no") and cell.get("display_value") is not None:value=cell["display_value"]
    if cell.get("validation_status") in ("cached_error","missing_cache","invalid_date"):
        s.fail(f"{address} 存在公式错误或缺失缓存，不能默认为零")
    if value is None or value=="": s.fail(f"{address} 缺少 {field}")
    if field=="business_date" and not re.match(r"^\d{4}-\d{2}-\d{2}",str(value)):
        try: value=from_excel(float(value)).date().isoformat()
        except (ValueError,OverflowError,TypeError): s.fail(f"{address} 日期必须确认年份，不能按文件名猜测")
    if field in NUMBERS:
        try:
            numeric=D(str(value))
            if not numeric.is_finite() or abs(numeric)>D('1e18'):raise ValueError('invalid number')
            value=str(numeric)
        except (ValueError,ArithmeticError):s.fail(f"{address} 不是有效历史数值")
    return str(value), {"cell":address,**cell}


def normalize(row, config, context=None):
    kind=config.get("kind")
    if kind not in KINDS:s.fail("请选择已支持的历史业务类型")
    values={"kind":kind}
    evidence={}
    for field,spec in config.get("fields",{}).items():
        if spec in (None,""):continue
        values[field],evidence[field]=cell_value(row,spec,field,context)
    for field in ("business_date","document_no"):
        if not values.get(field):s.fail("必须显式映射业务日期及单据/历史业务唯一编号")
    values["business_date"]=s.day(values["business_date"][:10])
    for field in ("document_no","customer","product_no","part_name","operation","source_line","unit","currency"):
        values[field]=str(values.get(field,"")).strip()
    if kind in ("receipt","report","shipment","order") and not all(values.get(k) for k in ("product_no","part_name","quantity","unit")):
        s.fail("生产数量必须明确货号、实体部件、数量与单位")
    if any(k in values for k in ("price","amount","wage","difference")) and values["currency"] not in ("HKD","CNY","USD"):
        s.fail("金额必须映射原币种")
    # Repeated source dates/lines are retained; only explicit business identity can link.
    key=digest({k:values.get(k,"") for k in IDENTITY})
    return values,evidence,key


def preview(db,factory,p):
    source=s.find(db,m.SprayImport,factory,p.get("import_id"))
    configs=p.get("sheets",[])
    if not isinstance(configs,list) or not configs or len(configs)>100:s.fail("请选择表页并设置映射")
    results=[]
    seen={}
    for config in configs:
        context={address:cell for item in db.scalars(select(m.SprayImportRow).where(m.SprayImportRow.import_id==source.id,m.SprayImportRow.sheet==config.get("sheet"))) for address,cell in item.cells.items()}
        query=select(m.SprayImportRow).where(m.SprayImportRow.import_id==source.id,m.SprayImportRow.sheet==config.get("sheet"),m.SprayImportRow.row_number>=int(config.get("start_row",1)),m.SprayImportRow.row_number<=int(config.get("end_row",1048576))).order_by(m.SprayImportRow.row_number)
        for row in db.scalars(query):
            variants=config.get("variants") or [{}]
            if not isinstance(variants,list) or len(variants)>366:s.fail("日期列映射最多 366 组")
            for index,variant in enumerate(variants):
                item={"row_id":row.id,"sheet":row.sheet,"row_number":row.row_number,"variant":index,"role":config.get("role","source")}
                if item["role"] not in ("source","comparison","ignore"):s.fail("表页角色无效")
                if item["role"]=="ignore":
                    results.append({**item,"decision":"ignored"});continue
                try:
                    values,evidence,key=normalize(row,{**config,"fields":{**config.get("fields",{}),**variant}},context)
                    old=s.find(db,m.SprayHistoryFact,factory,config["fact_id"]) if config.get("fact_id") else db.scalar(select(m.SprayHistoryFact).where(m.SprayHistoryFact.factory_id==factory,m.SprayHistoryFact.business_key==key,m.SprayHistoryFact.status=="active"))
                    existing=old.values if old else seen.get(key)
                    changes={k:{"previous":existing.get(k),"incoming":v} for k,v in values.items() if existing is not None and existing.get(k)!=v}
                    decision=("different" if changes else "linked") if existing is not None else "comparison_only" if item["role"]=="comparison" else "added"
                    if existing is None and item["role"]=="source":seen[key]=values
                    if old and old.business_key!=key:s.fail("指定关联的业务身份不一致，请修正映射而非强连")
                    results.append({**item,"values":values,"evidence":evidence,"business_key":key,"fact_id":old.id if old else None,"decision":decision,"differences":changes})
                except HTTPException as error:
                    results.append({**item,"decision":"pending","reason":str(error.detail)})
                if len(results)>20000:s.fail("本次映射超过 20,000 个业务事实，请分表分区预览")
    counts={key:sum(r["decision"]==key for r in results) for key in ("added","linked","different","pending","ignored","comparison_only")}
    return {"import_id":source.id,"sha256":source.sha256,"rows":results,"counts":counts,"fingerprint":digest(results),"stock_effect":0,"mode":"history"}


def apply(db,factory,actor,p):
    result=preview(db,factory,p)
    if p.get("fingerprint")!=result["fingerprint"]:s.fail("来源映射或历史业务版本已变化，请重新预览",409)
    reason=s.text(p.get("reason"),"执行厂区与历史归属确认依据",2000)
    chosen=set(p.get("selected",[]))
    approved=set(p.get("accept_differences",[]))
    counts=defaultdict(int)
    details=[]
    for row in result["rows"]:
        token=f'{row["row_id"]}:{row["variant"]}'
        if token not in chosen:continue
        decision=row["decision"]
        if decision in ("pending","ignored","comparison_only"):
            counts[decision]+=1; details.append({"token":token,"decision":decision,"reason":row.get("reason")});continue
        if decision=="different" and token not in approved and row["role"]!="comparison":
            counts["pending"]+=1;details.append({"token":token,"decision":"pending","reason":"差异尚未明确采用"});continue
        old=db.scalar(select(m.SprayHistoryFact).where(m.SprayHistoryFact.factory_id==factory,m.SprayHistoryFact.business_key==row["business_key"]))
        if old is None:
            v=row["values"]
            old=s.add(db,m.SprayHistoryFact,factory,actor,business_key=row["business_key"],values=v,**{k:v.get(k,"") for k in ("kind","business_date","document_no","customer","product_no","part_name")})
            outcome="added"
        elif old.values!=row["values"]:
            if row["role"]=="comparison":
                links=db.scalars(select(m.SprayHistoryLink).where(m.SprayHistoryLink.fact_id==old.id,m.SprayHistoryLink.import_row_id==row["row_id"],m.SprayHistoryLink.role=="comparison",m.SprayHistoryLink.status=="active"))
                if not any(link.snapshot.get("values")==row["values"] for link in links):
                    s.add(db,m.SprayHistoryLink,factory,actor,fact_id=old.id,import_row_id=row["row_id"],role="comparison",snapshot={"values":row["values"],"evidence":row["evidence"],"reason":reason,"version":old.revision})
                counts["comparison_difference"]+=1;details.append({"token":token,"decision":"comparison_difference","fact_id":old.id});continue
            if token not in approved:
                s.fail("同批导入出现不同金额/数量的重复身份，请拆开确认",409)
            if old.values.get("opening_ref"):
                s.fail("历史事实已引用为期初依据，须先登记期初差额，不能回改",409)
            old.values=row["values"];old.revision+=1;old.status="active";outcome="corrected"
        else:outcome="linked";old.status="active"
        link=db.scalar(select(m.SprayHistoryLink).where(m.SprayHistoryLink.fact_id==old.id,m.SprayHistoryLink.import_row_id==row["row_id"],m.SprayHistoryLink.status=="active"))
        if not link or link.snapshot.get("values")!=row["values"]:
            s.add(db,m.SprayHistoryLink,factory,actor,fact_id=old.id,import_row_id=row["row_id"],role=row["role"],snapshot={"values":row["values"],"evidence":row["evidence"],"reason":reason,"version":old.revision})
        counts[outcome]+=1;details.append({"token":token,"decision":outcome,"fact_id":old.id})
    source=s.find(db,m.SprayImport,factory,result["import_id"])
    retained={v['sheet']:v for v in (source.mapping or {}).get('sheets',[])}
    retained.update({v['sheet']:v for v in p['sheets']})
    source.mapping={"sheets":list(retained.values()),"reason":reason,"factory":factory,"mode":"history"};source.status="mapped"
    return {"id":source.id,"counts":dict(counts),"rows":details,"stock_effect":0}


def reverse(db,factory,actor,p):
    source=s.find(db,m.SprayImport,factory,p.get("import_id"))
    reason=s.text(p.get("reason"),"撤回依据",2000)
    links=list(db.scalars(select(m.SprayHistoryLink).join(m.SprayImportRow,m.SprayHistoryLink.import_row_id==m.SprayImportRow.id).where(m.SprayImportRow.import_id==source.id,m.SprayHistoryLink.status=="active")))
    affected={link.fact_id for link in links}
    for ident in affected:
        fact=s.find(db,m.SprayHistoryFact,factory,ident)
        if fact.values.get("opening_ref"):s.fail("此历史记录已关联期初库存，不能直接撤回；先登记有依据的库存差额",409)
    for link in links:
        link.status="reversed";link.snapshot={**link.snapshot,"reversal_reason":reason,"reversed_by":actor}
    db.flush()
    for ident in affected:
        fact=s.find(db,m.SprayHistoryFact,factory,ident)
        remaining=list(db.scalars(select(m.SprayHistoryLink).where(m.SprayHistoryLink.fact_id==ident,m.SprayHistoryLink.status=="active",m.SprayHistoryLink.role=="source").order_by(m.SprayHistoryLink.created_at,m.SprayHistoryLink.id)))
        fact.revision+=1
        if remaining:fact.values=remaining[-1].snapshot["values"]
        else:fact.status="reversed"
    source.status="reversed"
    return {"id":source.id,"reversed_links":len(links),"stock_effect":0}


def reconcile(db,factory,period=""):
    query=select(m.SprayHistoryFact).where(m.SprayHistoryFact.factory_id==factory,m.SprayHistoryFact.status=="active")
    if period:query=query.where(m.SprayHistoryFact.business_date.startswith(period))
    totals=defaultdict(lambda:{"quantity":D(0),"amount":D(0),"rows":0})
    facts=list(db.scalars(query))
    for fact in facts:
        key=(fact.kind,fact.values.get("currency",""),fact.values.get("unit",""))
        t=totals[key];t["rows"]+=1
        for field in ("quantity","amount"):t[field]+=D(fact.values.get(field,"0"))
    issues=[]
    for fact in facts:
        for link in db.scalars(select(m.SprayHistoryLink).where(m.SprayHistoryLink.fact_id==fact.id,m.SprayHistoryLink.status=="active",m.SprayHistoryLink.role=="comparison")):
            differences={k:{"source":fact.values.get(k),"comparison":v} for k,v in link.snapshot["values"].items() if fact.values.get(k)!=v}
            if differences:issues.append({"fact_id":fact.id,"document_no":fact.document_no,"differences":differences})
    return {"mode":"history","period":period,"coverage_dates":sorted({f.business_date for f in facts}),"totals":[{"kind":k[0],"currency":k[1],"unit":k[2],**{n:str(v) if isinstance(v,D) else v for n,v in t.items()}} for k,t in totals.items()],"differences":issues,"stock_effect":0}


def opening(db,factory,actor,p):
    cutover=s.day(p.get("cutover_date"));reason=s.text(p.get("reason"),"切换日盘点依据",2000)
    line=s.find(db,m.SprayOrderLine,factory,p.get("line_id"))
    refs=[s.find(db,m.SprayHistoryFact,factory,x) for x in p.get("history_ids",[])]
    if not refs or any(x.status!="active" or x.business_date>=cutover for x in refs):s.fail("期初必须引用切换日前已确认的历史事实")
    if any(x.product_no!=line.product_no or x.part_name!=line.part_name for x in refs):s.fail("期初依据必须对应同一货号及实体部件，不能挪用其他产品的历史余额")
    states=p.get("balances",{})
    if not isinstance(states,dict) or not states:s.fail("请逐状态填写实际盘点余额")
    from app.services.spray_advanced import eligible
    for state,qty in states.items():
        s.number(qty)
        if state not in ("finished","scrap","receipt-held","rejected") and not eligible(db,factory,line.id,state):s.fail("期初状态必须属于当前工艺版本")
    total=sum((s.number(q) for q in states.values()),D(0))
    if total<=0:s.fail("期初盘点合计必须大于零")
    if any(x.values.get("opening_ref") for x in refs):s.fail("历史依据已用于期初，不能重复建立库存",409)
    batch=s.add(db,m.SprayBatch,factory,actor,line_id=line.id,document_no=s.text(p.get("document_no"),"期初凭据",128),source_line="opening",business_date=cutover,received=total)
    for state,qty in states.items():s.move(db,factory,actor,batch.id,batch.id,"opening","",state,s.number(qty),reason)
    for fact in refs:fact.values={**fact.values,"opening_ref":batch.id,"cutover_date":cutover}
    return {"id":batch.id,"cutover_date":cutover,"stock_effect":str(total)}


def save_preference(db,factory,actor,p):
    kind=p.get("kind")
    if kind not in ("report_draft","schedule_draft","view","import_draft"):s.fail("草稿/视图类型无效")
    name=s.text(p.get("name"),"草稿名称",128)
    if not isinstance(p.get("payload"),dict) or len(json.dumps(p["payload"]))>2000000:s.fail("草稿内容无效或过大")
    old=db.scalar(select(m.SprayPreference).where(m.SprayPreference.factory_id==factory,m.SprayPreference.owner==actor,m.SprayPreference.kind==kind,m.SprayPreference.name==name))
    if old:
        changed=db.execute(update(m.SprayPreference).where(m.SprayPreference.id==old.id,m.SprayPreference.revision==p.get("expected_revision")).values(payload=p["payload"],revision=m.SprayPreference.revision+1))
        if changed.rowcount!=1:s.fail("另一窗口已更新草稿，请先恢复最新版本",409)
        db.refresh(old)
    else:
        if p.get("expected_revision") not in (None,0):s.fail("草稿不存在，请重新读取",409)
        old=s.add(db,m.SprayPreference,factory,actor,owner=actor,kind=kind,name=name,payload=p["payload"])
    return {"id":old.id,"preference_revision":old.revision}


def suggest_mapping(db,factory,import_id,sheet):
    source=s.find(db,m.SprayImport,factory,import_id)
    data=list(db.scalars(select(m.SprayImportRow).where(m.SprayImportRow.import_id==source.id,m.SprayImportRow.sheet==sheet).order_by(m.SprayImportRow.row_number)))
    header={}
    aliases={"business_date":["日期","送货日期","收货日期","接单日期","生产日期"],"document_no":["送货单号","单据号","订单号","订单号码","采购单号"],"product_no":["货号","产品编号","货号/货名"],"part_name":["名称","部件","品名","产品名称","货品名称","货物名称"],"quantity":["订单数","订单数量","数量","生产数","实际生产数","送货数量","收货数量"],"price":["单价","现价","实际工价"],"amount":["金额","总价","产值金额$","总金额"],"unit":["单位"],"customer":["客户","供应商","厂名","客名"],"wage":["实际总工资hk$/0.88","员工总工资"],"difference":["浪费工资"]}
    best=0
    for row in data[:12]:
        fields={}
        for address,cell in row.cells.items():
            label=re.sub(r"\s+","",str(cell.get("raw_value",""))).lower()
            for field,labels in aliases.items():
                if label in labels:fields[field]=re.sub(r"\d+","",address)
        if len(fields)>len(header):header=fields;best=row.row_number
    title=source.filename+sheet
    kind="order" if "接单" in title or "订单" in sheet else "purchase" if "采购" in title else "material" if "油漆" in title else "payroll" if "工资" in sheet else "report" if "日报" in sheet or "每天" in sheet else "returnable" if "胶箱" in sheet else "expense" if "收支" in title else "receipt" if "白件" in sheet else "shipment"
    role="comparison" if any(word in sheet for word in ("汇总","总表","总产值","请款","预算","月结")) else "source"
    required=[field for field in ("business_date","document_no","product_no","part_name","unit") if field not in header]
    return {"kind":kind,"role":role,"sheet":sheet,"start_row":best+1,"end_row":max((r.row_number for r in data),default=0),"fields":header,"pending_fields":required,"reason":"按原表表头提出候选；日期、厂区、部件及业务身份仍须显式核对"}
