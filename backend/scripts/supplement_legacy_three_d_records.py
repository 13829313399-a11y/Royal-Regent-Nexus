"""Append missing print history and its product/image dependencies only.

Uses the existing SQLite migration mapping and row provenance. Existing business
rows are never updated. A partial batch stays `imported`, not fully `reconciled`,
so it never claims a full migration. After an earlier full migration, the full
importer can resume this snapshot explicitly. An initially empty target keeps
its settings unowned; a later full cutover still needs a separate migration plan.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from sqlalchemy import select

import legacy_three_d_importer as imp
from legacy_sqlite_reader import connect_readonly, file_fingerprint, inspect_snapshot


def _plan(db, items):
    records = {r.legacy_id: r for r in db.scalars(select(imp.models.ThreeDPrintingProductionRecord).where(
        imp.models.ThreeDPrintingProductionRecord.factory_id == imp.FACTORY)) if r.legacy_id}
    missing = [i for i in items if i.entity == "records" and i.legacy not in records]
    names = defaultdict(list)
    for item in items:
        if item.entity == "products":
            names[item.raw.get("name")].append(item)
    required = {names[i.raw.get("productName")][0].legacy for i in missing
                if i.raw.get("productName") and len(names[i.raw.get("productName")]) == 1}
    days = {i.raw["business_date"] for i in missing}
    selected = [i for i in items if i.entity == "records" and i in missing
                or i.entity == "products" and i.legacy in required
                or i.entity == "images" and i.legacy in required
                or i.entity == "days" and i.legacy in days]
    additions = []
    for item in selected:
        if item.error:
            raise imp.MigrationError(item.error)
        matches = db.scalars(imp._natural_query(item)).all()
        if len(matches) > 1:
            raise imp.MigrationError("ambiguous_target_identity")
        if not matches:
            additions.append(item)
    by_day = Counter(i.raw["business_date"] for i in missing)
    report = {
        "scope": "missing_print_records_and_dependencies",
        "counts": dict(Counter(i.entity for i in additions)),
        "records_by_day": dict(sorted(by_day.items())),
        "active_records": sum(not i.raw.get("_deleted", False) for i in missing),
        "tombstones": sum(bool(i.raw.get("_deleted", False)) for i in missing),
        "existing_records_preserved": sum(i.entity == "records" and i.legacy in records for i in items),
    }
    return additions, report


def supplement_records(snapshot_path, manifest, *, session_factory, asset_dir, apply=False):
    """Plan by default; explicit apply commits all additions in one transaction."""
    source, assets = Path(snapshot_path).resolve(), Path(asset_dir).resolve()
    if manifest.get("factory_id") != imp.FACTORY or manifest.get("site_code") != "heyuan":
        raise imp.MigrationError("migration_scope_mismatch")
    if source == assets or assets in source.parents or source in assets.parents:
        raise imp.MigrationError("asset_source_overlap")
    if any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-shm")):
        raise imp.MigrationError("standalone_snapshot_required")
    with tempfile.TemporaryDirectory(prefix="three-d-supplement-") as temp:
        pinned = Path(temp) / "snapshot.sqlite"
        shutil.copyfile(source, pinned)
        fingerprint = file_fingerprint(pinned)
        if fingerprint != {k: manifest["snapshot"].get(k) for k in fingerprint}:
            raise imp.MigrationError("snapshot_manifest_mismatch")
        state, images, checks = inspect_snapshot(pinned)
        if checks["state_updated_at_ms"] != manifest["checks"]["state_updated_at_ms"]:
            raise imp.MigrationError("snapshot_timestamp_mismatch")
        items = imp._items(state, images)
        with session_factory() as db, closing(connect_readonly(pinned)) as source_db:
            imp._schema_ready(db)
            if apply:
                imp._lock_scope(db)
            additions, report = _plan(db, items)
            report.update(source_sha256=fingerprint["sha256"], source_updated_at=checks["state_updated_at_utc"])
            if not apply or not additions:
                report["status"] = "planned" if not apply else "already_present"
                return report
            batches = db.scalars(select(imp.models.ThreeDPrintingMigrationBatch).where(
                imp.models.ThreeDPrintingMigrationBatch.factory_id == imp.FACTORY,
                imp.models.ThreeDPrintingMigrationBatch.site_id == imp.SITE,
                imp.models.ThreeDPrintingMigrationBatch.source_system == imp.SOURCE)).all()
            now = imp._now()
            if any(b.lease_id and b.leased_until > now for b in batches):
                raise imp.MigrationError("migration_lease_active")
            if any(b.source_updated_at_ms > checks["state_updated_at_ms"] for b in batches):
                raise imp.MigrationError("stale_source_snapshot")
            batch = next((b for b in batches if b.source_sha256 == fingerprint["sha256"]), None)
            if batch is None and any(b.source_updated_at_ms == checks["state_updated_at_ms"] for b in batches):
                raise imp.MigrationError("source_timestamp_conflict")
            if batch is None:
                batch = imp.models.ThreeDPrintingMigrationBatch(
                    id="3dbatch-" + uuid4().hex, factory_id=imp.FACTORY, site_id=imp.SITE,
                    source_system=imp.SOURCE, source_sha256=fingerprint["sha256"],
                    source_updated_at_ms=checks["state_updated_at_ms"], source_size_bytes=fingerprint["size_bytes"],
                    migration_version=imp.VERSION, status="importing", started_at=now,
                    expected_counts_json=imp._json(imp._expected(imp.analyze_state(state, images))),
                    image_count=len(images), image_bytes=sum(i["size_bytes"] for i in images))
                db.add(batch)
                db.flush()
            elif batch.migration_version != imp.VERSION:
                raise imp.MigrationError("migration_version_mismatch")
            # Keep source-owned products resolvable by the established mapper.
            # New products precede records; image metadata comes after records.
            inserted = []
            for item in additions:
                status, identity, target_hash = imp._import_item(
                    db, item, state, batch, source_db, assets, checks["state_updated_at_utc"])
                if status != "imported":
                    raise imp.MigrationError("supplement_must_only_insert")
                imp._checkpoint(db, batch, item, status, identity, target_hash)
                inserted.append({"entity": item.entity, "legacy_id": item.legacy, "target_id": identity})
            for item in additions:
                row = db.scalar(imp._natural_query(item))
                if row is None or (item.entity == "images" and not imp._asset_valid(assets, row)):
                    raise imp.MigrationError("supplement_verification_failed")
            report.update(status="imported", batch_id=batch.id, inserted=inserted)
            batch.status = "imported"
            batch.summary_json = imp._json({k: v for k, v in report.items() if k != "inserted"})
            batch.checkpoint_json = imp._json({"scope": report["scope"], "added": len(inserted)})
            batch.completed_at, batch.lease_id, batch.leased_until = now, "", ""
            db.add(imp.models.ThreeDPrintingAuditEvent(
                id="3daudit-" + uuid4().hex, factory_id=imp.FACTORY, entity_type="migration_batch", entity_id=batch.id,
                action="missing_print_records_imported", detail_json=batch.summary_json,
                actor_id="legacy-migration", actor_name="旧系统记录补入", actor_type="system", created_at=now))
            db.commit()
            return report
