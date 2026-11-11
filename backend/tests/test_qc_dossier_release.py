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
    (source/'link').symlink_to(tmp_path/'elsewhere')
    with pytest.raises(RuntimeError,match='symlink'):release.inventory(source)


def test_release_rejects_old_unknown_main_version_before_writes(tmp_path,monkeypatch):
    release=module();engine=create_engine('sqlite:///'+str(tmp_path/'main.db'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE alembic_version(version_num TEXT)'))
        conn.execute(text("INSERT INTO alembic_version VALUES('20261022_0175')"))
    monkeypatch.setattr(release,'engine',engine)
    with pytest.raises(RuntimeError,match='0193 or 0194'):release.prepare(tmp_path)
    assert not (tmp_path/'qc-before').exists()


def test_start_requires_preparation_and_readiness_requires_collection(tmp_path,monkeypatch):
    release=module();monkeypatch.setattr(release.archive.settings,'qc_dossier_enabled',True)
    monkeypatch.setattr(release.archive.settings,'qc_department_data_dir',str(tmp_path))
    with pytest.raises(RuntimeError,match='preparation missing'):release.start()
    monkeypatch.setattr(release.archive.settings,'qc_dossier_enabled',False)
    assert release.readiness()=={'enabled':False,'status':'emergency-disabled'}


def test_deploy_orders_stop_backup_prepare_enable_health():
    root=Path(__file__).resolve().parents[2];script=(root/'deploy/update-from-github.sh').read_text()
    start=script.index('compose stop api document-tools-worker qc-department')
    assert start<script.index('database-stopped.dump',start)<script.index('qc_dossier_release.py prepare',start)<script.index('compose up -d --no-deps api',start)<script.index('qc_dossier_release.py verify',start)<script.index('notice complete',start)
    compose=(root/'docker-compose.prod.yml').read_text()
    assert 'QC_DOSSIER_ENABLED: "true"' in compose and 'QC_DOSSIER_EMERGENCY_DISABLED' in compose
    assert 'qc-api-data:${QC_DEPARTMENT_DATA_DIR' in compose
