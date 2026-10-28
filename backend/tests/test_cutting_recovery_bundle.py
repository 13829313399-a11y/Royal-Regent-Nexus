"""Recovery must verify encrypted bindings before creating fresh targets."""
from pathlib import Path
import json
import os
import sqlite3
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cutting_recovery_bundle as bundle


@pytest.fixture
def package(tmp_path):
    database=tmp_path/'source.db'
    with sqlite3.connect(database) as con:
        con.execute('CREATE TABLE facts(id TEXT PRIMARY KEY,value BLOB)');con.execute('INSERT INTO facts VALUES (?,?)',('fixture',b'\x00\xff'))
    code=tmp_path/'code';(code/'backend/app').mkdir(parents=True)
    (code/'backend/app/main.py').write_text('# synthetic recovery source')
    (code/'.env').write_text('SYNTHETIC_PRIVATE_CONFIGURATION=not-for-code-bundle')
    storage=tmp_path/'storage';storage.mkdir();(storage/'synthetic-proof.bin').write_bytes(b'\x00\xfe\xff')
    settings=dict(SEED_DEFAULT_ACCOUNTS='false',DATABASE_URL='sqlite:///old-synthetic.db',SYNTHETIC_SECRET='not-a-real-secret')
    metadata=dict(acceptance_release='test-recovery',p5c_source_files={'backend/app/main.py':bundle.file_hash(code/'backend/app/main.py')})
    target=tmp_path/'backup'
    bundle.create_bundle(database,code,storage,settings,metadata,target,protect=lambda v:b'TEST-ONLY:'+v)
    return target


def unprotect(value):
    assert value.startswith(b'TEST-ONLY:')
    return value[len(b'TEST-ONLY:'):]


def test_database_binary_code_and_config_restore_to_fresh_targets(package,tmp_path):
    database,meta=bundle.restore_bundle(package,tmp_path/'restored',tmp_path/'release',unprotect=unprotect)
    with sqlite3.connect(database) as con:assert con.execute('SELECT * FROM facts').fetchall()==[('fixture',b'\x00\xff')]
    assert (database.parent/'storage/synthetic-proof.bin').read_bytes()==b'\x00\xfe\xff'
    assert not (tmp_path/'release/source/.env').exists()
    settings=json.loads((tmp_path/'release/environment.local.json').read_text())
    assert settings['DATABASE_URL']=='sqlite:///'+database.as_posix()
    assert settings['SYNTHETIC_SECRET']=='not-a-real-secret' and settings['SEED_DEFAULT_ACCOUNTS']=='false'
    assert Path(settings['ASSISTANT_STORAGE_DIR']).is_relative_to(database.parent)
    assert meta['release_ready'] is False


@pytest.mark.parametrize('entry',['../outside','/outside','C:/outside','storage/../../outside','storage\\..\\outside'])
def test_unsafe_manifest_paths_are_rejected_before_targets(package,tmp_path,entry):
    p=package/'bundle.json';value=json.loads(p.read_text());value['files'][entry]={'size':1,'sha256':'bad'};p.write_text(json.dumps(value))
    with pytest.raises(ValueError):bundle.restore_bundle(package,tmp_path/'restored',tmp_path/'release',unprotect=unprotect)
    assert not (tmp_path/'restored').exists()


def test_corrupt_binary_or_unlisted_file_cannot_restore(package,tmp_path):
    (package/'storage/synthetic-proof.bin').write_bytes(b'changed')
    with pytest.raises(ValueError,match='integrity'):bundle.restore_bundle(package,tmp_path/'restored',tmp_path/'release',unprotect=unprotect)
    assert not (tmp_path/'restored').exists()


def test_rehashing_tampered_files_does_not_bypass_protected_binding(package,tmp_path):
    data=package/'storage/synthetic-proof.bin';data.write_bytes(b'changed')
    p=package/'bundle.json';value=json.loads(p.read_text());value['files']['storage/synthetic-proof.bin']={'size':7,'sha256':bundle.file_hash(data)};p.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='protected binding'):bundle.restore_bundle(package,tmp_path/'restored',tmp_path/'release',unprotect=unprotect)
    assert not (tmp_path/'restored').exists()


def test_existing_target_and_changed_release_metadata_are_refused(package,tmp_path):
    (tmp_path/'restored').mkdir()
    with pytest.raises(ValueError,match='overwrite'):bundle.restore_bundle(package,tmp_path/'restored',tmp_path/'release',unprotect=unprotect)
    p=package/'bundle.json';value=json.loads(p.read_text());value['release']['acceptance_release']='changed';p.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='protected binding'):bundle.restore_bundle(package,tmp_path/'other',tmp_path/'release',unprotect=unprotect)


