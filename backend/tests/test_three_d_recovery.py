import importlib.util
import sqlite3
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "deploy/three-d-printing/recovery.py"
spec = importlib.util.spec_from_file_location("three_d_recovery", PATH)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def test_backup_restore_twice_and_reject_corruption_or_existing_target(tmp_path):
    database = tmp_path / "business.sqlite"
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "图像.bin").write_bytes(b"asset-preserved")
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE alembic_version(version_num TEXT)")
        db.execute("INSERT INTO alembic_version VALUES ('20260904_0099')")
        db.execute("CREATE TABLE business(id INTEGER, quantity INTEGER)")
        db.execute("INSERT INTO business VALUES (1, 137)")
    original = recovery.digest(database)
    with pytest.raises(ValueError, match="Stop ALL"):
        recovery.backup(database, assets, tmp_path / "blocked")
    for index in range(2):
        bundle = tmp_path / f"backup-{index}"
        target = tmp_path / f"restored-{index}"
        recovery.backup(database, assets, bundle, writers_stopped=True)
        recovery.restore(bundle, target)
        assert (target / "assets/图像.bin").read_bytes() == b"asset-preserved"
        with sqlite3.connect(target / "database.sqlite") as db:
            assert db.execute("SELECT quantity FROM business").fetchone()[0] == 137
        with pytest.raises(FileExistsError):
            recovery.restore(bundle, target)
    assert recovery.digest(database) == original
    (bundle / "assets/图像.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="manifest mismatch"):
        recovery.restore(bundle, tmp_path / "corrupt-restore")
    assert not (tmp_path / "corrupt-restore").exists()
