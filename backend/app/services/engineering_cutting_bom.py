"""Publish an explicit cutting projection of one approved engineering BOM."""
import json
from fractions import Fraction
from uuid import uuid4

from fastapi import HTTPException
from pydantic import Field, ValidationError
from sqlalchemy import select

from app.models.cutting_ops import CuttingMaster, CuttingRevision
from app.models.engineering_bom import EngineeringEvent
from app.services import cutting_ops as cutting, cutting_schemas as schema
from app.services import engineering_bom as engineering, fabric_procurement
from app.services.engineering_bom_comparison import evidence
from app.services.transaction_lock import lock_transaction


class MaterialSelection(schema.Strict):
    key: str = Field(min_length=1, max_length=128)
    part_keys: list[str] = Field(min_length=1, max_length=200)
    required_for_cutting: bool


class Selection(schema.Strict):
    source_version: int = Field(ge=1)
    style: schema.Text
    color: schema.Text
    part_keys: list[str] = Field(min_length=1, max_length=200)
    materials: list[MaterialSelection] = Field(min_length=1, max_length=300)


class Publish(schema.Command):
    selection: Selection
    token: str = Field(pattern=r'^[0-9a-f]{64}$')


def approved_source(db, identity, version):
    document = engineering.document(db, identity)
    cutting.require(document.effective_version == version, '工程有效版本已变化，请重新读取', 409)
    event = db.scalar(select(EngineeringEvent).where(
        EngineeringEvent.factory_id == engineering.FACTORY, EngineeringEvent.entity_id == identity,
        EngineeringEvent.version == version, EngineeringEvent.action == 'bom_approve',
    ))
    cutting.require(event is not None, '工程 BOM 审核版本缺失', 409)
    saved = json.loads(event.result_json)
    cutting.require(saved.get('status') == 'APPROVED', '仅可使用已审核的工程 BOM', 409)
    return saved, dict(bom_id=identity, version=version, item_no=saved['data']['item_no'],
                       event_id=event.id, actor_id=event.actor_id, occurred_at=event.occurred_at)


def master(db, identity):
    return db.scalar(select(CuttingMaster).where(
        CuttingMaster.factory_id == cutting.FACTORY, CuttingMaster.kind == 'bom',
        CuttingMaster.code == 'ENG-' + identity,
    ))


def mapped_revision(db, item, source):
    if item is None:
        return None
    revisions = db.scalars(select(CuttingRevision).where(
        CuttingRevision.master_id == item.id).order_by(CuttingRevision.version.desc()))
    for revision in revisions:
        origin = revision.data.get('engineering_source', {})
        cutting.require(origin.get('bom_id') == source['bom_id'], '裁床执行 BOM 编码已被其他资料使用', 409)
        if origin['version'] == source['version']:
            return cutting.view(db, item, revision.version)
    return None


def choices(db, identity, version):
    saved, source = approved_source(db, identity, version)
    rows = []
    for key, row in evidence(saved).items():
        if not row['parent']:
            continue
        amount = Fraction(row['cumulative'])
        rows.append(dict(key=key, row=row['position'], name=row['name'], code=row['code'],
                         process=row['process'], path=row['path'], quantity=str(amount), unit=row['unit'],
                         can_be_part=row['unit'] in {'片', '件'} and amount.denominator == 1
                         and 1 <= amount.numerator <= 100000))
    item = master(db, identity)
    existing = mapped_revision(db, item, source)
    return dict(source=source, name=saved['data']['name'], rows=rows, existing=existing)


def cutting_material(db, saved, row):
    key = f"{row['material_id']}:{row['material_version']}"
    snapshot = saved['materials'].get(key)
    label = f"工程第 {row['position']} 行 {row['code']}"
    cutting.require(snapshot, f'{label}缺少审核物料快照', 422)
    original = snapshot['data']
    category = {'FABRIC': 'fabric', 'ACCESSORY': 'accessory', 'THREAD': 'accessory'}.get(original.get('category'))
    cutting.require(category, f'{label}未确认布料或辅料类别', 422)
    current = engineering.material_view(engineering.material(db, snapshot['id']))
    cutting.require(current['status'] == 'ACTIVE' and current['data'].get('engineering', {}).get('approval') == 'APPROVED'
                    and current['code'] == row['code']
                    and all(current['data'].get(field, '') == original.get(field, '') for field in ('unit', 'spec', 'color', 'category')),
                    f'{label}工程物料状态、单位、规格、颜色或类别已变化，请重新审核工程 BOM', 409)
    item = db.scalar(select(CuttingMaster).where(
        CuttingMaster.factory_id == cutting.FACTORY, CuttingMaster.kind == 'material', CuttingMaster.code == row['code']))
    cutting.require(item, f'{label}缺少同编码的裁床物料，请先核对基础资料', 422)
    ref = cutting.view(db, item)
    data = ref['data']
    cutting.require(ref['status'] == 'active' and data['category'] == category and data['unit'] == row['unit']
                    and data.get('specification', '') == original.get('spec', '') and data.get('color', '') == original.get('color', ''),
                    f'{label}与裁床物料的状态、类别、单位、规格或颜色不一致', 422)
    return ref


