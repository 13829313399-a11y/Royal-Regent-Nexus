"""Release safety gates, data preservation and repeat behavior."""
from pathlib import Path
import importlib.util
import pytest
from sqlalchemy import create_engine,text


def module():
    path=Path(__file__).resolve().parents[1]/'scripts/qc_dossier_release.py'
    spec=importlib.util.spec_from_file_location('qc_release',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def test_volume_bootstrap_never_overwrites_existing_files(tmp_path):
    release=module();source=tmp_path/'source';target=tmp_path/'volume';source.mkdir()
    (source/'business.txt').write_text('00012 original business')
    release.restore_empty_volume(source,target)
    release.restore_empty_volume(source,target)
    assert (target/'business.txt').read_text()=='00012 original business'
    (target/'business.txt').write_text('new work')
    with pytest.raises(RuntimeError,match='differs'):release.restore_empty_volume(source,target)
    assert (target/'business.txt').read_text()=='new work'


def test_empty_or_symlink_backups_are_rejected(tmp_path):
    release=module();source=tmp_path/'source';source.mkdir()
    with pytest.raises(RuntimeError,match='empty'):release.restore_empty_volume(source,tmp_path/'target')
    link = source / 'link'
    target = tmp_path / 'elsewhere'
    target.mkdir()
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, 'winerror', None) != 1314:
            raise
        # Windows permits directory junctions without the symlink privilege.
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    with pytest.raises(RuntimeError,match='symlink'):release.inventory(source)


def test_release_rejects_old_unknown_main_version_before_writes(tmp_path,monkeypatch):
    release=module();engine=create_engine('sqlite:///'+str(tmp_path/'main.db'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE alembic_version(version_num TEXT)'))
        conn.execute(text("INSERT INTO alembic_version VALUES('20261022_0175')"))
    monkeypatch.setattr(release,'engine',engine)
    with pytest.raises(RuntimeError,match='verified QC-compatible revision'):release.prepare(tmp_path)
    assert not (tmp_path/'qc-before').exists()


@pytest.mark.parametrize("revision", ["20261116_0195", "20261116_inj_retire", "20261119_0195", "20261119_0196", "20261119_0197", "20261121_inj_merge",
                                      "20261123_shipping_merge", "20261124_0202", "20261124_0203"])
def test_qc_recognizes_existing_compatible_successors(tmp_path, monkeypatch, revision):
    release = module()
    engine = create_engine("sqlite:///" + (tmp_path / "main.db").as_posix())
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version(version_num TEXT)"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": revision})
    monkeypatch.setattr(release, "engine", engine)
    assert release.version() == revision
    assert revision in release.QC_READY_REVISIONS
    engine.dispose()


def test_start_requires_preparation_and_readiness_requires_collection(tmp_path,monkeypatch):
    release=module();monkeypatch.setattr(release.archive.settings,'qc_dossier_enabled',True)
    monkeypatch.setattr(release.archive.settings,'qc_department_data_dir',str(tmp_path))
    with pytest.raises(RuntimeError,match='preparation missing'):release.start()
    monkeypatch.setattr(release.archive.settings,'qc_dossier_enabled',False)
    assert release.readiness()=={'enabled':False,'status':'emergency-disabled'}


@pytest.mark.parametrize("starting_revision", ["20261110_0194", "20261116_0195", "20261119_0197", "20261121_inj_merge"])
def test_prepare_upgrades_the_main_schema_before_start(tmp_path, monkeypatch, starting_revision):
    release = module()
    engine = create_engine('sqlite:///' + str(tmp_path / 'main.db'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE alembic_version(version_num TEXT)'))
        conn.execute(text('INSERT INTO alembic_version VALUES(:rev)'), {'rev': starting_revision})
    backup = tmp_path / 'backup'
    backup.mkdir()
    qc_dir = tmp_path / 'qc'
    qc_dir.mkdir()
    (qc_dir / 'existing').write_text('previous data')
    monkeypatch.setattr(release, 'engine', engine)
    monkeypatch.setattr(release.archive.settings, 'qc_department_data_dir', str(qc_dir))
    monkeypatch.setattr(release.archive.settings, 'qc_dossier_enabled', True)
    monkeypatch.setattr(release.archive, 'migrate', lambda: None)
    monkeypatch.setattr(release, 'validate_installed', lambda current: None)
    upgrades = []

    def apply_upgrade(command, *, cwd, check):
        assert command[-2:] == ['upgrade', release.REVISION] and check
        upgrades.append(command[-1])
        with engine.begin() as conn:
            conn.execute(text('UPDATE alembic_version SET version_num=:rev'), {'rev': command[-1]})

    monkeypatch.setattr(release.subprocess, 'run', apply_upgrade)
    assert release.prepare(backup)['revision'] == release.REVISION
    assert release.prepare(backup)['revision'] == release.REVISION
    assert upgrades == [release.REVISION]
    assert list(backup.glob('main-before-*.sqlite3'))
    assert (qc_dir / 'existing').read_text() == 'previous data'

    started = []
    monkeypatch.setattr(release.os, 'execvp', lambda program, args: started.append((program, args)))
    release.start()
    assert started[0][0] == 'uvicorn'
    engine.dispose()


def test_deploy_orders_stop_backup_prepare_enable_health():
    root=Path(__file__).resolve().parents[2];script=(root/'deploy/update-from-github.sh').read_text()
    start=script.index('compose stop api document-tools-worker qc-department')
    assert start<script.index('database-stopped.dump',start)<script.index('qc_dossier_release.py prepare',start)<script.index('compose up -d --no-deps api',start)<script.index('qc_dossier_release.py verify',start)<script.index('notice complete',start)
    compose=(root/'docker-compose.prod.yml').read_text()
    assert 'QC_DOSSIER_ENABLED: "true"' in compose and 'QC_DOSSIER_EMERGENCY_DISABLED' in compose
    assert 'qc-api-data:${QC_DEPARTMENT_DATA_DIR' in compose
