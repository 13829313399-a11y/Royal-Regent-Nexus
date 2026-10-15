"""Exact, audited supplier names resolve to stable IDs, never fuzzy matches."""
import json
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.models.fabric_master import FabricMasterChange, FabricMasterRecord
from app.models.material_handover import HandoverSupplierBinding

FACTORY = 'huakang-c'


def supplier_aliases(db):
    aliases = defaultdict(set)
    tables = set(inspect(db.get_bind()).get_table_names())
    if FabricMasterRecord.__tablename__ not in tables:
        return aliases
    suppliers = list(db.scalars(select(FabricMasterRecord).where(
        FabricMasterRecord.factory_id == FACTORY, FabricMasterRecord.kind == 'SUPPLIER')))
    ids = {row.id for row in suppliers}
    for row in suppliers:
        aliases[row.name].add(row.id)
    if FabricMasterChange.__tablename__ in tables:
        for row in db.scalars(select(FabricMasterChange).where(FabricMasterChange.factory_id == FACTORY)):
            if row.record_id in ids:
                for value in (row.before_json, row.after_json):
                    name = json.loads(value).get('name')
                    if name:
                        aliases[name].add(row.record_id)
    if HandoverSupplierBinding.__tablename__ in tables:
        for row in db.scalars(select(HandoverSupplierBinding).where(HandoverSupplierBinding.factory_id == FACTORY)):
            name = json.loads(row.supplier_snapshot_json).get('name')
            if name and row.supplier_id in ids:
                aliases[name].add(row.supplier_id)
    return aliases


def receipt_supplier(db, name):
    ids = supplier_aliases(db).get(name, set())
    if len(ids) > 1:
        raise HTTPException(422, '该名称对应多个供应商，请负责人核对基础资料及原单归属后再收料')
    supplier = db.get(FabricMasterRecord, next(iter(ids))) if ids else None
    if supplier and supplier.status == 'INACTIVE':
        raise HTTPException(422, '该供应商资料已停用，请负责人核对后再收料')
    return supplier
