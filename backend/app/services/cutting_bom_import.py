"""Preview a fixed engineering workbook and save one versioned BOM draft."""
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath
from zipfile import ZipFile

import openpyxl
from fastapi import HTTPException
from pydantic import Field, ValidationError
from sqlalchemy import select

from app.models.cutting_ops import CuttingMaster, CuttingRevision
from app.services import cutting_ops as c, cutting_schemas as s
from app.services.cutting_schedule_import import filename, text
from app.services.order_workbook_bounds import worksheet_bounds

ACTION = 'bom-import'
MAX_BYTES = 5 * 1024 * 1024
SHEETS = {
    '产品与版本': (('BOM编码', '货号', '产品名称', '款式规格', '颜色', '工程来源版本'), 1),
    '裁片组成': (('部件编码', '部件名称', '每套裁片数'), 200),
    '物料用量': (('物料编码', '适用部件编码', '每套净用量', '单位', '适用阶段', '裁剪必需', '备注'), 300),
}


class Confirm(s.Command):
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    file_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    file_name: str = Field(min_length=1, max_length=255)


class Recover(s.Strict):
    command: Confirm


def template():
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name, (headers, _) in SHEETS.items():
        sheet = book.create_sheet(name)
        sheet.append(headers)
        sheet.freeze_panes = 'A2'
        for index in range(1, len(headers) + 1):
            column = openpyxl.utils.get_column_letter(index)
            sheet.column_dimensions[column].width = 22
            if name == '产品与版本' or index in (1, 2):
                sheet.column_dimensions[column].number_format = '@'
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def parse(content, name):
    c.require(PurePath(name).suffix.lower() == '.xlsx', '请选择 BOM 固定模板 .xlsx 文件', 422)
    c.require(0 < len(content) <= MAX_BYTES, 'BOM 文件为空或超过 5 MB', 422)
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            c.require(len(entries) <= 100 and sum(entry.file_size for entry in entries) <= 20 * 1024 * 1024,
                      'BOM 工作簿解压后超限', 422)
            c.require(not any('externallinks/' in entry.filename.lower() or entry.filename.lower().endswith('vbaproject.bin')
                              for entry in entries), '请移除宏或外部链接后导入', 422)
        book = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=False, keep_links=False)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, '无法读取 BOM 工作簿，请使用固定模板') from exc

    tables, issues = {}, []
    try:
        c.require(len(book.sheetnames) == len(SHEETS) and set(book.sheetnames) == set(SHEETS),
                  '工作簿必须且只能包含产品与版本、裁片组成、物料用量三张表', 422)
        for name, (headers, limit) in SHEETS.items():
            sheet = book[name]
            c.require(sheet.sheet_state == 'visible', f'{name}不能隐藏', 422)
            sheet.reset_dimensions()
            height, _ = worksheet_bounds(book, sheet, limit + 1, len(headers), f'{name}超出模板行列范围', 422)
            rows = sheet.iter_rows(max_row=height, max_col=len(headers))
            header = next(rows, ())
            if tuple(text(cell) for cell in header) != headers or any(cell.data_type in ('f', 'e') for cell in header):
                issues.append(dict(sheet=name, row=1, message='表头与固定模板不一致，请重新下载模板'))
                continue
            tables[name] = []
            for number, cells in enumerate(rows, start=2):
                if any(cell.data_type in ('f', 'e') for cell in cells):
                    issues.append(dict(sheet=name, row=number, message='请使用原始值，不能含公式或错误单元格'))
                    continue
                values = tuple(text(cell) for cell in cells)
                if any(values):
                    tables[name].append((number, values))
            if not tables[name]:
                issues.append(dict(sheet=name, row=2, message='请填写至少一行资料'))
        return tables, issues
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, 'BOM 工作表损坏或格式不受支持') from exc
    finally:
        book.close()


def _model(model, fields, labels, sheet, row, issues):
    try:
        return model.model_validate(fields).model_dump(mode='json')
    except ValidationError as exc:
        for problem in exc.errors():
            label = labels.get(problem['loc'][0], '') if problem['loc'] else ''
            detail = problem['msg'].removeprefix('Value error, ') if problem['type'] == 'value_error' else '缺失或格式超出允许范围'
            issues.append(dict(sheet=sheet, row=row, message=f'{label} {detail}'.strip()))
        return None


