"""Isolated real 0040 -> 0098 DDL, seeded shell, and migration failure goldens."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from copy import deepcopy
from io import BytesIO
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from PIL import Image
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
import legacy_three_d_importer as importer
from app.models import three_d_printing as m
from app.services.three_d_printing import seed_three_d_printing_defaults
from legacy_sqlite_reader import file_fingerprint, inspect_snapshot


def migration(pattern):
    path = next((BACKEND / "alembic/versions").glob(pattern))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def target(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'nexus-isolated.sqlite'}")
    @sa.event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        old = migration("20260729_0040_*.py")
        old._create_tables()
        old._install_audit_immutability()
        migration("20260904_0098_*.py").upgrade()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        seed_three_d_printing_defaults(db)
        db.commit()
    yield factory, tmp_path / "assets"
    engine.dispose()


def state():
    return {
        "settings": {"machines": 11, "elecPerMachine": 1.5, "laborPerDay": 220, "lossRate": 1.2, "profitRate": 40},
        "materials": [{"id": "m1", "name": "PLA Black", "type": "PLA", "priceKg": 20}],
        "products": [
            {"id": 1, "name": "Duplicate", "material": "PLA Black", "weight": 10, "time": 2, "price": 3, "qty": 1},
            {"id": 2, "name": "Duplicate", "material": "PLA Black", "weight": 10, "time": 2, "price": 3, "qty": 1},
            {"id": 3, "name": "Unique", "material": "PLA Black", "weight": 10, "time": 2, "price": 3, "qty": 1, "customer": "Current"},
        ],
        "records": {"2026-09-04": {"off": False, "items": [
            {"_id": "r1", "_updatedAt": 1788497206084, "machine": 1, "status": "running", "productName": "Unique", "material": "PLA Black", "weight": .1, "qty": 3, "time": 1, "price": .1, "designFee": 2, "customer": "Historical", "printStartTime": "2026-09-03T23:00:00+08:00", "printEndTime": "2026-09-04T01:00:00+08:00", "autoRecord": True},
            {"_id": "r2", "_updatedAt": 1788497206084, "machine": 2, "status": "running", "productName": "Duplicate", "material": "", "weight": 0, "qty": 2, "time": 0, "price": 0, "printStartTime": "2026-09-04T01:00:00Z", "autoRecord": True},
            {"_id": "r3", "_updatedAt": 1788497206084, "machine": 3, "status": "done", "productName": "Gone", "material": "", "qty": 1, "printEndTime": "2026-09-04T02:00:00Z"},
            {"_id": "deleted", "_updatedAt": 1788497206084, "machine": 4, "status": "running", "productName": "Deleted", "qty": 99, "weight": 99, "price": 99, "_deleted": True},
        ]}},
        "inventory": {"PLA Black": {"stockG": 10, "minStockG": 0}, "PLABlack": {"stockG": 0, "minStockG": 0}},
        "stockInLogs": [{"id": "log1", "date": "2026-09-04", "material": "PLA Black", "amountG": 1000, "cost": 20}],
        "schedules": [], "maintenance": [],
    }


def snapshot(tmp_path, payload=None, *, updated=1788497206084, corrupt_image=False):
    payload = payload if payload is not None else state()
    directory = tmp_path / f"source-{updated}"
    directory.mkdir()
    path = directory / "snapshot.sqlite"
    image = BytesIO()
    Image.new("RGB", (3, 3), "red").save(image, format="JPEG")
    content = b"not a jpeg" if corrupt_image else image.getvalue()
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE app_state(id INTEGER PRIMARY KEY, state_json TEXT NOT NULL, updated_at INTEGER NOT NULL);
        CREATE TABLE product_images(product_id TEXT PRIMARY KEY,storage_type TEXT,mime_type TEXT,image_data BLOB,sha256 TEXT,updated_at INTEGER);
        """)
        db.execute("INSERT INTO app_state VALUES(1,?,?)", (json.dumps(payload), updated))
        db.execute("INSERT INTO product_images VALUES('3','base64','image/jpeg',?,'legacy-data-uri-hash',?)", (content, updated))
    _, _, checks = inspect_snapshot(path)
    manifest = {"factory_id": "huakang-a", "site_code": "heyuan", "snapshot": file_fingerprint(path), "checks": checks}
    return path, manifest