def test_failed_early_restore_cannot_delete_a_preexisting_config(tmp_path):
    release=tmp_path/'preexisting';release.mkdir();config=release/'environment.local.json';config.write_text('preserve')
    assert bundle.cleanup_runtime_config(release,'new-owner') is False
    (release/'.recovery-owner').write_text('previous-owner')
    assert bundle.cleanup_runtime_config(release,'new-owner') is False
    assert config.read_text()=='preserve'


def test_partial_restore_after_config_write_cleans_only_owned_config(package,tmp_path,monkeypatch):
    target=tmp_path/'restore';release=tmp_path/'release';original=bundle.file_hash
    monkeypatch.setattr(bundle,'file_hash',lambda p:'injected-mismatch' if p==target/'cutting.db' else original(p))
    with pytest.raises(ValueError,match='database bytes'):
        bundle.restore_bundle(package,target,release,unprotect=unprotect,owner_token='owned-run')
    assert (release/'environment.local.json').is_file()
    assert bundle.cleanup_runtime_config(release,'owned-run') is True
    assert not (release/'environment.local.json').exists()


def test_config_cleanup_failure_is_retained_as_failure_without_masking_primary(tmp_path,monkeypatch):
    release=tmp_path/'owned';release.mkdir();(release/'.recovery-owner').write_text('owner')
    config=release/'environment.local.json';config.write_text('synthetic-private-config')
    original=Path.unlink
    def locked(path,*args,**kwargs):
        if path==config:raise PermissionError('synthetic sharing violation')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',locked)
    report={'status':'passed','error_type':'PrimarySyntheticFailure'}
    error=bundle.finalize_cleanup(release,'owner',report)
    assert isinstance(error,PermissionError) and report['status']=='failed'
    assert not report['plaintext_runtime_config_removed'] and report['error_type']=='PrimarySyntheticFailure'
    assert report['cleanup_error_type']=='PermissionError'


def test_copy_damage_to_unpinned_source_cannot_start_restored_release(package,tmp_path,monkeypatch):
    release=tmp_path/'release';original=bundle.copy_tree
    def damaged(source,target,**kwargs):
        original(source,target,**kwargs)
        if target==release/'source':(target/'backend/app/main.py').write_text('# injected copy damage')
    monkeypatch.setattr(bundle,'copy_tree',damaged)
    with pytest.raises(ValueError,match='Restored source'):
        bundle.restore_bundle(package,tmp_path/'restore',release,unprotect=unprotect,owner_token='owner')
    assert bundle.cleanup_runtime_config(release,'owner')


def test_cleanup_link_refusal_is_recorded_without_masking_primary(tmp_path,monkeypatch):
    def refuse(*args):raise ValueError('synthetic reparse refusal')
    monkeypatch.setattr(bundle,'cleanup_runtime_config',refuse)
    report={'status':'passed','error_type':'PrimarySyntheticFailure'}
    error=bundle.finalize_cleanup(tmp_path,'owner',report)
    assert isinstance(error,ValueError) and report['status']=='failed'
    assert report['cleanup_error_type']=='ValueError' and report['error_type']=='PrimarySyntheticFailure'


def test_recovery_distinguishes_dispatched_orders_from_received_orders(tmp_path):
    from verify_cutting_recovery import order_counts
    with sqlite3.connect(tmp_path/'orders.db') as con:
        con.execute('CREATE TABLE cutting_ops_orders(id TEXT)')
        con.executemany('INSERT INTO cutting_ops_orders VALUES (?)',[(str(i),) for i in range(100)])
        con.execute('CREATE TABLE order_ledger_dispatches(line_id TEXT,factory_id TEXT,recipient TEXT)')
        con.executemany('INSERT INTO order_ledger_dispatches VALUES (?,?,?)',[(str(i),'huakang-c','cutting') for i in range(500)])
        con.execute("INSERT INTO order_ledger_dispatches VALUES ('0','huakang-c','cutting')")
        con.execute("INSERT INTO order_ledger_dispatches VALUES ('foreign','huakang-d','cutting')")
        assert order_counts(con)==(500,100)


def test_reparse_point_guard_fails_closed(tmp_path,monkeypatch):
    from types import SimpleNamespace
    p=tmp_path/'junction';p.mkdir()
    original=Path.lstat
    monkeypatch.setattr(Path,'lstat',lambda s:SimpleNamespace(st_file_attributes=0x400,st_mode=original(s).st_mode) if s==p else original(s))
    with pytest.raises(ValueError,match='reparse'):bundle.reject_link(p)


def test_platform_crypto_contract_and_windows_corruption_rejection():
    raw=b'{"kind":"synthetic-config-recovery-only"}'
    if os.name!='nt':
        with pytest.raises(RuntimeError,match='no plaintext fallback'):bundle.protect_config(raw)
        return
    encrypted=bundle.protect_config(raw)
    assert raw not in encrypted and bundle.protect_config(encrypted,decrypt=True)==raw
    damaged=bytearray(encrypted);damaged[-8]^=1
    with pytest.raises(RuntimeError,match='DPAPI'):bundle.protect_config(bytes(damaged),decrypt=True)
