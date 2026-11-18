"""First-launch references persist without replacing the clerk's later versions."""
from hashlib import sha256
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from test_standalone import BASE, HEADERS, ORIGIN, SCOPE, create_app, exported, intake, parsed, workbook
from app.reference_seed import read_seed


def seed_files(directory, invalid_price=False):
    directory.mkdir()
    rows = []
    for kind in ('schedule', 'price'):
        content = b'not a workbook' if kind == 'price' and invalid_price else workbook(kind)
        (directory / (kind + '.xlsx')).write_bytes(content)
        rows.append({'kind': kind, 'file': kind + '.xlsx', 'name': '预置' + kind + '.xlsx',
            'sha256': sha256(content).hexdigest()})
    manifest = {'format': 1, 'factory_id': 'huakang-b', 'files': rows}
    (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


def client_for(data, seed):
    return TestClient(create_app(data, port=18765, reference_seed_dir=seed), base_url=ORIGIN, headers=HEADERS)


def counts(data):
    with sqlite3.connect(data / 'jp-trial.sqlite3') as db:
        return {name: db.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] for name in
            ('jp_intake_references', 'jp_intake_reference_events', 'order_ledger_sources', 'jp_intake_counters')}


def test_seed_export_update_and_restart_preserve_evidence(tmp_path):
    seed, data = tmp_path / 'seed', tmp_path / 'data'
    seed_files(seed)
    with client_for(data, seed) as client:
        refs = client.get(BASE + '/references', params=SCOPE).json()
        assert set(refs) == {'schedule', 'price'}
        assert all(row['revision'] == 1 and row['actor'] == '试用包预置' for row in refs.values())
        raw, form, preview = parsed(client)
        saved = exported(client, raw, form, preview)
        assert saved.status_code == 200 and saved.json()['first_number'] == 21615
        export_id = saved.json()['id']
        original = client.get(BASE + f'/exports/{export_id}/download', params=SCOPE).content
        # A valid replacement must persist, while the old preview becomes stale.
        replacement = workbook('price') + b'valid ZIP trailing comment'
        response = client.post(BASE + '/references/price', data={**SCOPE, 'expected_revision': 1},
            files={'file': ('文员更新.xlsx', replacement)})
        assert response.status_code == 200, response.text
        assert response.json()['price']['revision'] == 2
        stale = exported(client, raw, form, preview)
        assert stale.status_code == 409
        after = counts(data)
    # Existing references remain sufficient even if seed files were removed after startup.
    (seed / 'price.xlsx').unlink()
    with client_for(data, seed) as restarted:
        refs = restarted.get(BASE + '/references', params=SCOPE).json()
        assert refs['price']['sha256'] == sha256(replacement).hexdigest()
        assert refs['price']['name'] == '文员更新.xlsx' and refs['price']['revision'] == 2
        assert restarted.get(BASE + f'/exports/{export_id}/download', params=SCOPE).content == original
        assert counts(data) == after


def test_existing_one_reference_is_preserved_and_only_missing_kind_is_added(tmp_path):
    seed, data = tmp_path / 'seed', tmp_path / 'data'
    seed_files(seed)
    with client_for(data, None) as client:
        existing = workbook('price') + b'existing'
        response = client.post(BASE + '/references/price', data={**SCOPE, 'expected_revision': 0},
            files={'file': ('旧包货价.xlsx', existing)})
        assert response.status_code == 200
        old_price = response.json()['price']
    with client_for(data, seed) as client:
        refs = client.get(BASE + '/references', params=SCOPE).json()
        assert refs['price'] == old_price and refs['schedule']['revision'] == 1
        assert counts(data)['jp_intake_reference_events'] == 2


def test_second_invalid_workbook_leaves_no_partial_reference(tmp_path):
    seed, data = tmp_path / 'seed', tmp_path / 'data'
    seed_files(seed, invalid_price=True)
    with pytest.raises(ValueError):
        create_app(data, reference_seed_dir=seed)
    assert set(counts(data).values()) == {0}


def test_second_save_failure_rolls_back_both_sources_and_events(tmp_path, monkeypatch):
    seed, data = tmp_path / 'seed', tmp_path / 'data'
    seed_files(seed)
    original = intake.save_reference
    def fail_second(db, kind, *args, **kwargs):
        if kind == 'price':
            raise RuntimeError('second write failed')
        return original(db, kind, *args, **kwargs)
    monkeypatch.setattr(intake, 'save_reference', fail_second)
    with pytest.raises(RuntimeError, match='second write failed'):
        create_app(data, reference_seed_dir=seed)
    assert set(counts(data).values()) == {0}


@pytest.mark.parametrize('invalid', ['hash', 'path', 'duplicate', 'factory', 'missing', 'oversize', 'symlink'])
def test_invalid_seed_is_rejected(tmp_path, invalid):
    seed = tmp_path / 'seed'
    manifest = seed_files(seed)
    if invalid == 'hash': manifest['files'][1]['sha256'] = '0' * 64
    if invalid == 'path': manifest['files'][1]['file'] = '../price.xlsx'
    if invalid == 'duplicate': manifest['files'][1]['kind'] = 'schedule'
    if invalid == 'factory': manifest['factory_id'] = 'huakang-a'
    if invalid == 'missing': (seed / 'price.xlsx').unlink()
    if invalid == 'oversize':
        with (seed / 'price.xlsx').open('wb') as stream: stream.truncate(intake.MAX_FILE + 1)
    if invalid == 'symlink':
        (seed / 'price.xlsx').unlink()
        (seed / 'price.xlsx').symlink_to(seed / 'schedule.xlsx')
    (seed / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises((ValueError, OSError)):
        read_seed(seed)