def run(source, target, **options):
    factory, assets = target
    return importer.run_migration(*source, session_factory=factory, asset_dir=assets, **options)


def test_full_import_replay_history_aliases_and_frozen_costs(tmp_path, target):
    source = snapshot(tmp_path)
    before = file_fingerprint(source[0])
    report = run(source, target, chunk_size=3)
    assert report["status"] == "reconciled", report
    assert report["counts"]["products"] == 3
    assert report["counts"]["active_records"] == 3
    assert report["counts"]["soft_deleted_records"] == 1
    assert report["counts"]["inventory_total_g"] == 10
    factory, assets = target
    with factory() as db:
        records = {row.legacy_id: row for row in db.scalars(sa.select(m.ThreeDPrintingProductionRecord))}
        assert records["r1"].customer == "Historical"
        assert records["r1"].run_status == "succeeded"
        assert records["r2"].run_status == "unknown"
        assert records["r2"].reconciliation_status == "pending"
        assert records["r2"].product_id == ""
        assert json.loads(records["r3"].product_snapshot_json)["weight"] is None
        assert json.loads(records["r3"].calculated_cost_snapshot_json)["material_cost_per_unit"] is None
        assert records["deleted"].deleted_at
        movements = db.scalars(sa.select(m.ThreeDPrintingInventoryMovement)).all()
        assert len(movements) == 3
        history = next(row for row in movements if row.movement_type == "legacy_history_only")
        assert history.delta_g == 1000 and history.affects_balance is False
        assert sum(row.delta_g for row in movements if row.affects_balance) == 10
        image = db.scalar(sa.select(m.ThreeDPrintingProductImage))
        assert image.legacy_sha256 == "legacy-data-uri-hash"
        assert file_fingerprint(assets / image.storage_key)["sha256"] == image.sha256
        assert len(db.scalars(sa.select(m.ThreeDPrintingPrinter)).all()) == 11
        ids_before = {entity: [row.id for row in db.scalars(sa.select(model))] for entity, model in (
            ("products", m.ThreeDPrintingProduct), ("records", m.ThreeDPrintingProductionRecord), ("movements", m.ThreeDPrintingInventoryMovement))}
    repeated = run(source, target)
    assert repeated["status"] == "already_reconciled"
    assert repeated["counts"] == report["counts"]
    with factory() as db:
        for entity, model in (("products", m.ThreeDPrintingProduct), ("records", m.ThreeDPrintingProductionRecord), ("movements", m.ThreeDPrintingInventoryMovement)):
            assert [row.id for row in db.scalars(sa.select(model))] == ids_before[entity]
    assert file_fingerprint(source[0]) == before


def test_import_preserves_live_printer_identity_and_replay_accepts_new_telemetry(tmp_path, target):
    factory, _ = target
    with factory() as db:
        printer = db.scalar(sa.select(m.ThreeDPrintingPrinter).where(m.ThreeDPrintingPrinter.machine_no == 1))
        printer.connected = True
        printer.id = "3dprinter-huakang-b-1"
        printer.state = "RUNNING"
        printer.progress_percent = 67
        printer.status_payload_json = '{"connector":{"sequence":100}}'
        printer.revision = 3
        db.commit()
        before = {c.name: getattr(printer,c.name) for c in printer.__table__.columns}
    source = snapshot(tmp_path)
    result = run(source,target)
    assert result["status"] == "reconciled", result
    with factory() as db:
        printer = db.get(m.ThreeDPrintingPrinter,before['id'])
        assert {c.name: getattr(printer,c.name) for c in printer.__table__.columns} == before
        checkpoint = db.scalar(sa.select(m.ThreeDPrintingMigrationRowResult).where(
            m.ThreeDPrintingMigrationRowResult.entity_type == "printers",
            m.ThreeDPrintingMigrationRowResult.target_id == printer.id,
        ))
        checkpoint.target_hash = importer._hash({c.name: getattr(printer,c.name) for c in printer.__table__.columns})
        printer.progress_percent = 68
        db.commit()
    assert run(source,target)['status'] == 'already_reconciled'