def projection(db, identity, selection):
    saved, source = approved_source(db, identity, selection.source_version)
    item = master(db, identity)
    cutting.require(not mapped_revision(db, item, source), '该工程版本已有裁床执行 BOM，请使用已发布版本', 409)
    rows = evidence(saved)
    part_keys = set(selection.part_keys)
    material_keys = {m.key for m in selection.materials}
    cutting.require(len(part_keys) == len(selection.part_keys) and len(material_keys) == len(selection.materials)
                    and not part_keys & material_keys, '同一工程行只能选用一次', 422)
    cutting.require(all(rows.get(key, {}).get('parent') for key in part_keys | material_keys),
                    '只能选用本工程版本的非成品行', 422)
    parts, codes, part_sources = [], {}, []
    for key, row in rows.items():
        if key not in part_keys:
            continue
        amount = Fraction(row['cumulative'])
        cutting.require(row['unit'] in {'片', '件'} and amount.denominator == 1 and 1 <= amount <= 100000,
                        f"工程第 {row['position']} 行无法按整数片数核套，请核对工程单位和配比", 422)
        code = f"P-{row['position']:03d}"
        codes[key] = code
        parts.append(dict(code=code, name=row['name'], pieces_per_set=amount.numerator))
        part_sources.append(dict(code=code, key=key, row=row['position']))
    requirements, material_sources = [], []
    by_key = {m.key: m for m in selection.materials}
    for key, row in rows.items():
        chosen = by_key.get(key)
        if not chosen:
            continue
        cutting.require(set(chosen.part_keys) <= part_keys and len(set(chosen.part_keys)) == len(chosen.part_keys),
                        f"请核对工程第 {row['position']} 行的适用裁片", 422)
        amount = Fraction(row['cumulative'])
        scaled, remainder = divmod(amount.numerator * 1000000, amount.denominator)
        cutting.require(scaled > 0 and not remainder, f"工程第 {row['position']} 行用量超出裁床精度，须核对原依据", 422)
        ref = cutting_material(db, saved, row)
        requirements.append(dict(material_id=ref['id'], material_version=ref['version'],
                                 part_codes=[codes[k] for k in codes if k in chosen.part_keys],
                                 quantity_per_set=f'{scaled // 1000000}.{scaled % 1000000:06d}', unit=row['unit'],
                                 required_for_cutting=chosen.required_for_cutting, stage=row['process']))
        material_sources.append(dict(key=key, row=row['position'], code=ref['code'], name=ref['data']['name'],
                                     material_id=row['material_id'], material_version=row['material_version'],
                                     path_keys=row['path_keys']))
    try:
        data = schema.Bom.model_validate(dict(
            name=saved['data']['name'], item_no=source['item_no'], style=selection.style, color=selection.color,
            source_reference=f'工程 BOM {identity} V{source["version"]}', parts=parts, requirements=requirements,
        )).model_dump(mode='json')
    except ValidationError as exc:
        raise HTTPException(422, '工程货号、名称、工序或用量超出裁床执行资料范围，请核对') from exc
    cutting.validate_references(db, data, publishing=True)
    data['engineering_source'] = source | dict(parts=part_sources, materials=material_sources)
    return item, data


def preview(db, identity, selection):
    item, data = projection(db, identity, selection)
    version = item.version if item else 0
    return dict(data=data, expected_version=version, token=cutting.payload_fingerprint(
        dict(data=data, expected_version=version), 'engineering-projection'))


def publish(db, user, identity, body):
    lock_transaction(db, 'engineering-bom', engineering.FACTORY)

    def apply():
        # Match the established cutting -> fabric order used by issue/receipt.
        fabric_procurement.lock_factory(db)
        result = preview(db, identity, body.selection)
        cutting.require(body.expected_version == result['expected_version'] and body.token == result['token'],
                        '工程或裁床依据已变化，请重新预览确认')
        item = master(db, identity)
        if item is None:
            item = CuttingMaster(id=str(uuid4()), factory_id=cutting.FACTORY, kind='bom', code='ENG-' + identity, version=0)
            db.add(item)
        return cutting.append(db, user, item, result['data'], 'published', body.reason)

    return cutting.command(db, user, body, 'engineering-projection:' + identity, apply)
