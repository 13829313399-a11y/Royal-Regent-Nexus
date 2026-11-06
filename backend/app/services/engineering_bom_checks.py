"""Version-bound preparation advice; approval always performs its own checks."""
from fastapi import HTTPException
from app.core.time import business_now
from app.services import engineering_bom as bom
from app.services.transaction_lock import lock_transaction


def read(db, identity, expected_version):
    # Engineering material mutations take this same lock. No event or revision is written.
    lock_transaction(db, 'engineering-bom', bom.FACTORY)
    record = bom.document(db, identity)
    bom.require(record.version == expected_version, 'BOM 已变化，请刷新资料后重新检查')
    current = bom.view(db, record)
    bom.require(current is not None, 'BOM 历史依据缺失，无法检查')
    issues = []
    if current['status'] != 'DRAFT':
        issues.append(dict(row=None, key='', code='', name='', attribute='', message='仅草稿可审核；此版本无需重复审核'))
    try:
        bom.validate_tree(current['data'])
    except HTTPException as error:
        if error.status_code != 422:
            raise
        issues.append(dict(row=None, key='', code='', name='', attribute='', message=error.detail))
    else:
        for row, node in enumerate(current['data']['nodes'], 1):
            try:
                # Reuse the authoritative approval validator, retaining its rule order.
                bom.pin_materials(db, {'nodes': [node]}, current, publishing=True)
            except HTTPException as error:
                if error.status_code not in (404, 422):
                    raise
                frozen = current['materials'].get(f"{node['material_id']}:{node['material_version']}", {})
                issues.append(dict(row=row, key=node['key'], code=frozen.get('code', node['source_code']),
                    name=frozen.get('name', node['source_name']),
                    attribute=frozen.get('data', {}).get('engineering', {}).get('attribute', ''), message=error.detail))
    return dict(id=identity, version=record.version, status=current['status'], effective_version=record.effective_version,
                checked_at=business_now().isoformat(), checked_rows=len(current['data']['nodes']),
                ready_for_approval=not issues, issues=issues, can_release=False)
