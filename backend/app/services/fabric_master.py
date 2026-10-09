"""Confirmed master data; source candidates remain drafts until a person saves them."""
import json
from collections import defaultdict
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import inspect, select
from app.core.time import business_now
from app.models.fabric_master import FabricMasterRecord, FabricMasterChange
from app.models.fabric_procurement import FabricProcurementLine
from app.services import fabric_procurement as source
from app.services.fabric_procurement_parser import digest, dump


def ready(db):
    return {"fabric_master_records", "fabric_master_changes", "fabric_chase_resolutions"} <= set(inspect(db.get_bind()).get_table_names())


def ensure_schema(db):
    source.ensure_schema(db)
    if not ready(db):
        raise HTTPException(503, "布料仓基础资料尚未升级，请先备份并执行迁移 20261008_0143")


def record_data(record):
    return {"id": record.id, "kind": record.kind, "code": record.code, "name": record.name,
            "status": record.status, "revision": record.revision, "data": json.loads(record.data_json), "updated_at": record.updated_at}


def records(db):
    if not ready(db):
        return []
    return list(db.scalars(select(FabricMasterRecord).where(FabricMasterRecord.factory_id == source.FACTORY)))


def list_records(db, kind, search="", status="ALL", sort="CODE"):
    ensure_schema(db)
    needle = search.strip().casefold()
    all_records = records(db)
    items = [record_data(row) for row in all_records if row.kind == kind and (status == "ALL" or row.status == status)
             and (not needle or needle in (row.code + row.name + row.data_json).casefold())]
    items.sort(key=lambda row: (row["name" if sort == "NAME" else "code"].casefold(), row["id"]))
    if sort == "UPDATED":
        items.sort(key=lambda row: row["updated_at"], reverse=True)
    return {"items": items, "total": len(items), "warehouse_tokens": warehouse_tokens(all_records) if kind == "LOCATION" else {}}


def warehouse_tokens(all_records):
    groups = defaultdict(list)
    for row in all_records:
        if row.kind == "LOCATION":
            groups[json.loads(row.data_json).get("warehouse", "")].append([row.id, row.revision])
    return {name: digest([source.FACTORY, name, sorted(rows)]) for name, rows in groups.items()}


def candidates(db, kind):
    ensure_schema(db)
    known = {(row.kind, row.code) for row in records(db)}
    known_suppliers = {row.name for row in records(db) if row.kind == "SUPPLIER"}
    groups = defaultdict(list)
    for line in db.scalars(select(FabricProcurementLine).where(FabricProcurementLine.factory_id == source.FACTORY, FabricProcurementLine.status != "WITHDRAWN")):
        facts = json.loads(line.payload_json)
        key = facts.get({"MATERIAL": "material_code", "SUPPLIER": "supplier", "UNIT": "unit"}.get(kind, ""))
        if key:
            groups[key].append((line.id, facts))
    items = []
    for key, rows in sorted(groups.items()):
        if (kind, key) in known or (kind == "SUPPLIER" and key in known_suppliers):
            continue
        variants = sorted({(facts["material_name"], facts["unit"]) for _, facts in rows}) if kind == "MATERIAL" else []
        facts = rows[0][1]
        items.append({"key": digest([kind, key]), "kind": kind, "code": "" if kind == "SUPPLIER" else key,
            "name": facts["material_name"] if kind == "MATERIAL" else key, "status": "DRAFT", "revision": 0,
            "data": {"unit": facts["unit"], "old_code": facts.get("old_material_code", "")} if kind == "MATERIAL" else {},
            "variants": [{"name": name, "unit": unit} for name, unit in variants], "conflict": len(variants) > 1,
            "source_line_ids": [line_id for line_id, _ in rows], "source_count": len(rows)})
    return {"items": items, "stock_posted": False}