def preview(db, user, content, name, parsed):
    tables, structural_issues = parsed
    issues = list(structural_issues)
    result = dict(file_name=name, file_sha256=sha256(content).hexdigest(), issues=issues, candidate=None, fingerprint=None)
    if issues:
        return result

    _, (code, item_no, product, style, color, source) = tables['产品与版本'][0]
    parts, part_codes = [], set()
    for row, (part_code, part_name, count) in tables['裁片组成']:
        part = _model(s.Part, dict(code=part_code, name=part_name, pieces_per_set=int(count) if count.isascii() and count.isdigit() and len(count) <= 6 else count),
                      dict(zip(('code', 'name', 'pieces_per_set'), SHEETS['裁片组成'][0])), '裁片组成', row, issues)
        if part_code in part_codes:
            issues.append(dict(sheet='裁片组成', row=row, message=f'部件编码重复：{part_code}'))
        elif part:
            parts.append(part)
            part_codes.add(part_code)

    material_codes = {fields[0] for _, fields in tables['物料用量']}
    materials = {item.code: item for item in db.scalars(select(CuttingMaster).where(
        CuttingMaster.factory_id == c.FACTORY, CuttingMaster.kind == 'material', CuttingMaster.code.in_(material_codes)))}
    requirements, display_rows, usages = [], [], set()
    for row, (material_code, applicable, quantity, unit, stage, required, note) in tables['物料用量']:
        def issue(message):
            issues.append(dict(sheet='物料用量', row=row, message=message))

        item = materials.get(material_code)
        material = c.view(db, item) if item else None
        codes = [value.strip() for value in applicable.replace('，', ',').replace('、', ',').split(',')]
        if not material or material['status'] != 'active':
            issue(f'未匹配有效物料编码：{material_code}')
        elif material['data']['unit'] != unit:
            issue(f'单位须与物料 {material_code} V{item.version} 一致（{material["data"]["unit"]}）')
        if any(value not in part_codes for value in codes) or len(set(codes)) != len(codes):
            issue('适用部件必须来自裁片组成表，多个编码用逗号分隔且不可重复')
        if required not in ('是', '否'):
            issue('裁剪必需只能填写“是”或“否”')
        identity = (material_code, stage, tuple(sorted(codes)))
        if identity in usages:
            issue(f'物料用量行重复：{material_code}、{stage}、{applicable}')
        usages.add(identity)
        if not material or material['status'] != 'active':
            continue
        labels = dict(zip(('material_id', 'part_codes', 'quantity_per_set', 'unit', 'stage', 'required_for_cutting', 'note'), SHEETS['物料用量'][0]))
        requirement = _model(s.Requirement, dict(material_id=item.id, material_version=item.version, part_codes=codes,
                             quantity_per_set=quantity, unit=unit, stage=stage, required_for_cutting=required == '是', note=note),
                             labels, '物料用量', row, issues)
        if requirement:
            requirements.append(requirement)
            display_rows.append(dict(row=row, material_code=material_code, material_name=material['data']['name'], **requirement))

    data = _model(s.Bom, dict(name=product, item_no=item_no, style=style, color=color, source_reference=source,
                  parts=parts, requirements=requirements),
                  dict(zip(('item_no', 'name', 'style', 'color', 'source_reference'), SHEETS['产品与版本'][0][1:])),
                  '产品与版本', 2, issues) if not issues else None
    if not code or len(code) > 80:
        issues.append(dict(sheet='产品与版本', row=2, message='BOM 编码必填，最多 80 字'))
    if issues:
        return result
    try:
        c.validate_references(db, data, publishing=True)
    except HTTPException as exc:
        issues.append(dict(sheet='物料用量', row=None, message=exc.detail))
        return result

    existing = db.scalar(select(CuttingMaster).where(CuttingMaster.factory_id == c.FACTORY,
                         CuttingMaster.kind == 'bom', CuttingMaster.code == code))
    if existing:
        current = c.view(db, existing)
        used_source = db.scalar(select(CuttingRevision.version).where(CuttingRevision.master_id == existing.id,
                                CuttingRevision.data['source_reference'].as_string() == source).limit(1))
        if used_source is not None:
            issues.append(dict(sheet='产品与版本', row=2, message='该 BOM 的工程来源版本已经登记，请核对版本记录'))
        elif current['status'] != 'published':
            issues.append(dict(sheet='产品与版本', row=2, message='此编码已有待处理草稿，请先核对现有草稿'))
        elif current['data']['item_no'] != item_no:
            issues.append(dict(sheet='产品与版本', row=2, message='货号与此 BOM 编码的已发布版本不一致'))
    if issues:
        return result

    candidate = dict(code=code, existing_id=existing.id if existing else None,
                     expected_version=existing.version if existing else 0, data=data, material_rows=display_rows)
    result['candidate'] = candidate
    result['fingerprint'] = c.payload_fingerprint(dict(actor_id=user.id, factory_id=c.FACTORY, name=name,
        file_sha256=result['file_sha256'], candidate=candidate), 'bom-import-preview-v1')
    return result


def confirm(db, user, body, content, parsed):
    fresh = preview(db, user, content, body.file_name, parsed)
    candidate = fresh['candidate']
    c.require(candidate and fresh['fingerprint'] == body.fingerprint and candidate['expected_version'] == body.expected_version,
              'BOM 或物料依据已变化，请重新预览并核对后导入')
    command = s.Save(factory_id=body.factory_id, operation_id=body.operation_id, expected_version=body.expected_version,
                     reason=body.reason, kind='bom', code=candidate['code'], data=candidate['data'])
    record = c.save(db, user, command, candidate['existing_id'])
    return dict(record=record, file_name=body.file_name, file_sha256=body.file_sha256)
