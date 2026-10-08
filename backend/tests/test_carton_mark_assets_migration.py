import hashlib
import sqlite3
import os
import subprocess
import sys
from pathlib import Path


def _run_alembic(url, *arguments):
    backend = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "DATABASE_URL": url, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-m", "alembic", "-c", str(backend / "alembic.ini"), *arguments],
        cwd=backend, env=environment, capture_output=True, text=True, encoding="utf-8", check=False)


def test_asset_migration_backfills_originals_deduplicates_and_refuses_data_loss(tmp_path):
    path = tmp_path / "asset-migration.db"
    url = f"sqlite:///{path.as_posix()}"
    result = _run_alembic(url, "upgrade", "20261005_0131")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        for index, contract in enumerate(("4500222793", "SC-OTHER")):
            db.execute("""INSERT INTO carton_mark_templates
              (id,factory_id,customer_name,po,item,contract_number,business_key_sha256,
               document_fingerprint,version,check_status,check_result_json,excel_sha256,pdf_sha256,
               created_by,created_by_name,created_at,updated_at,is_archived,archived_by,archived_by_name,archived_at)
              VALUES (?, 'huaxing','ZURU','PO','100369',?,?,?,1,'需复核','{}','x','p',
                      'seed','seed','2026-10-05','2026-10-05',0,'','','')""",
                      (f"template-{index}", contract, f"key-{index}", f"fingerprint-{index}"))
            for kind, content in (("source_excel", b"excel-source"), ("print_pdf", b"pdf-source")):
                db.execute("""INSERT INTO carton_mark_documents
                  (id,template_id,factory_id,kind,file_name,content_type,size_bytes,sha256,content,created_at)
                  VALUES (?,?,'huaxing',?,?,?, ?,?,?, '2026-10-05')""",
                  (f"doc-{index}-{kind}", f"template-{index}", kind, "source.xlsx" if kind == "source_excel" else "print.pdf",
                   "application/octet-stream", len(content), hashlib.sha256(content).hexdigest(), content))
        before = db.execute("SELECT id, check_status, check_result_json FROM carton_mark_templates ORDER BY id").fetchall()
    result = _run_alembic(url, "upgrade", "20261005_0132")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT id, check_status, check_result_json FROM carton_mark_templates ORDER BY id").fetchall() == before
        rows = db.execute("SELECT content,contract_number,candidates_json FROM carton_mark_assets").fetchall()
        assert len(rows) == 2 and {r[0] for r in rows} == {b"excel-source", b"pdf-source"}
        assert all(r[1] == "" and "SC-OTHER" in r[2] and "4500222793" in r[2] for r in rows)
        foreign_keys = db.execute("PRAGMA foreign_key_list(carton_mark_assets)").fetchall()
        assert any(row[3] == "bound_order_id" and row[6] == "SET NULL" for row in foreign_keys)
        assert any(row[3] == "factory_id" and row[4] == "factory_id" for row in foreign_keys)
    result = _run_alembic(url, "downgrade", "20261005_0131")
    assert result.returncode != 0 and "RuntimeError" in result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM carton_mark_assets").fetchone()[0] == 2
