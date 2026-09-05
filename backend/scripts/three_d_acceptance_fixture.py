"""Generate synthetic browser fixtures in a NEW directory; never imports real data."""

import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    os.environ.update(
        DATABASE_URL=f"sqlite:///{directory / 'fixture.sqlite'}",
        THREE_D_ASSET_DIR=str(directory / "assets"),
        SEED_ADMIN_PASSWORD="Local3DTestOnly!2026",
        AUTHZ_MODE="enforce",
        THREE_D_CONNECTOR_ENABLED="false",
        THREE_D_CONNECTOR_CONTROL_ENABLED="false",
    )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.db import SessionLocal, engine, init_db
    from app.models import three_d_printing as m

    init_db()
    (directory / "assets").mkdir(exist_ok=True)
    with engine.begin() as db:
        db.exec_driver_sql(
            "CREATE TABLE alembic_version(version_num VARCHAR(32) PRIMARY KEY)"
        )
        db.exec_driver_sql("INSERT INTO alembic_version VALUES ('20260904_0099')")
    with SessionLocal() as db:
        db.add(
            m.ThreeDPrintingSite(
                id="qa-site",
                factory_id="huakang-a",
                site_code="qa",
                name="合成验收站点",
                enabled=False,
            )
        )
        db.flush()
        db.add(
            m.ThreeDPrintingMaterial(
                id="qa-pla",
                factory_id="huakang-a",
                name="PLA",
                price_per_kg=100,
                is_active=True,
                created_at="2026-09-04",
                updated_at="2026-09-04",
            )
        )
        for n in range(1316):
            db.add(
                m.ThreeDPrintingProduct(
                    id=f"qa-product-{n:04}",
                    factory_id="huakang-a",
                    name=f"验收产品 {n:04}",
                    customer="合成数据客户",
                    material_name="PLA",
                    weight_g=10,
                    default_quantity=1,
                    duration_hours=1,
                    quoted_price=20,
                    created_at="2026-09-04",
                    updated_at="2026-09-04",
                )
            )
        for n in range(3020):
            db.add(
                m.ThreeDPrintingProductionRecord(
                    id=f"qa-record-{n:04}",
                    factory_id="huakang-a",
                    business_date="2026-09-04",
                    machine_no=n % 11 + 1,
                    status="done",
                    run_status="succeeded",
                    product_id=f"qa-product-{n % 1316:04}",
                    product_name=f"验收产品 {n % 1316:04}",
                    material_name="PLA",
                    weight_g=10,
                    quantity=1,
                    duration_hours=1,
                    source_system="nexus",
                    reconciliation_status="none",
                    created_at="2026-09-04T10:00:00+08:00",
                    updated_at="2026-09-04T10:00:00+08:00",
                )
            )
        db.add(
            m.ThreeDPrintingMigrationBatch(
                id="qa-batch",
                factory_id="huakang-a",
                site_id="qa-site",
                source_system="synthetic",
                source_updated_at_ms=1788523200000,
                migration_version="synthetic-acceptance-v1",
                source_sha256="a" * 64,
                status="reconciled",
                started_at="2026-09-04T10:00:00+08:00",
                reconciliation_json='{"passed":true,"expected":{"products":1316,"production_records":3020},"actual":{"products":1316,"production_records":3020}}',
            )
        )
        db.commit()
    print(
        f"Synthetic fixtures created: {directory}; products=1316, records=3020; no hardware enabled"
    )


if __name__ == "__main__":
    main()