def test_interrupt_preserves_checkpoint_and_requires_explicit_resume(tmp_path, target, monkeypatch):
    source = snapshot(tmp_path)
    original = importer._import_item
    def fail_second_product(db, item, *args):
        if item.entity == "products" and item.legacy == "2":
            raise RuntimeError("private-driver-error-MUST-NOT-LEAK")
        return original(db, item, *args)
    monkeypatch.setattr(importer, "_import_item", fail_second_product)
    with pytest.raises(importer.MigrationError, match="^migration_execution_failed$") as interrupted:
        run(source, target, chunk_size=1)
    assert interrupted.value.batch_id.startswith("3dbatch-")
    with target[0]() as db:
        assert len(db.scalars(sa.select(m.ThreeDPrintingProduct)).all()) == 1
        batch = db.scalar(sa.select(m.ThreeDPrintingMigrationBatch))
        assert batch.status == "failed" and not batch.lease_id
        assert json.loads(batch.checkpoint_json)["completed_rows"] > 0
    monkeypatch.setattr(importer, "_import_item", original)
    with pytest.raises(importer.MigrationError, match="migration_resume_required"):
        run(source, target)
    result = run(source, target, resume=True, chunk_size=2)
    assert result["status"] == "reconciled", result
    assert result["row_status_counts"]["skipped"] > 0


def test_image_write_failure_does_not_lose_business_and_retries(tmp_path, target, monkeypatch):
    source = snapshot(tmp_path)
    original = importer._write_asset
    def fail(*args):
        raise importer.MigrationError("asset_write_failed")
    monkeypatch.setattr(importer, "_write_asset", fail)
    report = run(source, target)
    assert report["status"] == "failed"
    assert report["counts"]["production_records"] == 4
    assert report["counts"]["product_images"] == 0
    monkeypatch.setattr(importer, "_write_asset", original)
    repaired = run(source, target, resume=True)
    assert repaired["status"] == "reconciled", repaired
    with target[0]() as db:
        image_row = db.scalar(sa.select(m.ThreeDPrintingMigrationRowResult).where(m.ThreeDPrintingMigrationRowResult.entity_type == "images"))
        assert image_row.attempt_count == 2


def test_incremental_inventory_uses_adjustment_and_keeps_history_immutable(tmp_path, target):
    first = snapshot(tmp_path)
    assert run(first, target)["status"] == "reconciled"
    updated = state()
    updated["inventory"]["PLA Black"]["stockG"] = 25
    updated["products"][2]["customer"] = "New Customer"
    second = snapshot(tmp_path, updated, updated=1788497207084)
    result = run(second, target)
    assert result["status"] == "reconciled", result
    with target[0]() as db:
        rows = db.scalars(sa.select(m.ThreeDPrintingInventoryMovement)).all()
        assert len(rows) == 4
        assert next(row for row in rows if row.movement_type == "migration_adjustment").delta_g == 15
        assert next(row for row in rows if row.movement_type == "legacy_history_only").balance_after_g == 10
        record = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "r1"))
        assert record.customer == "Historical"
    with pytest.raises(importer.MigrationError, match="stale_source_snapshot"):
        run(first, target)


