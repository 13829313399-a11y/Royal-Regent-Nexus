"""Compare optimized schedule hints against the previous per-row reader."""
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

import test_molding_sample_api
from test_carton_materials import make_client, setup


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    for key in ('ONLINE_DOCUMENTS_ENABLED', 'COLLABORATION_ENABLED', 'QC_DEPARTMENT_MANAGED', 'CARTON_ASSET_V1_ENABLED'):
        monkeypatch.setenv(key, 'false')
    monkeypatch.setenv('CARTON_MATERIALS_V2_WRITES_ENABLED', 'true')
    monkeypatch.setenv('AUTHZ_MODE', 'enforce')


def old_hints(db, user, batch_id, rows):
    from app.schemas.carton_materials import Target
    from app.services import carton_materials as m
    folders = m.folders(db, 'huaxing')
    result = {}
    for row in rows:
        key = (row.get('source_sheet') or '', row.get('source_row') or 0)
        if not row.get('schedule_customer_code'):
            continue
        try:
            data = m.resolve_target(db, 'huaxing', 'warehouse', Target(kind='SCHEDULE', id=batch_id, sheet=key[0], row=key[1]))
            identifier = m.folder_id('huaxing', data)
            if identifier in folders:
                m.authorize(db, user, 'huaxing', 'warehouse', folders[identifier])
                result[key] = dict(materials_folder_id=identifier, materials_status=m.output(folders[identifier], 'warehouse')['status_label'])
        except HTTPException:
            pass
    return result


def test_prefetch_matches_legacy_reader_for_bindings_conflicts_and_scope(monkeypatch):

    with make_client(monkeypatch) as client:
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.models.carton_procurement import CartonAuditEvent, CartonImportBatch
        from app.schemas.carton_materials import Target
        from app.services import carton_materials as m, carton_schedule_marks as marks
        from app.services.carton_materials_resolver import BINDINGS, Resolver, target_key
        from app.services import carton_file_jobs
        monkeypatch.setattr(carton_file_jobs, 'LOCK_PATH', test_molding_sample_api.TEST_TMP_DIR / 'file-job.lock')
        state, target_data = setup(client)
        target = Target(**target_data)
        with SessionLocal() as db:
            admin = db.scalar(select(AuthUser).where(AuthUser.username == 'admin'))
            from app.services.auth import build_auth_context
            user = build_auth_context(db, admin)
            batch = db.get(CartonImportBatch, target.id)
            summary = json.loads(batch.parse_summary_json)
            def rows():
                return marks.schedule_sources(db, 'huaxing')[batch.id]
            def check(expected):
                before = db.scalar(select(func.count()).select_from(CartonAuditEvent))
                reference = old_hints(db, user, batch.id, rows())
                actual = marks.legacy_material_hints(db, user, 'huaxing', batch.id, rows())
                assert actual == reference
                assert bool(actual) is expected
                assert db.scalar(select(func.count()).select_from(CartonAuditEvent)) == before
            check(True)  # Explicit native binding and active authority.
            # A row-level customer annotation is not the authoritative batch customer.
            summary['rows'][0]['schedule_customer_code'] = 'OTHER'
            batch.parse_summary_json = json.dumps(summary, ensure_ascii=False); db.flush()
            check(True)
            # A stale caller snapshot cannot bypass a changed persisted identity.
            stale_rows = rows()
            summary['rows'][0]['contract_no'] = 'CHANGED-CONTRACT'
            batch.parse_summary_json = json.dumps(summary, ensure_ascii=False); db.flush()
            assert marks.legacy_material_hints(db, user, 'huaxing', batch.id, stale_rows) == old_hints(db, user, batch.id, stale_rows) == {}
            summary['rows'][0]['contract_no'] = state['contract_no']
            batch.parse_summary_json = json.dumps(summary, ensure_ascii=False); db.flush()
            # Repeated source coordinates invalidate the target, even with a binding.
            summary['rows'].append(deepcopy(summary['rows'][0]))
            batch.parse_summary_json = json.dumps(summary, ensure_ascii=False); db.flush()
            check(False)
            summary['rows'].pop()
            batch.parse_summary_json = json.dumps(summary, ensure_ascii=False); db.flush()
            # Permission errors remain suppressed, without leaking a folder hint.
            original = m.authorize
            def denied(*args, **kwargs):
                raise HTTPException(403, 'denied')
            monkeypatch.setattr(m, 'authorize', denied)
            check(False)
            monkeypatch.setattr(m, 'authorize', original)
            # A legacy and a native authority for the same facts conflict, even
            # when a binding exists. An orphaned alias must not hide that conflict.
            nested = db.begin_nested()
            data, _, _ = Resolver(db, 'huaxing', 'warehouse').facts(target=target)
            native = m.get(db, 'huaxing', state['id'])
            legacy_id = m.legacy_folder_id('huaxing', data)
            m.append(db, admin, 'huaxing', legacy_id, {**native, 'id': legacy_id}, 'TEST', uuid4().hex, '')
            db.flush()
            check(False)
            nested.rollback()
            # No metadata or binding: the optimized reader must report no hint.
            nested = db.begin_nested()
            db.query(CartonAuditEvent).filter(CartonAuditEvent.entity_id.in_([state['id'], target_key('huaxing', target)])).delete(synchronize_session=False)
            db.flush()
            check(False)
            nested.rollback()
            # A stale binding must never fall through to another record.
            binding_key = target_key('huaxing', target)
            binding = Resolver(db, 'huaxing', 'warehouse').read(BINDINGS, binding_key)
            broken = {**binding, 'authority_id': 'CMF-missing'}
            m.append(db, admin, 'huaxing', binding_key, broken, 'TEST', uuid4().hex, '', BINDINGS); db.flush()
            check(False)
            # Different factory and rejected batches cannot expose these records.
            assert marks.legacy_material_hints(db, user, 'huakang-a', batch.id, rows()) == {}
            current_rows = rows()
            batch.status = 'REJECTED'; db.flush()
            assert marks.legacy_material_hints(db, user, 'huaxing', batch.id, current_rows) == {}
