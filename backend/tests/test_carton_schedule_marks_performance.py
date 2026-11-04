"""Large schedule reads must not resolve absent materials once per row."""
import copy
import json
import time

import pytest


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    for key in ('ONLINE_DOCUMENTS_ENABLED', 'COLLABORATION_ENABLED', 'QC_DEPARTMENT_MANAGED',
                'CARTON_ASSET_V1_ENABLED'):
        monkeypatch.setenv(key, 'false')
    monkeypatch.setenv('AUTHZ_MODE', 'enforce')
    monkeypatch.setenv('CARTON_MATERIALS_V2_WRITES_ENABLED', 'true')


def test_1154_absent_materials_use_bounded_key_queries_and_never_resolve_or_write(monkeypatch):
    from test_carton_materials import make_client, setup, _audit_total, ok
    with make_client(monkeypatch) as client:
        from app.services import carton_file_jobs
        import test_molding_sample_api
        monkeypatch.setattr(carton_file_jobs, 'LOCK_PATH', test_molding_sample_api.TEST_TMP_DIR / 'file-job.lock')
        _, target = setup(client)
        from app.db import SessionLocal, engine
        from app.models.carton_procurement import CartonImportBatch
        from app.models.auth import AuthUser
        from app.services.auth import build_auth_context
        from app.services.carton_schedule_marks import legacy_material_hints
        from app.services.carton_materials_resolver import Resolver
        from sqlalchemy import event, select
        with SessionLocal() as db:
            batch = db.get(CartonImportBatch, target['id'])
            summary = json.loads(batch.parse_summary_json)
            original = summary['rows'][0]
            rows = [dict(copy.deepcopy(original), source_row=i + 1004, contract_no=f'PERF-{i}',
                         item_no=f'ITEM-{i}', schedule_customer_code='DICKIE') for i in range(1154)]
            summary['rows'] = rows
            batch.parse_summary_json = json.dumps(summary)
            db.commit()
        before = _audit_total()
        def forbidden(*args, **kwargs):
            raise AssertionError('Absent schedule materials must not run the per-row resolver')
        monkeypatch.setattr(Resolver, 'resolve', forbidden)
        queries = []
        def trace(conn, cursor, sql, params, context, executemany):
            queries.append(sql)
        with SessionLocal() as db:
            user = build_auth_context(db, db.scalar(select(AuthUser).where(AuthUser.username == 'admin')))
            event.listen(engine, 'before_cursor_execute', trace)
            started = time.perf_counter()
            try:
                assert legacy_material_hints(db, user, 'huaxing', target['id'], rows) == {}
            finally:
                event.remove(engine, 'before_cursor_execute', trace)
            elapsed = time.perf_counter() - started
        # At most three binding chunks and six authority chunks, plus batch/customer reads.
        assert len(queries) <= 12, len(queries)
        assert all('entity_id IN' in sql for sql in queries if 'carton_audit_events' in sql)
        assert all(sql.lstrip().upper().startswith('SELECT') for sql in queries)
        response = ok(client.get('/api/carton-mark/assets/schedule',
            params={'factory_id': 'huaxing', 'batch_id': target['id']}))
        assert len(response['rows']) == 1154
        assert all('materials_folder_id' not in row and row['status'] == 'MISSING' for row in response['rows'])
        assert _audit_total() == before
        print(json.dumps({'rows': 1154, 'material_hint_queries': len(queries),
                          'material_hint_seconds': round(elapsed, 4), 'read_only': True}))