def test_nexus_edits_and_manual_inventory_are_never_overwritten(tmp_path, target):
    first = snapshot(tmp_path)
    assert run(first, target)["status"] == "reconciled"
    with target[0]() as db:
        product = db.scalar(sa.select(m.ThreeDPrintingProduct).where(m.ThreeDPrintingProduct.legacy_id == "3"))
        product.name = "Edited in Nexus"
        inventory = db.scalar(sa.select(m.ThreeDPrintingInventory).where(m.ThreeDPrintingInventory.material_name == "PLA Black"))
        inventory.stock_g = 777
        db.commit()
    updated = state()
    updated["inventory"]["PLA Black"]["stockG"] = 25
    second = snapshot(tmp_path, updated, updated=1788497207084)
    report = run(second, target)
    assert report["status"] == "failed"
    assert "target_edited_in_nexus" in report["error_codes"]
    with target[0]() as db:
        assert db.scalar(sa.select(m.ThreeDPrintingProduct.name).where(m.ThreeDPrintingProduct.legacy_id == "3")) == "Edited in Nexus"
        assert db.scalar(sa.select(m.ThreeDPrintingInventory.stock_g).where(m.ThreeDPrintingInventory.material_name == "PLA Black")) == 777


def test_reconcile_detects_asset_loss_and_business_tampering(tmp_path, target):
    source = snapshot(tmp_path)
    assert run(source, target)["status"] == "reconciled"
    with target[0]() as db:
        image = db.scalar(sa.select(m.ThreeDPrintingProductImage))
        (target[1] / image.storage_key).unlink()
    failed = run(source, target, mode="reconcile")
    assert failed["status"] == "failed" and "reconciliation_asset_mismatch" in failed["error_codes"]
    assert run(source, target, resume=True)["status"] == "reconciled"
    with target[0]() as db:
        record = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "r1"))
        record.quantity = 99
        db.flush()
        checkpoint = db.scalar(sa.select(m.ThreeDPrintingMigrationRowResult).where(m.ThreeDPrintingMigrationRowResult.entity_type == "records", m.ThreeDPrintingMigrationRowResult.legacy_id == "r1"))
        checkpoint.target_hash = importer._target_hash(record)
        db.commit()
    report = run(source, target, mode="reconcile")
    assert "reconciliation_business_field_mismatch" in report["error_codes"]


def test_wrong_source_hash_batch_and_live_lease_are_rejected(tmp_path, target):
    source = snapshot(tmp_path)
    bad = deepcopy(source[1])
    bad["snapshot"]["sha256"] = "0" * 64
    with pytest.raises(importer.MigrationError, match="snapshot_manifest_mismatch"):
        run((source[0], bad), target)
    result = run(source, target)
    with pytest.raises(importer.MigrationError, match="migration_batch_source_mismatch"):
        run(source, target, migration_batch="wrong")
    with target[0]() as db:
        batch = db.get(m.ThreeDPrintingMigrationBatch, result["batch_id"])
        batch.lease_id = "another-worker"
        batch.leased_until = "2999-01-01T00:00:00.000+00:00"
        db.commit()
    with pytest.raises(importer.MigrationError, match="migration_lease_active"):
        run(source, target, resume=True)


def test_bad_image_and_numeric_values_are_explicit_row_failures(tmp_path, target):
    payload = state()
    payload["products"][0]["qty"] = "not a number"
    report = run(snapshot(tmp_path, payload, corrupt_image=True), target)
    assert report["status"] == "failed"
    assert "invalid_numeric_field" in report["error_codes"]
    assert "invalid_source_image" in report["error_codes"]
    assert report["counts"]["production_records"] == 4
    assert report["counts"]["inventory_total_g"] == 10


def test_duplicate_source_ids_do_not_select_arbitrary_winner(tmp_path, target):
    payload = state()
    payload["products"][1]["id"] = 1
    report = run(snapshot(tmp_path, payload), target)
    assert report["status"] == "failed"
    assert "duplicate_legacy_id" in report["error_codes"]
    with target[0]() as db:
        assert db.scalar(sa.select(m.ThreeDPrintingProduct).where(m.ThreeDPrintingProduct.legacy_id == "1")) is None


def test_existing_unowned_business_blocks_seed_adoption_without_overwrite(tmp_path, target):
    with target[0]() as db:
        db.add(m.ThreeDPrintingInventory(id="manual", factory_id="huakang-a", material_name="PLA Black", stock_g=321,
                                        min_stock_g=0, created_at="2026-09-04", updated_at="2026-09-04"))
        db.commit()
    report = run(snapshot(tmp_path), target)
    assert report["status"] == "failed"
    assert "target_has_no_migration_ownership" in report["error_codes"]
    with target[0]() as db:
        assert db.get(m.ThreeDPrintingInventory, "manual").stock_g == 321


