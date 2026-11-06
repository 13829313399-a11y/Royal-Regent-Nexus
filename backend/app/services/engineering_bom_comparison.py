"""Read-only comparison of immutable versions of one engineering BOM."""
from fractions import Fraction
import json
from sqlalchemy import select
from app.services import engineering_bom as bom

LABELS = {'position': '表内行序', 'parent': '上级行', 'path': '层级路径', 'material_id': '物料身份',
    'material_version': '物料版本', 'code': '物料编码', 'name': '物料名称', 'attribute': '物料属性',
    'specification': '物料规格', 'color': '颜色', 'department': '负责部门', 'unit': '单位', 'process': '工序',
    'numerator': '用量分子', 'denominator': '用量分母', 'exempt_loss': '免损', 'note': '备注',
    'review_required': '需核对', 'review_note': '核对说明', 'cumulative': '沿路径单套用量'}


def evidence(saved):
    nodes = bom.validate_tree(saved['data'])
    result = {}
    for position, node in enumerate(saved['data']['nodes'], 1):
        snapshot = saved['materials'].get(f"{node['material_id']}:{node['material_version']}") if node['material_id'] else None
        bom.require(not node['material_id'] or snapshot is not None, '历史物料快照缺失，无法比较', 409)
        material = (snapshot or {}).get('data', {})
        engineering = material.get('engineering', {})
        values = {f: node.get(f, '') for f in ('parent', 'material_id', 'material_version', 'unit', 'process', 'numerator',
                  'denominator', 'exempt_loss', 'note', 'review_required', 'review_note')}
        values.update(position=position, code=snapshot['code'] if snapshot else node.get('source_code', ''),
            name=snapshot['name'] if snapshot else node.get('source_name', ''), attribute=engineering.get('attribute', ''),
            specification=material.get('spec', ''), color=material.get('color', ''), department=engineering.get('department', ''))
        result[node['key']] = values
    for key, values in result.items():
        path, quantity, cursor = [], Fraction(1), key
        while cursor:
            node = nodes[cursor]
            path.append(cursor)
            quantity *= Fraction(node['numerator']) / Fraction(node['denominator'])
            cursor = node['parent']
        path.reverse()
        values['path_keys'] = path
        values['path'] = ' → '.join((result[k]['code'] + ' ' + result[k]['name']).strip() or k for k in path)
        values['cumulative'] = str(quantity.numerator) + '/' + str(quantity.denominator)
    return result


def compare(before, after):
    old, new = evidence(before), evidence(after)
    rows, unchanged = [], 0
    for key in sorted(old.keys() | new.keys()):
        left, right = old.get(key), new.get(key)
        changes = []
        if left is not None and right is not None:
            for field, label in LABELS.items():
                same = Fraction(left[field]) == Fraction(right[field]) if field in ('numerator', 'denominator') else left[field] == right[field]
                if field == 'path': same = same and left['path_keys'] == right['path_keys']
                if not same: changes.append(dict(field=field, label=label))
            if not changes:
                unchanged += 1
                continue
        rows.append(dict(key=key, kind='ADDED' if left is None else 'REMOVED' if right is None else 'CHANGED',
                         before=left, after=right, changes=changes))
    header = [dict(field=f, label=label, before=before['data'].get(f, ''), after=after['data'].get(f, ''))
              for f, label in (('item_no', '货号'), ('name', 'BOM 名称'), ('specification', '成品规格'), ('source_reference', '来源说明'))
              if before['data'].get(f, '') != after['data'].get(f, '')]
    return dict(id=before['id'], from_version=before['version'], to_version=after['version'],
        from_status=before['status'], to_status=after['status'], header=header, rows=rows, unchanged_count=unchanged)


def read(db, identity, from_version, to_version):
    bom.require(from_version < to_version, '请选择较早版本作为原版，较新版本作为对比版', 422)
    bom.document(db, identity)
    events = db.scalars(select(bom.EngineeringEvent).where(bom.EngineeringEvent.factory_id == bom.FACTORY,
        bom.EngineeringEvent.entity_id == identity, bom.EngineeringEvent.version.in_((from_version, to_version)),
        bom.EngineeringEvent.action.in_(('bom_write', 'bom_approve'))))
    versions = {event.version: json.loads(event.result_json) for event in events}
    before, after = versions.get(from_version), versions.get(to_version)
    bom.require(before is not None and after is not None, '所选 BOM 历史版本不存在', 404)
    return compare(before, after)
