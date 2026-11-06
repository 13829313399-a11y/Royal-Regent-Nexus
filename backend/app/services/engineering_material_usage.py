"""Current engineering references only; no order, stock or procurement projection."""
import json
from sqlalchemy import or_, select
from app.core.time import business_now
from app.services import engineering_bom as bom
from app.services.transaction_lock import lock_transaction


def read(db, identity, expected_version):
    lock_transaction(db, 'engineering-bom', bom.FACTORY)
    material = bom.material_view(bom.material(db, identity))
    bom.require(material['data'].get('engineering') and material['code'].startswith(('01-', '02-', '03-', '04-')),
                '请先将物料纳入工程档案', 422)
    bom.require(material['version'] == expected_version, '物料已变化，请刷新资料后重新打开 BOM 引用')
    documents = list(db.scalars(select(bom.EngineeringBom).where(bom.EngineeringBom.factory_id == bom.FACTORY)))
    wanted = {(r.id, v) for r in documents for v in (r.version, r.effective_version) if v is not None}
    events = db.scalars(select(bom.EngineeringEvent).join(bom.EngineeringBom,
        bom.EngineeringEvent.entity_id == bom.EngineeringBom.id).where(
            bom.EngineeringBom.factory_id == bom.FACTORY, bom.EngineeringEvent.factory_id == bom.FACTORY,
            bom.EngineeringEvent.action.in_(('bom_write', 'bom_approve')),
            or_(bom.EngineeringEvent.version == bom.EngineeringBom.version,
                bom.EngineeringEvent.version == bom.EngineeringBom.effective_version)))
    snapshots = {(e.entity_id, e.version): json.loads(e.result_json) for e in events}
    bom.require(wanted == snapshots.keys(), 'BOM 当前版本依据缺失，无法完整查询引用')
    items = []
    for document in sorted(documents, key=lambda r: (r.item_no, r.id)):
        for version in sorted({v for v in (document.version, document.effective_version) if v is not None}, reverse=True):
            saved = snapshots[(document.id, version)]
            bom.require(saved['id'] == document.id and saved['version'] == version, 'BOM 版本依据不一致，无法查询引用')
            roles = (['LATEST'] if version == document.version else []) + (['EFFECTIVE'] if version == document.effective_version else [])
            for row, node in enumerate(saved['data']['nodes'], 1):
                if node['material_id'] != identity:
                    continue
                frozen = saved['materials'].get(f"{identity}:{node['material_version']}")
                bom.require(frozen is not None, 'BOM 历史物料依据缺失，无法完整查询引用')
                items.append(dict(bom_id=document.id, bom_version=version, item_no=saved['data']['item_no'],
                    bom_name=saved['data']['name'], status=saved['status'], roles=roles, row=row, key=node['key'],
                    material_version=node['material_version'], code=frozen['code'], name=frozen['name'],
                    attribute=frozen['data'].get('engineering', {}).get('attribute', ''), process=node['process'],
                    unit=node['unit'], numerator=node['numerator'], denominator=node['denominator']))
    return dict(material_id=identity, material_version=material['version'], code=material['code'], name=material['name'],
                checked_at=business_now().isoformat(), bom_count=len({i['bom_id'] for i in items}), items=items)