def test_corrupt_asset_failed_retry_keeps_committed_ownership(tmp_path, target):
    source = snapshot(tmp_path)
    assert run(source, target)["status"] == "reconciled"
    with target[0]() as db:
        image = db.scalar(sa.select(m.ThreeDPrintingProductImage))
        path = target[1] / image.storage_key
        original = db.scalar(sa.select(m.ThreeDPrintingMigrationRowResult).where(m.ThreeDPrintingMigrationRowResult.entity_type == "images"))
        ownership = original.target_id, original.target_hash, original.source_hash
    path.write_bytes(b"damaged file")
    assert run(source, target, mode="reconcile")["status"] == "failed"
    failed_retry = run(source, target, resume=True)
    assert failed_retry["status"] == "failed" and "asset_content_conflict" in failed_retry["error_codes"]
    with target[0]() as db:
        checkpoint = db.scalar(sa.select(m.ThreeDPrintingMigrationRowResult).where(m.ThreeDPrintingMigrationRowResult.entity_type == "images"))
        assert checkpoint.status == "conflict"
        assert (checkpoint.target_id, checkpoint.target_hash, checkpoint.source_hash) == ownership
    path.unlink()
    assert run(source, target, resume=True)["status"] == "reconciled"


def test_new_snapshot_failed_image_update_does_not_claim_new_source_applied(tmp_path, target, monkeypatch):
    first = snapshot(tmp_path)
    assert run(first, target)["status"] == "reconciled"
    second = snapshot(tmp_path, updated=1788497207084)
    original = importer._write_asset
    def fail(*args):
        raise importer.MigrationError("asset_write_failed")
    monkeypatch.setattr(importer, "_write_asset", fail)
    failed = run(second, target)
    assert failed["status"] == "failed"
    with target[0]() as db:
        new_row = db.scalar(sa.select(m.ThreeDPrintingMigrationRowResult).where(m.ThreeDPrintingMigrationRowResult.batch_id == failed["batch_id"], m.ThreeDPrintingMigrationRowResult.entity_type == "images"))
        assert new_row.target_hash == "" and new_row.target_id == ""
    monkeypatch.setattr(importer, "_write_asset", original)
    repaired = run(second, target, resume=True)
    assert repaired["status"] == "reconciled", repaired
    with target[0]() as db:
        new_row = db.scalar(sa.select(m.ThreeDPrintingMigrationRowResult).where(m.ThreeDPrintingMigrationRowResult.batch_id == failed["batch_id"], m.ThreeDPrintingMigrationRowResult.entity_type == "images"))
        assert new_row.status == "updated" and new_row.target_hash and new_row.attempt_count == 2


def test_new_master_name_and_price_do_not_rewrite_historical_mapping_or_cost(tmp_path, target):
    first = snapshot(tmp_path)
    assert run(first, target)["status"] == "reconciled"
    with target[0]() as db:
        old = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "r1"))
        frozen = old.product_id, old.product_snapshot_json, old.calculated_cost_snapshot_json, old.data_quality_flags_json
    changed = state()
    changed["products"][2]["name"] = "New master name"
    changed["materials"][0]["priceKg"] = 99
    changed["settings"]["laborPerDay"] = 999
    second = snapshot(tmp_path, changed, updated=1788497207084)
    report = run(second, target)
    assert report["status"] == "reconciled", report
    with target[0]() as db:
        current = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "r1"))
        assert (current.product_id, current.product_snapshot_json, current.calculated_cost_snapshot_json, current.data_quality_flags_json) == frozen


def test_missing_record_timestamps_use_source_time_in_import_and_reconcile(tmp_path, target):
    payload = state()
    raw = payload["records"]["2026-09-04"]["items"][-1]
    raw.pop("_updatedAt")
    report = run(snapshot(tmp_path, payload), target)
    assert report["status"] == "reconciled", report
    with target[0]() as db:
        original = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "deleted"))
        frozen = original.legacy_updated_at, original.deleted_at
    report = run(snapshot(tmp_path, payload, updated=1788497207084), target)
    assert report["status"] == "reconciled", report
    with target[0]() as db:
        current = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "deleted"))
        assert (current.legacy_updated_at, current.deleted_at) == frozen


