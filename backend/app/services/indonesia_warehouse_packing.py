"""Physical cartons belong to a warehouse/voucher, not to each material row."""
from collections import Counter, defaultdict
import hashlib
import json
import unicodedata

from pydantic import ValidationError

from app.schemas.indonesia_materials import Package

FIELDS = ('cartons', 'length_cm', 'width_cm', 'height_cm', 'carton_weight_kg')
LABELS = dict(zip(FIELDS, ('箱数', '箱长', '箱宽', '箱高', '每箱纸箱重量')))


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).strip().lower().split())


def packing_key(source, warehouse=''):
    return tuple(normalized(value) for value in
                 (source.get('warehouse') or warehouse, source.get('receipt_no'), source.get('package_label')))


def packing_groups(rows, warehouse='', previously_received=()):
    groups = defaultdict(list)
    for row in rows:
        key = packing_key(row['source'], warehouse)
        if key[-1]:
            groups[key].append(row)
    labels = Counter(key[-1] for key in groups)
    result = []
    for position, (key, members) in enumerate(groups.items(), 1):
        source = members[0]['source']
        label = source['package_label'].strip()
        # Keep different warehouses/vouchers distinct even if their carton labels coincide.
        output_label = label if labels[key[-1]] == 1 else f'{label[:140]}（来源 {position}）'
        issues, values, invalid_rows = [], [], []
        if not all(key):
            issues.append('缺少仓库或收料单号')
        if key in previously_received or any(row.get('imported_supply_id') for row in members):
            issues.append('同箱已有导入记录，请核对原出货草稿，避免重复计箱')
        if any(row.get('blocked') for row in members):
            issues.append('同箱有实收行待核对')
        if len({row['source'].get('actual_date') for row in members}) > 1:
            issues.append('同箱实收日期不一致')
        for row in members:
            data = row['source']
            missing = [LABELS[field] for field in FIELDS if data.get(field) in ('', None)]
            if missing:
                invalid_rows.append(f"第 {row['index'] + 1} 行缺少{'、'.join(missing)}")
                continue
            try:
                package = Package.model_validate(dict(label=output_label, **{field: data[field] for field in FIELDS},
                    items=[dict(allocation_id='packing-check', normal_quantity='1', spare_quantity='0')]))
                values.append(package)
            except ValidationError:
                invalid_rows.append(f"第 {row['index'] + 1} 行装箱数值无效（箱数须为正整数，尺寸须大于零，纸箱重不得为负数）")
        # Group metadata accompanies each source row; keep it bounded for 2,000-row files.
        issues.extend(invalid_rows[:3])
        if len(invalid_rows) > 3:
            issues.append(f'另有 {len(invalid_rows) - 3} 行装箱资料缺失或无效，请核对原单')
        if values:
            differences = [LABELS[field] for field in FIELDS if any(getattr(value, field) != getattr(values[0], field) for value in values[1:])]
            if differences:
                issues.append(f"同箱{'、'.join(differences)}不一致")
        result.append(dict(id=hashlib.sha256(json.dumps(key).encode()).hexdigest(), indexes=[row['index'] for row in members],
            warehouse=source.get('warehouse') or warehouse, receipt_no=source.get('receipt_no', ''), label=label,
            output_label=output_label, row_count=len(members), issues=list(dict.fromkeys(issues)),
            package=values[0].model_dump(mode='json', exclude={'items'}) if values and not issues else None))
    return result


def assemble_packages(groups, row_lines):
    """Only a fully selected, consistent physical group can carry into a new draft."""
    packages, notes = [], []
    covered = set()
    for group in groups:
        selected = set(group['indexes']) & row_lines.keys()
        if not selected:
            continue
        problems = list(group['issues'])
        if len(selected) != group['row_count']:
            problems.append('同箱物料未全部选中，请一起导入或在出货草稿核对混箱')
        if problems:
            notes.append(f"{group['warehouse']} / {group['receipt_no']} / {group['label']}：{'；'.join(problems)}")
        elif group['package']:
            items = [line for index in group['indexes'] for line in row_lines[index]]
            packages.append(Package.model_validate(dict(**group['package'], items=items)).model_dump(mode='json'))
            covered.update(selected)
    missing = row_lines.keys() - covered
    if missing and not notes:
        notes.append('部分物料未填写箱号或装箱资料，请在下方补齐。')
    return packages, notes, bool(missing)
