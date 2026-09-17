import copy

import pytest
from sqlalchemy import select

from test_legacy_three_d_importer import importer, m, run, snapshot, state, target  # noqa: F401
from supplement_legacy_three_d_records import supplement_records


def supplement(source, target, **kwargs):
    factory, assets = target
    return supplement_records(*source, session_factory=factory, asset_dir=assets, **kwargs)


def hashes(factory):
    with factory() as db:
        return {(entity, str(row.id) if hasattr(row, "id") else row.factory_id): importer._target_hash(row)
                for entity in importer.MODEL_NAMES for row in db.scalars(select(importer._model(entity)))}


def test_only_missing_records_and_dependencies_preserve_edits_and_inventory(tmp_path, target):
    old = snapshot(tmp_path)
    assert run(old, target)["status"] == "reconciled"
    factory, _ = target
    with factory() as db:
        db.get(m.ThreeDPrintingProductionRecord, importer._id("records", "r1")).remark = "New system correction"
        db.get(m.ThreeDPrintingProduct, importer._id("products", "3")).name = "New system product name"
        db.commit()
    before = hashes(factory)
    payload = state()
    payload["settings"]["laborPerDay"] = 999
    payload["inventory"]["PLA Black"]["stockG"] = 99999
    payload["records"]["2026-09-04"]["items"][0]["remark"] = "Old writer correction"
    payload["products"].append({**payload["products"][2], "id": 4, "name": "New product"})
    new_record = {**payload["records"]["2026-09-04"]["items"][0], "_id": "new-r", "productName": "New product"}
    payload["records"]["2026-09-05"] = {"off": False, "items": [new_record, {**new_record, "_id": "new-deleted", "_deleted": True}]}
    source = snapshot(tmp_path, payload, updated=1788583606084)
    plan = supplement(source, target)
    assert plan["counts"] == {"products": 1, "days": 1, "records": 2}
    assert plan["active_records"] == 1 and plan["tombstones"] == 1
    assert hashes(factory) == before
    result = supplement(source, target, apply=True)
    assert result["status"] == "imported"
    after = hashes(factory)
    assert all(after[key] == value for key, value in before.items())
    with factory() as db:
        record = db.get(m.ThreeDPrintingProductionRecord, importer._id("records", "new-r"))
        assert record.product_id == importer._id("products", "4")
        assert record.business_date == "2026-09-05"
        assert record.inventory_consumed is False
        assert db.get(m.ThreeDPrintingProductionRecord, importer._id("records", "new-deleted")).deleted_at
        assert db.get(m.ThreeDPrintingMigrationBatch, result["batch_id"]).status == "imported"
    assert supplement(source, target, apply=True)["status"] == "already_present"
    assert hashes(factory) == after


def test_empty_target_imports_only_required_images(tmp_path, target):
    source = snapshot(tmp_path)
    factory, assets = target
    before = hashes(factory)
    report = supplement(source, target, apply=True)
    assert report["counts"] == {"products": 1, "days": 1, "records": 4, "images": 1}
    assert all(hashes(factory)[key] == value for key, value in before.items())
    with factory() as db:
        image = db.scalar(select(m.ThreeDPrintingProductImage))
        assert importer._asset_valid(assets, image)


def test_full_import_can_resume_a_supplemented_incremental_snapshot(tmp_path, target):
    assert run(snapshot(tmp_path), target)["status"] == "reconciled"
    payload = state()
    payload["records"]["2026-09-05"] = {"off": False, "items": [
        {**payload["records"]["2026-09-04"]["items"][0], "_id": "new-record"}]}
    source = snapshot(tmp_path, payload, updated=1788583606084)
    assert supplement(source, target, apply=True)["status"] == "imported"
    result = run(source, target, resume=True)
    assert result["status"] == "reconciled", result


def test_invalid_missing_record_rolls_back_all_database_writes(tmp_path, target):
    payload = state()
    payload["records"]["2026-09-04"]["items"][0]["machine"] = 999
    source = snapshot(tmp_path, payload)
    factory, _ = target
    before = hashes(factory)
    with pytest.raises(importer.MigrationError, match="unknown_machine_number"):
        supplement(source, target, apply=True)
    assert hashes(factory) == before
    with factory() as db:
        assert not db.scalars(select(m.ThreeDPrintingMigrationBatch)).all()


def test_manifest_mismatch_and_factory_scope_do_not_write(tmp_path, target):
    source, manifest = snapshot(tmp_path)
    wrong = copy.deepcopy(manifest)
    wrong["snapshot"]["sha256"] = "0" * 64
    with pytest.raises(importer.MigrationError, match="snapshot_manifest_mismatch"):
        supplement((source, wrong), target, apply=True)
    wrong["factory_id"] = "huaxing"
    with pytest.raises(importer.MigrationError, match="migration_scope_mismatch"):
        supplement((source, wrong), target, apply=True)