def test_removed_source_row_is_detected_even_after_ownership_retry_conflict(tmp_path, target):
    first = snapshot(tmp_path)
    assert run(first, target)["status"] == "reconciled"
    with target[0]() as db:
        row = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "r3"))
        row.quantity = 999
        db.commit()
    assert run(first, target, mode="reconcile")["status"] == "failed"
    assert run(first, target, resume=True)["status"] == "failed"
    changed = state()
    changed["records"]["2026-09-04"]["items"] = [row for row in changed["records"]["2026-09-04"]["items"] if row["_id"] != "r3"]
    result = run(snapshot(tmp_path, changed, updated=1788497207084), target)
    assert result["status"] == "failed"
    assert "source_missing_previously_imported_row" in result["error_codes"]


def test_record_corrections_preserve_rates_and_require_review_for_new_material(tmp_path, target):
    first = snapshot(tmp_path)
    assert run(first, target)["status"] == "reconciled"
    with target[0]() as db:
        row = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "r1"))
        frozen = row.calculated_cost_snapshot_json
    changed = state()
    record = changed["records"]["2026-09-04"]["items"][0]
    record.update(remark="Corrected note", _updatedAt=1788497207084, printEndTime="2026-09-04T02:00:00+08:00")
    changed["settings"]["laborPerDay"] = 999
    changed["materials"][0]["priceKg"] = 99
    assert run(snapshot(tmp_path, changed, updated=1788497207084), target)["status"] == "reconciled"
    with target[0]() as db:
        row = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "r1"))
        assert row.calculated_cost_snapshot_json == frozen
    record.update(weight=.2, _updatedAt=1788497208084)
    assert run(snapshot(tmp_path, changed, updated=1788497208084), target)["status"] == "reconciled"
    with target[0]() as db:
        row = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "r1"))
        cost = json.loads(row.calculated_cost_snapshot_json)
        assert cost["settings"]["laborPerDay"] == 220
        assert cost["material_price_kg"] == 20
        assert cost["inputs"]["weight"] == .2
        assert cost["correction"]["requires_review"] is False
    changed["materials"].append({"id": "m2", "name": "New Material", "priceKg": 888})
    record.update(material="New Material", _updatedAt=1788497209084)
    result = run(snapshot(tmp_path, changed, updated=1788497209084), target)
    assert result["status"] == "reconciled", result
    with target[0]() as db:
        row = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "r1"))
        cost = json.loads(row.calculated_cost_snapshot_json)
        assert cost["material_price_kg"] is None and cost["material_cost_per_unit"] is None
        assert cost["correction"]["requires_review"] is True
        assert "cost_snapshot_requires_review" in json.loads(row.data_quality_flags_json)
    record.update(remark="Another note", _updatedAt=1788497210084)
    assert run(snapshot(tmp_path, changed, updated=1788497210084), target)["status"] == "reconciled"
    with target[0]() as db:
        row = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "r1"))
        assert json.loads(row.calculated_cost_snapshot_json)["correction"]["requires_review"] is True
        assert "cost_snapshot_requires_review" in json.loads(row.data_quality_flags_json)
    record.update(weight=.3, _updatedAt=1788497211084)
    assert run(snapshot(tmp_path, changed, updated=1788497211084), target)["status"] == "reconciled"
    with target[0]() as db:
        row = db.scalar(sa.select(m.ThreeDPrintingProductionRecord).where(m.ThreeDPrintingProductionRecord.legacy_id == "r1"))
        cost = json.loads(row.calculated_cost_snapshot_json)
        assert cost["material_price_kg"] is None and cost["correction"]["requires_review"] is True
        assert "cost_snapshot_requires_review" in json.loads(row.data_quality_flags_json)
