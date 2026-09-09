"""Reviewed opening balances; source arrival totals never become opening stock."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal
from sqlalchemy import select

from app.models.carton_procurement import CartonCustomer, CartonOrder, CartonOrderLine, CartonInventoryMovement, CartonClosing
from app.models.carton_positions import CartonLocation, CartonPositionEntry
from app.services import carton_positions as positions
from app.services.carton_history_wide import date_value, number
from app.services.carton_procurement_imports import _cell, _header_mapping, _sheet_rows, _text
from app.services.carton_procurement import MAX_IMPORT_BYTES, _audit, _ensure_period_open, _lock_receipt_factory, get_active_customer_by_name, require_carton_factory
from app.schemas.carton_procurement import CartonHistoryInventoryImportOut


class OpeningOptions(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    customer_name: str=Field(min_length=1,max_length=255)
    warehouse: str=Field(min_length=1,max_length=64)
    snapshot_date: str
    dimension_unit: Literal["cm","in"]
    currency: Literal["CNY"]="CNY"


ALIASES={
    "contract_no":{"PO","合同号","合同号PO"},"item_no":{"货号","产品编号"},
    "paper":{"纸品／纸质","纸品/纸质","纸品纸质","纸质纸品","材质类型"},
    "packaging_type":{"纸品类型","纸箱类型"},"paper_quality":{"纸质","材质"},
    "length":{"长","长度","L"},"width":{"宽","宽度","W"},"height":{"高","高度","H"},
    "specification":{"规格","尺寸"},"unit":{"单位","纸品单位"},
    "location":{"仓位","库位"},"opening_quantity":{"期初库存数量","期初数量","结余","结余数量","库存结余"},
    "unit_price":{"单价","结余单价"},"opening_amount":{"原结余金额","结余金额","期初金额"},
    "document_no":{"来源单号","单据号","盘点单号"},"legacy_row_no":{"历史库存行号","原库存行号"},
    "note":{"备注","说明"},"ignored_inbound":{"入库箱","入库数量","入库箱数"},
    "ignored_amount":{"入库金额","原入库金额"},"ignored_date":{"日期","原日期","入库日期"},
    "customer_name":{"客户名称","客户"},"warehouse":{"仓库"},"snapshot_date":{"库存基准日期","盘点日期","库存日期"},
    "dimension_unit":{"尺寸单位","规格单位"},"currency":{"币种"},
}
PAPER_TYPES=("滑板纸","展示盒","外箱","内箱","平卡","刀卡","卡纸","卡")


def encoded(value): return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"),default=str)
def digest(value): return hashlib.sha256(encoded(value).encode()).hexdigest()
def normalize(value): return "".join(str(value or "").casefold().split())
def fail(source,message): raise HTTPException(422,detail=f"{source}：{message}")


def options_from_json(raw):
    try:
        options=OpeningOptions.model_validate(json.loads(raw) if isinstance(raw,str) else raw)
        options.snapshot_date=date_value(options.snapshot_date,0,"导入设置","库存基准日期",True)
        return options
    except (ValidationError,ValueError,TypeError) as exc:
        raise HTTPException(422,detail="请明确选择客户、仓库、完整库存基准日期和尺寸单位（cm/in），币种为CNY") from exc


def dimensions(spec):
    clean=re.sub(r"(?:cm|in|厘米|英寸)\s*$","",str(spec),flags=re.I).strip()
    parts=re.split(r"\s*[×xX*]\s*",clean)
    if len(parts) not in (2,3): return None
    try:
        values=tuple(Decimal(p) for p in parts)
        if any(not x.is_finite() for x in values): return None
        return values+(Decimal(0),) if len(values)==2 else values
    except Exception: return None


def parse_rows(filename,content,options):
    rows_out=[]; found=False; warnings=[]
    for sheet,rows,datemode in _sheet_rows(filename,content):
        if sheet.strip() in {"填写示例","字段说明"}: continue
        header=_header_mapping(rows,ALIASES)
        if not header: continue
        index,mapping=header
        if not {"item_no","opening_quantity","location"}.issubset(mapping):
            if any(any(_text(cell) for cell in row) for row in rows[:20]):
                fail(f"工作表“{sheet}”","未找到货号、结余/期初库存数量和仓位；入库箱数不能代替当前结余")
            continue
        found=True
        for rownum,row in enumerate(rows[index+1:],index+2):
            if not any(_text(_cell(row,mapping,key)) for key in ALIASES): continue
            source=f"“{sheet}”第 {rownum} 行"
            if len(rows_out)>=5000: fail("期初库存导入","单次最多5000行")
            for field in ("customer_name","warehouse","dimension_unit","currency"):
                cell=_text(_cell(row,mapping,field))
                if cell and normalize(cell)!=normalize(getattr(options,field)):
                    label={"customer_name":"客户","warehouse":"仓库","dimension_unit":"尺寸单位","currency":"币种"}[field]
                    fail(source,f"行内{label}与批次设置不一致，请分批导入，不能覆盖行内原值")
            row_date=_cell(row,mapping,"snapshot_date")
            if _text(row_date) and date_value(row_date,datemode,source,"库存基准日期",True)!=options.snapshot_date:
                fail(source,"行内库存基准日期与批次设置不一致")
            entry={key:_text(_cell(row,mapping,key)) for key in ("contract_no","item_no","packaging_type","paper_quality","location","document_no","legacy_row_no","note")}
            if not entry["item_no"]: fail(source,"货号不能为空")
            entry.update(source=source,source_sheet=sheet,source_row=rownum,customer_name=options.customer_name,
                snapshot_date=options.snapshot_date,currency=options.currency,dimension_unit=options.dimension_unit,warnings=[])
            quantity=number(_cell(row,mapping,"opening_quantity"),source,"期初库存数量")
            if quantity is None: fail(source,"期初库存数量不能为空，不能用入库箱数代替")
            if quantity>Decimal("99999999999999.9999") or quantity!=quantity.quantize(Decimal(".0001")):
                fail(source,"期初数量最多四位小数，且不能超过库存数量范围")
            entry["opening_quantity"]=quantity
            price=number(_cell(row,mapping,"unit_price"),source,"单价")
            if price is not None and (price>Decimal("999999999999.999999") or price!=price.quantize(Decimal(".000001"))):
                fail(source,"单价最多六位小数，且不能超过单价范围")
            entry["unit_price"]=price if price and price>0 else None
            if quantity==0:
                entry.update(status="ZERO",specification="",unit=_text(_cell(row,mapping,"unit")) or "个",amount=None)
                entry["warnings"].append("结余为0，本行不入账")
                rows_out.append(entry);continue
            if entry["unit_price"] is None:
                entry["warnings"].append("单价未核实，按待核价入账，不表示免费")
            combined=_text(_cell(row,mapping,"paper"))
            if not combined and not entry["packaging_type"] and any(entry["paper_quality"].endswith(kind) for kind in PAPER_TYPES):
                combined=entry["paper_quality"];entry["paper_quality"]=""
            if combined:
                types=[kind for kind in PAPER_TYPES if combined.endswith(kind)]
                if not types: fail(source,"纸品/纸质无法拆分，请单独填写纸品类型和纸质")
                kind=types[0];quality=combined[:-len(kind)].strip(" /／·-")
                if not quality: fail(source,"纸品/纸质缺少纸质")
                if (entry["packaging_type"] and entry["packaging_type"]!=kind) or (entry["paper_quality"] and entry["paper_quality"]!=quality):
                    fail(source,"合并纸品/纸质与独立字段不一致")
                entry.update(packaging_type=kind,paper_quality=quality)
            if not entry["packaging_type"] or not entry["paper_quality"]: fail(source,"请明确纸品类型与纸质")
            explicit_spec=_text(_cell(row,mapping,"specification"))
            dimension_values=None
            if any(_text(_cell(row,mapping,key)) for key in ("length","width","height")):
                vals=[number(_cell(row,mapping,key),source,label) for key,label in (("length","长"),("width","宽"),("height","高"))]
                if any(v is None for v in vals): fail(source,"长、宽、高均须填写，平卡高度可填0")
                dimension_values=tuple(vals)
            if explicit_spec:
                unit_match=re.search(r"(cm|in|mm|厘米|英寸|毫米)\s*$",explicit_spec,re.I)
                spec_unit={"厘米":"cm","英寸":"in"}.get(unit_match.group(1).lower(),unit_match.group(1).lower()) if unit_match else options.dimension_unit
                if spec_unit!=options.dimension_unit: fail(source,"规格中的尺寸单位与批次设置不一致")
                spec_values=dimensions(explicit_spec)
                if spec_values is None: fail(source,"规格须为长×宽×高，单位在导入设置中选择")
                if dimension_values and spec_values!=dimension_values: fail(source,"规格与长宽高不一致")
                dimension_values=spec_values
            if dimension_values is None or dimension_values[0]<=0 or dimension_values[1]<=0:
                fail(source,"请提供有效长宽高，长和宽须大于0")
            if any(value>100000 or value.as_tuple().exponent < -6 for value in dimension_values):
                fail(source,"尺寸数值过大或超过六位小数，请核实原表")
            if dimension_values[2]<0 or (dimension_values[2]==0 and entry["packaging_type"] in {"外箱","内箱","展示盒"}):
                fail(source,"箱类高度须大于0；平卡等平面纸品高度可为0")
            entry["specification"]=" × ".join(format(v.normalize(),"f") for v in dimension_values)+" "+options.dimension_unit
            entry["dimensions"]=dimension_values
            entry["unit"]=_text(_cell(row,mapping,"unit")) or ("个" if entry["packaging_type"] in {"外箱","内箱","展示盒"} else "张")
            if not _text(_cell(row,mapping,"unit")): entry["warnings"].append(f"纸品单位按{entry['packaging_type']}使用“{entry['unit']}”，请核对")
            if not entry["location"]: fail(source,"仓位不能为空，不清楚时请明确填写“待核仓位”")
            if max(len(entry[key]) for key in ("contract_no","item_no","paper_quality","location","document_no","legacy_row_no"))>128 or len(entry["packaging_type"])>64 or len(entry["unit"])>32 or len(entry["specification"])>255 or len(entry["note"])>2000:
                fail(source,"标识或纸品字段过长")
            entry["amount"]=(quantity*entry["unit_price"]).quantize(Decimal(".01"),rounding=ROUND_HALF_UP) if entry["unit_price"] is not None else None
            amount=number(_cell(row,mapping,"opening_amount"),source,"原结余金额")
            if amount is not None:
                if entry["amount"] is None: entry["warnings"].append("原结余金额缺少可核实单价，暂不用于估价或倒推单价")
                elif amount!=entry["amount"]: fail(source,"原结余金额与期初数量×单价不一致，请核实")
            if any(_text(_cell(row,mapping,key)) for key in ("ignored_inbound","ignored_amount","ignored_date")):
                entry["warnings"].append("原入库箱数、入库金额和原日期未计入期初；使用结余数量及批次库存基准日期")
            entry["status"]="READY";rows_out.append(entry)
            if len(rows_out)>5000: fail("期初库存导入","单次最多5000行")
    if not found or not rows_out: fail("期初库存导入","未找到可导入数据，请填写期初库存模板")
    return rows_out,warnings


def check_file(filename,content):
    if Path(filename).suffix.lower() not in {".xlsx",".xlsm",".xls"}: fail("文件","仅支持Excel文件")
    if not content: fail("文件","上传文件为空")
    if len(content)>MAX_IMPORT_BYTES: raise HTTPException(413,detail="期初库存文件不能超过20MB")


def semantic(row):
    return tuple(normalize(row[key]) for key in ("customer_code","contract_no","item_no","packaging_type","paper_quality","specification","unit","location_id"))


def _preview(db,factory,filename,content,options):
    locations=list(db.scalars(select(CartonLocation).where(CartonLocation.factory_id==factory)))
    customers=list(db.scalars(select(CartonCustomer).where(CartonCustomer.factory_id==factory)))
    movements=list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id==factory)))
    orders=list(db.scalars(select(CartonOrder).where(CartonOrder.factory_id==factory)))
    lines=list(db.scalars(select(CartonOrderLine).where(CartonOrderLine.factory_id==factory)))
    closings=list(db.scalars(select(CartonClosing).where(CartonClosing.factory_id==factory)))
    parts=list(db.scalars(select(CartonPositionEntry).where(CartonPositionEntry.factory_id==factory)))
    evidence={"version":1,"factory":factory,"file":hashlib.sha256(content).hexdigest(),"options":options.model_dump(),
        "customers":sorted((r.id,r.revision,r.customer_name,r.status) for r in customers),
        "locations":sorted((r.id,r.revision,r.warehouse,r.bin_code,r.status) for r in locations),
        "movements":sorted((r.id,str(r.quantity),str(r.unit_price),r.currency,r.source_line_id) for r in movements),
        "orders":sorted((r.id,r.revision,r.status) for r in orders),
        "parts":sorted((r.id,r.location_id,r.movement_id,str(r.quantity)) for r in parts),
        "closings":sorted((r.id,r.revision,r.status,r.period) for r in closings)}
    result={"factory_id":factory,"original_filename":filename,"source_fingerprint":digest(evidence),"row_count":0,
        "skipped_count":0,"missing_price_count":0,"rows":[],"warnings":[],"errors":[],"totals":[]}
    try:
        rows,warnings=parse_rows(filename,content,options)
        customer=get_active_customer_by_name(db,factory,options.customer_name)
    except HTTPException as exc:
        result["errors"].append(str(exc.detail));return result,[]
    result["row_count"]=len(rows);result["warnings"]=warnings
    warehouse=options.warehouse.strip().upper()
    scoped=[r for r in locations if r.warehouse.upper()==warehouse]
    if not scoped:
        result["errors"].append("所选仓库不存在，请先在基础资料中建立仓库及仓位")
    locations_by_id={r.id:r for r in locations};orders_by_id={r.id:r for r in orders}
    line_by_id={line.id:line for line in lines}
    parts_by_movement=defaultdict(list)
    for p in parts:
        if p.movement_id: parts_by_movement[p.movement_id].append(p)
    existing={}
    for movement in movements:
        if movement.source_type!="HISTORY_INVENTORY": continue
        allocations=parts_by_movement[movement.id]
        if len(allocations)!=1: continue
        saved={key:getattr(movement,key) for key in ("customer_code","contract_no","item_no","packaging_type","paper_quality","specification","unit")}
        saved["location_id"]=allocations[0].location_id
        linked=line_by_id.get(movement.order_line_id)
        if linked and linked.dimension_unit in {"cm","in"} and dimensions(linked.specification):
            saved["specification"]=" × ".join(format(v.normalize(),"f") for v in dimensions(linked.specification))+" "+linked.dimension_unit
        existing.setdefault(semantic(saved),[]).append(movement)
    seen={};prepared=[];totals={}
    for row in rows:
        row.update(customer_code=customer.customer_code,customer_name=customer.customer_name)
        if row["status"]=="ZERO":
            result["skipped_count"]+=1;result["rows"].append(row);continue
        try:
            if normalize(row["location"]) in {"待核仓位","未分仓位"}:
                candidates=[loc for loc in locations if loc.id==positions.unknown_id(factory) and loc.status=="ACTIVE"]
                row["warnings"].append("已明确指定系统待核仓位；实际位置核实后请调仓")
            else:
                label=row["location"].strip().upper()
                candidates=[loc for loc in scoped if loc.status=="ACTIVE" and label in {loc.bin_code.upper(),positions.label(loc).upper(),f"{loc.warehouse}/{loc.bin_code}".upper(),f"{loc.warehouse} / {loc.bin_code}".upper()}]
            if len(candidates)!=1: fail(row["source"],"仓位未唯一匹配所选仓库的启用仓位，请核对，系统不会自动建立或猜测仓位")
            loc=candidates[0];row.update(location_id=loc.id,location=positions.label(loc))
            canonical_spec=row["specification"]
            matches=[line for line in lines if line.customer_code==customer.customer_code and normalize(line.item_no)==normalize(row["item_no"])
                and row["contract_no"] and normalize(line.contract_no)==normalize(row["contract_no"])
                and line.packaging_type==row["packaging_type"] and line.paper_quality==row["paper_quality"] and line.unit==row["unit"]
                and line.dimension_unit==options.dimension_unit and dimensions(line.specification)==row["dimensions"]]
            key=semantic(row)
            source_line_id="CHI2-LINE-"+digest([factory,key,options.snapshot_date])[:48]
            row["source_line_id"]=source_line_id
            previous=existing.get(key,[])
            uncertain_openings=[movement for movement in movements if movement.source_type=="HISTORY_INVENTORY" and not movement.order_line_id
                and all(normalize(getattr(movement,field))==normalize(row[field]) for field in ("customer_code","contract_no","item_no","packaging_type","paper_quality","unit"))
                and dimensions(movement.specification)==row["dimensions"] and not re.search(r"(?:cm|in|厘米|英寸)\s*$",movement.specification,re.I)
                and any(part.location_id==loc.id for part in parts_by_movement[movement.id])]
            if uncertain_openings:
                fail(row["source"],"已有同纸品同数字规格的期初记录未明确尺寸单位，请先核实旧记录，不能猜测合并或再次入账")
            if previous:
                if len(previous)!=1: fail(row["source"],"已有多笔同库存身份的期初记录，请先核实，不能再次累计")
                saved=previous[0]
                same_date=str(saved.occurred_at)[:10]==options.snapshot_date
                same_value=saved.quantity==row["opening_quantity"] and saved.unit_price==(row["unit_price"] or Decimal(0)) and saved.currency==row["currency"]
                if not same_date or not same_value: fail(row["source"],"同一库存身份已有不同基准日、数量或价格的期初记录，请核实原单；不能覆盖或再次累计")
                row.update(status="DUPLICATE",existing_movement_id=saved.id)
                row["warnings"].append("相同库存身份及期初数值已入账，本次跳过")
                result["skipped_count"]+=1
            elif key in seen:
                old=seen[key]
                if old["opening_quantity"]!=row["opening_quantity"] or old["unit_price"]!=row["unit_price"]: fail(row["source"],"同一文件相同库存身份出现不同数量或单价，不能合并或静默丢弃")
                row["status"]="DUPLICATE";row["warnings"].append("与本文件前行相同，跳过重复期初")
                result["skipped_count"]+=1
            else:
                if any(c.status=="LOCKED" and c.customer_code==customer.customer_code and c.period>=options.snapshot_date[:7] for c in closings):
                    fail(row["source"],"基准日所在或后续月份已锁账，请先由主管核对锁账范围")
                seen[key]=row
            if len(matches)==1:
                row.update(order_line_id=matches[0].id,posting_specification=matches[0].specification)
                row["warnings"].append("按相同尺寸单位唯一关联正式纸品；仅恢复期初库存，不增加到货进度")
            else:
                row.update(order_line_id=None,posting_specification=canonical_spec)
                row["warnings"].append("未按相同尺寸单位唯一匹配订单，作为带明确尺寸单位的独立旧库存")
            if row["status"]=="READY":
                bucket=totals.setdefault((row["unit"],row["currency"]),{"unit":row["unit"],"currency":row["currency"],"quantity":Decimal(0),"amount":Decimal(0),"missing_price_count":0})
                bucket["quantity"]+=row["opening_quantity"]
                if row["amount"] is None:
                    result["missing_price_count"]+=1;bucket["missing_price_count"]+=1
                else: bucket["amount"]+=row["amount"]
                prepared.append(row)
            result["rows"].append(row)
        except HTTPException as exc: result["errors"].append(str(exc.detail))
    for bucket in totals.values():
        if bucket["missing_price_count"]: bucket["amount"]=None
    result["totals"]=list(totals.values())
    return json.loads(encoded(result)),prepared


def preview_opening_inventory(db,factory_id,filename,content,options):
    factory=require_carton_factory(factory_id);filename=Path(filename or "").name
    check_file(filename,content);options=options_from_json(options)
    return _preview(db,factory,filename,content,options)[0]


def import_opening_inventory(db,factory_id,filename,content,user,options,expected_preview_fingerprint):
    factory=require_carton_factory(factory_id);filename=Path(filename or "").name
    check_file(filename,content);options=options_from_json(options)
    if not expected_preview_fingerprint: raise HTTPException(409,detail="简化期初库存请先预览核对，再确认入账")
    try:
        _lock_receipt_factory(db,factory)
        preview,prepared=_preview(db,factory,filename,content,options)
        if preview["errors"]: raise HTTPException(422,detail="；".join(preview["errors"]))
        duplicate=not prepared and any(row["status"]=="DUPLICATE" for row in preview["rows"])
        if expected_preview_fingerprint!=preview["source_fingerprint"] and not duplicate:
            raise HTTPException(409,detail="文件、导入设置、客户、仓位、订单或库存已变化，请重新预览")
        source_hash=digest({"file":hashlib.sha256(content).hexdigest(),"options":options.model_dump()})
        source_id="CHI2-"+source_hash[:32]
        ids=[];matched=0;total=Decimal(0)
        for row in prepared:
            occurred_at=options.snapshot_date+"T00:00:00+08:00"
            _ensure_period_open(db,factory,row["customer_code"],occurred_at)
            movement=CartonInventoryMovement(id="CIM-"+uuid4().hex,factory_id=factory,
                order_line_id=row["order_line_id"],customer_code=row["customer_code"],customer_name=row["customer_name"],
                contract_no=row["contract_no"],item_no=row["item_no"],packaging_type=row["packaging_type"],paper_quality=row["paper_quality"],
                specification=row["posting_specification"],movement_type="ADJUSTMENT",quantity=row["opening_quantity"],unit=row["unit"],
                unit_price=row["unit_price"] or Decimal(0),currency=row["currency"],location=row["location"],
                document_no=row["document_no"] or "OPEN-"+options.snapshot_date+"-"+row["source_line_id"][-8:],
                source_type="HISTORY_INVENTORY",source_id=source_id,source_line_id=row["source_line_id"],
                reversal_of_movement_id=None,reason=row["note"] or "期初库存结余导入",actor_user_id=user.id,actor_name=user.display_name,occurred_at=occurred_at)
            positions.post(db,movement,location_id=row["location_id"])
            ids.append(movement.id);matched+=bool(row["order_line_id"]);total+=row["opening_quantity"]
        if ids:
            _audit(db,user,factory,"HISTORY_INVENTORY_IMPORTED","carton_inventory_import",source_id,
                {"filename":filename,"source_sha256":source_hash,"options":options.model_dump(),"row_count":preview["row_count"],
                 "imported_count":len(ids),"skipped_count":preview["skipped_count"],"missing_price_count":preview["missing_price_count"],
                 "totals":preview["totals"],"source_fingerprint":expected_preview_fingerprint,
                 "rows":json.loads(encoded([{**{key:row.get(key) for key in ("source","source_sheet","source_row","legacy_row_no","document_no",
                    "customer_code","contract_no","item_no","packaging_type","paper_quality","specification","dimension_unit","unit",
                    "opening_quantity","unit_price","amount","currency","location","location_id","source_line_id","note")},
                    "movement_id":movement_id} for row,movement_id in zip(prepared,ids,strict=True)]))})
        db.commit()
        return CartonHistoryInventoryImportOut(factory_id=factory,original_filename=filename,row_count=preview["row_count"],
            imported_count=len(ids),skipped_count=preview["skipped_count"],matched_order_line_count=matched,
            standalone_count=len(ids)-matched,total_quantity=total,duplicate=duplicate,
            movement_ids=ids or [row["existing_movement_id"] for row in preview["rows"] if row.get("existing_movement_id")],
            warnings=preview["warnings"]+[f"{row['source']}：{warning}" for row in preview["rows"] for warning in row["warnings"]])
    except Exception:
        db.rollback();raise