def save(db, actor, payload):
    ensure_schema(db)
    body = payload.model_dump(mode="json")
    request_hash = digest([actor.id, body])
    state = source.lock_factory(db)
    previous = db.scalar(select(FabricMasterChange).where(FabricMasterChange.factory_id == source.FACTORY, FabricMasterChange.request_id == str(payload.request_id)))
    if previous:
        if previous.request_hash != request_hash:
            raise HTTPException(409, "该请求已用于其他资料或账号，请刷新资料核对")
        db.rollback()
        return json.loads(previous.after_json)
    record = db.scalar(select(FabricMasterRecord).where(FabricMasterRecord.factory_id == source.FACTORY, FabricMasterRecord.id == payload.id)) if payload.id else None
    if payload.id and not record:
        raise HTTPException(404, "找不到该厂区的基础资料")
    if payload.expected_revision != (record.revision if record else 0) or (record and record.kind != payload.kind):
        raise HTTPException(409, "基础资料已变化，请刷新后修改")
    if record and record.code != payload.code:
        raise HTTPException(422, "资料编码创建后不能修改，请停用原资料并另建新编码")
    duplicate = db.scalar(select(FabricMasterRecord).where(FabricMasterRecord.factory_id == source.FACTORY, FabricMasterRecord.kind == payload.kind,
        FabricMasterRecord.code == payload.code, FabricMasterRecord.id != (payload.id or "")))
    if duplicate:
        raise HTTPException(409, "该分类的编码已存在，请修改现有资料")
    if payload.kind == "LOCATION" and any(row.kind == "LOCATION" and row.id != (payload.id or "")
            and row.code.casefold() == payload.code.casefold() for row in records(db)):
        raise HTTPException(409, "仓位编码已存在（不区分大小写），请修改现有仓位")
    if payload.kind == "SUPPLIER" and db.scalar(select(FabricMasterRecord.id).where(FabricMasterRecord.factory_id == source.FACTORY,
        FabricMasterRecord.kind == "SUPPLIER", FabricMasterRecord.name == payload.name, FabricMasterRecord.id != (payload.id or ""))):
        raise HTTPException(409, "供应商名称已存在，请修改现有资料")
    fields = body["data"]
    if record and payload.kind == "LOCATION" and json.loads(record.data_json).get("warehouse") and fields.get("warehouse") != json.loads(record.data_json).get("warehouse"):
        raise HTTPException(422, "仓位不能直接改换所属仓库；实物移动请调仓，仓库改名请使用整仓更名")
    if payload.kind == "UNIT" and not fields["ratio"]:
        for existing in records(db):
            if existing.kind == "UNIT" and existing.id != (payload.id or "") and not json.loads(existing.data_json).get("ratio") and {payload.code, payload.name} & {existing.code, existing.name}:
                raise HTTPException(409, "标准单位的编码或名称与现有单位重叠，请修改现有单位")
    allowed = {"MATERIAL": {"category", "unit", "old_code", "spec", "color", "composition", "note"},
               "SUPPLIER": {"contact", "phone", "note"}, "LOCATION": {"warehouse", "note"},
               "UNIT": {"unit", "material_code", "price_unit", "ratio", "evidence", "conditions", "effective_date", "note"}}[payload.kind]
    if any(value and key not in allowed for key, value in fields.items()):
        raise HTTPException(422, "包含不属于当前资料类型的字段")
    if payload.status == "ACTIVE":
        if payload.kind == "MATERIAL" and (not fields["category"] or not fields["unit"]):
            raise HTTPException(422, "启用物料须确认分类和库存单位")
        if payload.kind == "LOCATION" and not fields["warehouse"]:
            raise HTTPException(422, "启用仓位须填写所属仓库")
    if payload.kind == "UNIT" and fields["ratio"]:
        from app.services.fabric_receiving import quantity
        fields["ratio"] = str(quantity(fields["ratio"], "单位换算系数"))
        if not all(fields[key] for key in ("material_code", "unit", "price_unit", "evidence", "conditions", "effective_date")) or fields["unit"] == fields["price_unit"]:
            raise HTTPException(422, "换算须指定物料、两种不同单位、系数依据、适用条件及生效日期")
        if not any(row.kind == "MATERIAL" and row.code == fields["material_code"] and row.status == "ACTIVE" for row in records(db)):
            raise HTTPException(422, "请先启用换算对应的物料资料")
    before = record_data(record) if record else {}
    now = business_now().isoformat()
    if not record:
        record = FabricMasterRecord(id=uuid4().hex, factory_id=source.FACTORY, kind=payload.kind, code=payload.code, revision=0)
        db.add(record)
    record.name, record.status, record.data_json, record.updated_at = payload.name, payload.status, dump(fields), now
    record.revision += 1
    db.flush()
    result = record_data(record)
    db.add(FabricMasterChange(id=uuid4().hex, factory_id=source.FACTORY, record_id=record.id, request_id=str(payload.request_id), request_hash=request_hash,
        before_json=dump(before), after_json=dump(result), actor_id=actor.id, actor_name=actor.display_name, occurred_at=now))
    state.revision += 1
    db.commit()
    return result


def history(db, record_id):
    ensure_schema(db)
    if not any(row.id == record_id for row in records(db)):
        raise HTTPException(404, "找不到该厂区的基础资料")
    return {"items": [{"before": json.loads(row.before_json), "after": json.loads(row.after_json), "actor_name": row.actor_name, "occurred_at": row.occurred_at}
        for row in db.scalars(select(FabricMasterChange).where(FabricMasterChange.factory_id == source.FACTORY,
            FabricMasterChange.record_id == record_id).order_by(FabricMasterChange.occurred_at.desc(), FabricMasterChange.id))]}


def material_info(facts, all_records):
    item = next((row for row in all_records if row.kind == "MATERIAL" and row.code == facts["material_code"]), None)
    if not item:
        return {"material_category": None, "master_material": None, "master_material_matches": False}
    data = record_data(item)
    matches = item.name == facts["material_name"] and data["data"].get("unit") == facts["unit"]
    return {"material_category": data["data"].get("category") if item.status == "ACTIVE" and matches else None, "master_material": data, "master_material_matches": matches}


def receipt_references(db, facts, payload):
    all_records = records(db)
    material = material_info(facts, all_records)
    if material["master_material"] and material["master_material"]["status"] == "INACTIVE":
        raise HTTPException(422, "该物料资料已停用，请负责人核对后再收料")
    if material["material_category"] and material["material_category"] != payload.material_category:
        raise HTTPException(422, "物料分类与已确认基础资料不同，请刷新并核对资料")
    supplier = next((row for row in all_records if row.kind == "SUPPLIER" and row.name == facts["supplier"]), None)
    if supplier and supplier.status == "INACTIVE":
        raise HTTPException(422, "该供应商资料已停用，请负责人核对后再收料")
    unit = next((row for row in all_records if row.kind == "UNIT" and not json.loads(row.data_json).get("ratio") and facts["unit"] in (row.code, row.name)), None)
    if unit and unit.status == "INACTIVE":
        raise HTTPException(422, "该单位资料已停用，请负责人核对后再收料")
    from app.services.warehouse_locations import resolve
    by_id = {row.id: row for row in all_records}
    bins = []
    for batch in payload.batches:
        resolved = resolve(db, 'fabric', batch.location_id)
        bins.append({**record_data(by_id[resolved['id']]), **resolved})
    return {"material": material["master_material"] if material["master_material_matches"] and material["material_category"] else None,
            "supplier": record_data(supplier) if supplier and supplier.status == "ACTIVE" else None,
            "unit": record_data(unit) if unit and unit.status == "ACTIVE" else None, "locations": bins}
