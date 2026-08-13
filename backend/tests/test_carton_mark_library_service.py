import importlib

import pytest
from fastapi import HTTPException

from test_molding_sample_api import make_client


def _check_result(schema, status: str):
    issue_count = 0 if status == "核对通过" else 1
    comparison_status = "pass" if status == "核对通过" else "changed"
    return schema.CartonMarkDocumentCheckResponse(
        excel_file_name="contract.xlsx",
        pdf_file_name="print.pdf",
        summary=schema.CartonMarkDocumentCheckSummary(
            overall_status=status,
            pass_count=1 if status == "核对通过" else 0,
            changed_count=issue_count,
            missing_count=0,
            unexpected_count=0,
            review_count=0,
        ),
        excel_items=[
            schema.CartonMarkDocumentTextItem(text="ABC", location="箱唛!A1")
        ],
        pdf_items=[
            schema.CartonMarkDocumentTextItem(text="ABC", location="第 1 页 · 第 1 行")
        ],
        comparisons=[
            schema.CartonMarkDocumentComparisonItem(
                status=comparison_status,
                expected="ABC",
                actual="ABC" if comparison_status == "pass" else "ABD",
            )
        ],
        extraction=[
            schema.CartonMarkExtractionStatus(
                source="source_excel", ok=True, engine="test"
            ),
            schema.CartonMarkExtractionStatus(
                source="print_pdf", ok=True, engine="test"
            ),
        ],
    )


def test_library_assigns_versions_stores_all_outcomes_and_rejects_duplicate_hashes(
    monkeypatch,
):
    with make_client(monkeypatch):
        db_module = importlib.import_module("app.db")
        auth = importlib.import_module("app.services.auth")
        schema = importlib.import_module("app.schemas.carton_mark")
        library = importlib.import_module("app.services.carton_mark_library")
        models = importlib.import_module("app.models.carton_mark")
        carton_models = importlib.import_module("app.models.carton_procurement")
        user = auth.AuthContext(
            id="user-carton-test",
            username="carton-test",
            display_name="纸箱测试员",
            roles=("纸箱仓管",),
            role_codes=("carton_warehouse_keeper",),
            permissions=frozenset({"carton_mark:read", "carton_mark:template_upload"}),
            factory_scopes=("huaxing",),
            department_scopes=("pmc-warehouse",),
        )

        with db_module.SessionLocal() as db:
            first = library.create_carton_mark_template(
                db,
                user,
                factory_id="huaxing",
                customer_name="客人 A",
                po="PO-1",
                item="ITEM-1",
                contract_number="C-1",
                excel_file_name="contract.xlsx",
                excel_bytes=b"excel-v1",
                pdf_file_name="print.pdf",
                pdf_bytes=b"pdf-v1",
                check_result=_check_result(schema, "核对通过"),
            )
            second = library.create_carton_mark_template(
                db,
                user,
                factory_id="huaxing",
                customer_name="客人 A",
                po="PO-1",
                item="ITEM-1",
                contract_number="C-1",
                excel_file_name="contract.xlsx",
                excel_bytes=b"excel-v2",
                pdf_file_name="print.pdf",
                pdf_bytes=b"pdf-v2",
                check_result=_check_result(schema, "发现差异"),
            )
            assert (first.version, first.qc_ready) == (1, True)
            assert (second.version, second.qc_ready) == (2, False)
            assert second.check_result.summary.changed_count == 1

            with pytest.raises(HTTPException) as duplicate:
                library.create_carton_mark_template(
                    db,
                    user,
                    factory_id="huaxing",
                    customer_name="另一个名字也不能绕过文档去重",
                    po="PO-2",
                    item="ITEM-2",
                    contract_number="C-2",
                    excel_file_name="contract.xlsx",
                    excel_bytes=b"excel-v2",
                    pdf_file_name="print.pdf",
                    pdf_bytes=b"pdf-v2",
                    check_result=_check_result(schema, "发现差异"),
                )
            assert duplicate.value.status_code == 409
            assert db.query(models.CartonMarkTemplate).count() == 2
            assert db.query(models.CartonMarkDocument).count() == 4
            assert db.query(carton_models.CartonAuditEvent).filter_by(
                entity_type="carton_mark_template"
            ).count() == 2
